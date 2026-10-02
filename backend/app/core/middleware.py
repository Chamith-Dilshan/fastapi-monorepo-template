"""Request-scoped middleware.

`RequestContextMiddleware` is intentionally the outermost middleware (added
last, so it runs first — see `app.main`): every other layer, including the
exception handlers, needs `request_id_var` already set.
"""

import time

import structlog
from fastapi.requests import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.request_context import new_request_id, request_id_var

logger = structlog.get_logger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_id = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming_id or new_request_id()
        token = request_id_var.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Let the exception continue to FastAPI's exception handlers
            # (app.core.exception_handlers) — this except exists only so the
            # "request finished" log line below still fires with an
            # accurate duration and a 500 status, instead of being skipped
            # because call_next raised.
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            request_id_var.reset(token)
            structlog.contextvars.unbind_contextvars("request_id")
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id

        log_method = logger.warning if response.status_code >= 400 else logger.info
        log_method(
            "request_finished",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        request_id_var.reset(token)
        structlog.contextvars.unbind_contextvars("request_id")
        return response
