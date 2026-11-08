from __future__ import annotations

from typing import Any


class TroveError(Exception):
    """Base class for errors that map to a stable user-facing code."""

    status_code = 400
    code = "trove.error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationError(TroveError):
    status_code = 422
    code = "request.invalid"


class UnauthorizedError(TroveError):
    status_code = 401
    code = "auth.required"


class ForbiddenError(TroveError):
    status_code = 403
    code = "auth.forbidden"


class NotFoundError(TroveError):
    status_code = 404
    code = "item.not_found"


class ConflictError(TroveError):
    status_code = 409
    code = "item.conflict"


class RateLimitedError(TroveError):
    status_code = 429
    code = "auth.rate_limited"

    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProcessingError(Exception):
    """An error raised by a processing stage with a stable code."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class ProcessingCancelled(Exception):
    """Raised when the current stage observes a cancellation request."""
