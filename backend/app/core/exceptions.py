"""Application-specific exceptions."""

from fastapi import HTTPException, status


class AppError(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status.HTTP_404_NOT_FOUND)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Not authenticated") -> None:
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, status.HTTP_403_FORBIDDEN)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(message, status.HTTP_409_CONFLICT)


class TooManyRequestsError(AppError):
    def __init__(self, retry_after: int, message: str = "Too many requests. Please slow down and try again shortly.") -> None:
        super().__init__(message, status.HTTP_429_TOO_MANY_REQUESTS)
        self.retry_after = retry_after


def raise_http_for_app_error(exc: AppError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)
