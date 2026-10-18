from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.middleware import REQUEST_ID_HEADER

logger = logging.getLogger("app.error")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[Any] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str


class ErrorCode(StrEnum):
    """Stable machine-readable error codes (PRD "key errors", ADR-008, ADR-011)."""

    # 400 — request validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    # 401 — authentication
    UNAUTHORIZED = "UNAUTHORIZED"
    OTP_INVALID = "OTP_INVALID"
    OTP_EXPIRED = "OTP_EXPIRED"
    MOBILE_NOT_VERIFIED = "MOBILE_NOT_VERIFIED"
    # 403 — authorization
    FORBIDDEN = "FORBIDDEN"
    # 404 — missing resource
    NOT_FOUND = "NOT_FOUND"
    # 409 — conflicting state
    CONFLICT = "CONFLICT"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    PRICE_CHANGED = "PRICE_CHANGED"
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
    RESERVATION_ALREADY_CONSUMED = "RESERVATION_ALREADY_CONSUMED"
    DUPLICATE_SLUG = "DUPLICATE_SLUG"
    MOBILE_ALREADY_REGISTERED = "MOBILE_ALREADY_REGISTERED"
    ORDER_PENDING = "ORDER_PENDING"
    # 422 — business rule violation
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    DISCOUNT_NOT_APPLICABLE = "DISCOUNT_NOT_APPLICABLE"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    # 429 — rate limiting
    RATE_LIMITED = "RATE_LIMITED"
    OTP_RATE_LIMITED = "OTP_RATE_LIMITED"
    # 5xx — server side
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"


ERROR_STATUS: Mapping[ErrorCode, int] = MappingProxyType(
    {
        ErrorCode.VALIDATION_ERROR: 400,
        ErrorCode.UNAUTHORIZED: 401,
        ErrorCode.OTP_INVALID: 401,
        ErrorCode.OTP_EXPIRED: 401,
        ErrorCode.MOBILE_NOT_VERIFIED: 401,
        ErrorCode.FORBIDDEN: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.CONFLICT: 409,
        ErrorCode.INSUFFICIENT_STOCK: 409,
        ErrorCode.PRICE_CHANGED: 409,
        ErrorCode.RESERVATION_EXPIRED: 409,
        ErrorCode.RESERVATION_ALREADY_CONSUMED: 409,
        ErrorCode.DUPLICATE_SLUG: 409,
        ErrorCode.MOBILE_ALREADY_REGISTERED: 409,
        ErrorCode.ORDER_PENDING: 409,
        ErrorCode.BUSINESS_RULE_VIOLATION: 422,
        ErrorCode.INVALID_STATE_TRANSITION: 422,
        ErrorCode.DISCOUNT_NOT_APPLICABLE: 422,
        ErrorCode.IDEMPOTENCY_KEY_REUSED: 422,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.OTP_RATE_LIMITED: 429,
        ErrorCode.INTERNAL_SERVER_ERROR: 500,
        ErrorCode.DATABASE_UNAVAILABLE: 503,
    }
)
"""Single source of truth: every ErrorCode maps to exactly one HTTP status."""


class AppError(Exception):
    """Base application error; the HTTP status always comes from ``ERROR_STATUS``.

    Subclasses pin ``expected_status``; constructing one with a code mapped to a
    different status raises ``ValueError`` (a programming error, not a client error).
    """

    expected_status: ClassVar[int | None] = None
    default_code: ClassVar[ErrorCode | None] = None

    def __init__(
        self,
        *,
        code: ErrorCode | None = None,
        message: str,
        status_code: int | None = None,
        details: list[Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        resolved = code or self.default_code
        if resolved is None:
            raise ValueError(f"{type(self).__name__} requires an error code")
        status = ERROR_STATUS[resolved]
        for claimed in (status_code, self.expected_status):
            if claimed is not None and claimed != status:
                raise ValueError(
                    f"{type(self).__name__}: {resolved} maps to {status}, not {claimed}"
                )
        self.code = resolved
        self.message = message
        self.status_code = status
        self.details = details or []
        self.headers = headers or {}
        super().__init__(message)


class BadRequestError(AppError):
    expected_status = 400
    default_code = ErrorCode.VALIDATION_ERROR


class UnauthorizedError(AppError):
    expected_status = 401
    default_code = ErrorCode.UNAUTHORIZED


class ForbiddenError(AppError):
    expected_status = 403
    default_code = ErrorCode.FORBIDDEN


class NotFoundError(AppError):
    expected_status = 404
    default_code = ErrorCode.NOT_FOUND


class ConflictError(AppError):
    expected_status = 409
    default_code = ErrorCode.CONFLICT


class BusinessRuleError(AppError):
    expected_status = 422
    default_code = ErrorCode.BUSINESS_RULE_VIOLATION


class RateLimitedError(AppError):
    expected_status = 429
    default_code = ErrorCode.RATE_LIMITED

    def __init__(
        self,
        *,
        retry_after: int,
        code: ErrorCode | None = None,
        message: str = "Too many requests",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            details=details,
            headers={"Retry-After": str(retry_after)},
        )
        self.retry_after = retry_after


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", uuid4()))


def _error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[Any],
    headers: dict[str, str] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "details": details},
            "request_id": request_id or _request_id(request),
        },
        headers=headers,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request=request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        headers=exc.headers or None,
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return _error_response(
        request=request,
        status_code=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        message=detail,
        details=[],
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return _error_response(
        request=request,
        status_code=ERROR_STATUS[ErrorCode.VALIDATION_ERROR],
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details=details,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Exceptions bypass RequestContextMiddleware, so echo the request id here.
    request_id = _request_id(request)
    logger.exception("unhandled.exception", extra={"request_id": request_id}, exc_info=exc)
    return _error_response(
        request=request,
        status_code=ERROR_STATUS[ErrorCode.INTERNAL_SERVER_ERROR],
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred",
        details=[],
        headers={REQUEST_ID_HEADER: request_id},
        request_id=request_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
