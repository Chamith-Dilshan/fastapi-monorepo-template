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

    # `get_db` rolls the request's transaction back when an exception
    # escapes — correct for nearly everything. A subclass sets this to
    # True only when it represents a *security response* whose database
    # side effects must survive the error (see RefreshTokenReuseException).
    # Opt-in per class, never per call site.
    persist_on_error: bool = False

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


class EmailNotVerifiedException(AppException):
    """Correct credentials, but the address was never confirmed. Its own
    error code so a frontend can send the person to the verification page
    instead of showing a generic failure. Only ever raised *after* the
    password checks out, so it reveals nothing to someone guessing emails.
    """

    def __init__(
        self, message: str = "Please verify your email address", status_code: int = 403
    ):
        super().__init__(status_code, message, error_code="email_not_verified")


class InvalidPasswordException(AppException):
    """A *logged-in* user supplied the wrong current password. Deliberately
    a 400, not a 401: their session is fine, and a 401 tells a frontend
    "your token is bad — go refresh it", which is the wrong reaction here.
    """

    def __init__(self, message: str = "Incorrect password", status_code: int = 400):
        super().__init__(status_code, message, error_code="invalid_password")


class RefreshTokenReuseException(UnauthorizedException):
    """A refresh token that was already rotated away was presented again —
    the signature of a stolen token being replayed (by the thief, or by the
    real owner after the thief already used it). TokenService revokes the
    whole token family before raising this, and that revocation has to be
     committed even though the response is a 401, so this opts out of the
    usual rollback.
    """

    persist_on_error = True

    def __init__(self) -> None:
        super().__init__(message="Session expired, please sign in again")
        self.error_code = "refresh_token_reuse"


class InvalidOTPException(AppException):
    """Wrong code, expired code, already-used code, too many attempts, or
    no active code at all for that purpose — deliberately one exception
    and one message for every one of those cases. Distinguishing them in
    the response would let an attacker tell "expired" from "wrong" from
    "never requested", which is exactly the kind of oracle an OTP flow
    should not hand out. The real reason is still in the log line
    (`app.services.otp_service`), just not in the HTTP response.
    """

    def __init__(
        self, message: str = "Invalid or expired code", status_code: int = 400
    ):
        super().__init__(status_code, message, error_code="invalid_otp")


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
