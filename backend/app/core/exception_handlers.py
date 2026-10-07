"""Global exception handling.

Every error response the API returns — whichever of the paths below
produced it — has the same shape:

    {
      "error": {
        "code": "not_found",
        "message": "Post not found",
        "details": null,
        "request_id": "9f8c2b7a1e4d4c6b8a2f0d1e3c5b7a9f"
      }
    }

`code` is the stable, machine-readable slug (`AppException.error_code`);
`message` is human-readable and may change; `request_id` lets a client
report an error and have it found in logs/Sentry immediately. Register with
`register_exception_handlers(app)` in `app.main` — order doesn't matter,
FastAPI dispatches by the most specific matching exception type.
"""

import structlog
from fastapi import FastAPI, status
from fastapi.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppException
from app.core.request_context import get_request_id

logger = structlog.get_logger("app.errors")

_STATUS_TO_ERROR_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


def _envelope(*, code: str, message: str, details: dict | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": get_request_id(),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        log = logger.error if exc.status_code >= 500 else logger.warning
        log(
            "app_exception",
            error_code=exc.error_code,
            status_code=exc.status_code,
            path=request.url.path,
            exc_info=exc.status_code >= 500,
        )
        if exc.status_code >= 500:
            _capture_to_sentry(exc)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(
                code=exc.error_code, message=exc.message, details=exc.details
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(
            "request_validation_error",
            path=request.url.path,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                code="validation_error",
                message="Request validation failed",
                details={"field_errors": exc.errors()},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # Covers plain `raise HTTPException(...)` call sites (e.g. auth
        # flows in app.core.security) that predate the AppException
        # hierarchy — normalized into the same envelope rather than
        # FastAPI's default `{"detail": ...}` shape.
        code = _STATUS_TO_ERROR_CODE.get(exc.status_code, "http_error")
        log = logger.error if exc.status_code >= 500 else logger.warning
        log("http_exception", status_code=exc.status_code, path=request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code=code, message=str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(
        request: Request, exc: SQLAlchemyError
    ) -> JSONResponse:
        # Safety net: repositories should catch SQLAlchemyError and raise
        # app.core.exceptions.DatabaseException themselves (see
        # AGENT_GUIDE.md's "done means" checklist — errors shouldn't leak
        # raw driver exceptions). This exists for whatever slips through.
        logger.error(
            "unhandled_database_error",
            path=request.url.path,
            exc_info=True,
        )
        _capture_to_sentry(exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                code="database_error", message="Database operation failed"
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            exc_info=True,
        )
        _capture_to_sentry(exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(code="internal_error", message="Internal server error"),
        )


def _capture_to_sentry(exc: Exception) -> None:
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except ImportError:
        pass
