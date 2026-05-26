"""Custom exception hierarchy for the ControlPanel Kitchen API client."""

from __future__ import annotations

import httpx


class APIError(Exception):
    """Base class for all API errors."""

    def __init__(self, message: str, *, response: httpx.Response | None = None) -> None:
        super().__init__(message)
        self.response = response
        self.status_code: int | None = response.status_code if response is not None else None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self!s}, status_code={self.status_code})"


class AuthenticationError(APIError):
    """Raised on 401 Unauthorized responses."""


class PermissionDeniedError(APIError):
    """Raised on 403 Forbidden responses."""


class NotFoundError(APIError):
    """Raised on 404 Not Found responses."""


class ValidationError(APIError):
    """Raised on 400 Bad Request / 422 Unprocessable Entity responses."""


class RateLimitError(APIError):
    """Raised on 429 Too Many Requests responses."""


class ServerError(APIError):
    """Raised on 5xx responses."""


_STATUS_MAP: dict[int, type[APIError]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    422: ValidationError,
    429: RateLimitError,
}


def raise_for_status(response: httpx.Response) -> None:
    """Raise the appropriate :class:`APIError` subclass for a non-2xx response."""
    if response.is_success:
        return

    exc_class = _STATUS_MAP.get(response.status_code)
    if exc_class is None:
        exc_class = ServerError if response.status_code >= 500 else APIError

    try:
        detail = response.json()
    except Exception:
        detail = response.text

    raise exc_class(str(detail), response=response)
