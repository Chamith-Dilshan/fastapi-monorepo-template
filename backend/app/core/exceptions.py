"""Application exception hierarchy.

Every exception raised deliberately by our own code (as opposed to letting
an unexpected bug surface as a bare `Exception`) should be one of these, or
a subclass of one of these. `app.core.exception_handlers` maps the whole
tree to one consistent JSON error envelope, so raising `NotFoundException`
from a repository looks the same to the client as raising it from a route.

`error_code` is a short, stable, machine-readable slug — separate from
`message`, which is free text meant for a human/log line and may change
without it being a breaking API change. Frontend code should switch on
`error_code`, never on the message string.
"""


class AppException(Exception):
    """Base class for every exception this codebase raises on purpose."""

    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(
        self, message: str, status_code: int = 404, details: dict | None = None
    ):
        super().__init__(status_code, message, error_code="not_found", details=details)


class ConflictException(AppException):
    def __init__(
        self, message: str, status_code: int = 409, details: dict | None = None
    ):
        super().__init__(status_code, message, error_code="conflict", details=details)


class ValidationException(AppException):
    def __init__(
        self, message: str, status_code: int = 422, details: dict | None = None
    ):
        super().__init__(
            status_code, message, error_code="validation_error", details=details
        )


class ForbiddenException(AppException):
    def __init__(
        self, message: str, status_code: int = 403, details: dict | None = None
    ):
        super().__init__(status_code, message, error_code="forbidden", details=details)


class UnauthorizedException(AppException):
    def __init__(
        self,
        message: str = "Could not validate credentials",
        status_code: int = 401,
        details: dict | None = None,
    ):
        super().__init__(
            status_code, message, error_code="unauthorized", details=details
        )


class DatabaseException(AppException):
    """Raised by the repository layer when an SQLAlchemy call fails.

    Deliberately does not accept or expose the underlying driver error to
    the client — chain it with `raise DatabaseException() from exc` so the
    original exception is still visible in logs/Sentry, without leaking
    schema or query details in the response.
    """

    def __init__(
        self, message: str = "Database operation failed", status_code: int = 500
    ):
        super().__init__(status_code, message, error_code="database_error")
