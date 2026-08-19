"""Application exception hierarchy.

Domain modules (Phase 3+) raise these instead of building JSONResponses by
hand; the handlers registered in `core.exceptions.handlers` turn them into
the standard error envelope from docs/api/API.md.
"""

from typing import Any


class AppError(Exception):
    """Base class for errors that should reach the client as a structured envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(
        self, message: str = "Resource not found", details: list[Any] | None = None
    ) -> None:
        super().__init__(404, "NOT_FOUND", message, details)


class BadRequestError(AppError):
    def __init__(self, message: str = "Bad request", details: list[Any] | None = None) -> None:
        super().__init__(400, "BAD_REQUEST", message, details)


class UnauthorizedError(AppError):
    """`code` varies by cause (INVALID_CREDENTIALS, INVALID_TOKEN, ...) so
    callers can distinguish causes internally/in logs, while the message stays
    generic enough not to leak which check failed - see auth/service.py."""

    def __init__(
        self,
        message: str = "Authentication required",
        code: str = "UNAUTHORIZED",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(401, code, message, details)


class ConflictError(AppError):
    def __init__(
        self,
        message: str = "Resource already exists",
        code: str = "CONFLICT",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(409, code, message, details)
