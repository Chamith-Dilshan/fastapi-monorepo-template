class AppException(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
    ):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str, status_code: int = 404):
        super().__init__(status_code, message)


class ConflictException(AppException):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(status_code, message)


class ValidationException(AppException):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(status_code, message)

class PostNotFoundError(Exception):
    pass

class PostOwnershipError(Exception):
    pass


class UserNotFoundError(Exception):
    pass

class ForbiddenException(AppException):
    def __init__(self, message: str, status_code: int = 403):
        super().__init__(status_code, message)

class DatabaseException(Exception):
    def __init__(
        self,
        message: str = "Database operation failed",
    ):
        self.message = message
        super().__init__(message)
