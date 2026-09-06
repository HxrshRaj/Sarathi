"""Typed error taxonomy and a single JSON error envelope for the whole API.

Every non-2xx response is:
    {"error": {"category", "message", "detail", "retryable", "correlation_id"}}
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import correlation_id_var, get_logger

log = get_logger("errors")


class ErrorCategory(StrEnum):
    USER = "user"
    AUTH = "auth"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    CONFLICT = "conflict"
    AGENT = "agent"
    TOOL = "tool"
    MODEL = "model"
    SANDBOX = "sandbox"
    LIMIT_EXCEEDED = "limit_exceeded"
    INFRA = "infra"


_STATUS_BY_CATEGORY = {
    ErrorCategory.USER: status.HTTP_400_BAD_REQUEST,
    ErrorCategory.AUTH: status.HTTP_401_UNAUTHORIZED,
    ErrorCategory.FORBIDDEN: status.HTTP_403_FORBIDDEN,
    ErrorCategory.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCategory.VALIDATION: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCategory.RATE_LIMIT: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCategory.CONFLICT: status.HTTP_409_CONFLICT,
    ErrorCategory.AGENT: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCategory.TOOL: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCategory.MODEL: status.HTTP_502_BAD_GATEWAY,
    ErrorCategory.SANDBOX: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCategory.LIMIT_EXCEEDED: status.HTTP_402_PAYMENT_REQUIRED,
    ErrorCategory.INFRA: status.HTTP_503_SERVICE_UNAVAILABLE,
}


class AppError(Exception):
    """Base application error. Carries everything the envelope needs."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        detail: dict[str, Any] | None = None,
        retryable: bool = False,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.detail = detail or {}
        self.retryable = retryable
        self.status_code = status_code or _STATUS_BY_CATEGORY[category]
        self.headers = headers or {}


# ── convenience subclasses ──────────────────────────────────────────────────
class NotFound(AppError):
    def __init__(self, what: str = "Resource") -> None:
        super().__init__(ErrorCategory.NOT_FOUND, f"{what} not found")


class Unauthorized(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(ErrorCategory.AUTH, message)


class Forbidden(AppError):
    def __init__(self, message: str = "Not permitted") -> None:
        super().__init__(ErrorCategory.FORBIDDEN, message)


class RateLimited(AppError):
    def __init__(self, retry_after_s: int) -> None:
        super().__init__(
            ErrorCategory.RATE_LIMIT,
            "Rate limit exceeded",
            retryable=True,
            detail={"retry_after_s": retry_after_s},
            headers={"Retry-After": str(retry_after_s)},
        )


class BadRequest(AppError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCategory.USER, message, detail=detail)


def _envelope(err: AppError) -> dict[str, Any]:
    return {
        "error": {
            "category": err.category.value,
            "message": err.message,
            "detail": err.detail,
            "retryable": err.retryable,
            "correlation_id": correlation_id_var.get(),
        }
    }


def install_error_handlers(app) -> None:  # noqa: ANN001
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            log.error("app_error", category=exc.category, message=exc.message, detail=exc.detail)
        else:
            log.info("app_error", category=exc.category, message=exc.message)
        return JSONResponse(_envelope(exc), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        err = AppError(
            ErrorCategory.VALIDATION,
            "Request validation failed",
            detail={"errors": exc.errors()},
        )
        return JSONResponse(_envelope(err), status_code=err.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        category = {
            401: ErrorCategory.AUTH,
            403: ErrorCategory.FORBIDDEN,
            404: ErrorCategory.NOT_FOUND,
            409: ErrorCategory.CONFLICT,
            429: ErrorCategory.RATE_LIMIT,
        }.get(exc.status_code, ErrorCategory.USER if exc.status_code < 500 else ErrorCategory.INFRA)
        err = AppError(category, str(exc.detail), status_code=exc.status_code)
        return JSONResponse(_envelope(err), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", error=str(exc))
        err = AppError(ErrorCategory.INFRA, "Internal server error", retryable=True)
        return JSONResponse(_envelope(err), status_code=500)
