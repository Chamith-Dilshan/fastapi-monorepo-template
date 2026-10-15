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

from app.core.request_context import (
    client_ip_var,
    new_request_id,
    request_id_var,
    user_agent_var,
)

logger = structlog.get_logger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"

# Polled constantly by infrastructure (Compose healthcheck, Prometheus
# scraping every ~15s) rather than caused by a user action — an access-log
# line per hit is noise, not signal. The request id is still generated and
# set on the response either way; only the INFO/WARNING log line is
# skipped, so a failure on one of these still logs via the `except` branch
# below (errors are signal even here).
_UNLOGGED_PATHS = frozenset({"/health", "/health/ready", "/metrics"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_id = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming_id or new_request_id()
        user_agent = request.headers.get("user-agent")

        tokens = [
            (request_id_var, request_id_var.set(request_id)),
            (
                client_ip_var,
                client_ip_var.set(request.client.host if request.client else None),
            ),
            (
                user_agent_var,
                user_agent_var.set(user_agent),
            ),
        ]
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                # Let the exception continue to FastAPI's exception handlers
                # (app.core.exception_handlers) — this except exists only so
                # the "request finished" log line below still fires with an
                # accurate duration and a 500 status, instead of being
                # skipped because call_next raised.
                logger.error(
                    "request_failed",
                    method=request.method,
                    path=request.url.path,
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                )
                raise

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            response.headers[REQUEST_ID_HEADER] = request_id

            if request.url.path not in _UNLOGGED_PATHS or response.status_code >= 400:
                log_method = (
                    logger.warning if response.status_code >= 400 else logger.info
                )
                log_method(
                    "request_finished",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            return response
        finally:
            for var, token in tokens:
                var.reset(token)
            structlog.contextvars.unbind_contextvars("request_id")
