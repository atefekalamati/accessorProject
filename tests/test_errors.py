from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import (
    ERROR_STATUS,
    AppError,
    BusinessRuleError,
    ConflictError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
)
from app.main import create_app
from app.shared.money import Toman

SUBCLASSES: list[type[AppError]] = [
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    ConflictError,
    BusinessRuleError,
    RateLimitedError,
]

SECRET = "db-password-leaked-in-exception"


class AmountIn(BaseModel):
    amount: Toman


def _raise(exc: Exception) -> None:
    raise exc


def _build_error_app(settings: Settings) -> FastAPI:
    application = create_app(settings)

    @application.post("/_test/amount")
    async def post_amount(payload: AmountIn) -> dict[str, int]:
        return {"amount": payload.amount}

    @application.get("/_test/reservation-expired")
    async def reservation_expired() -> None:
        _raise(ConflictError(code=ErrorCode.RESERVATION_EXPIRED, message="Reservation expired"))

    @application.get("/_test/rate-limited")
    async def rate_limited() -> None:
        _raise(RateLimitedError(code=ErrorCode.OTP_RATE_LIMITED, retry_after=60))

    @application.get("/_test/boom")
    async def boom() -> None:
        _raise(RuntimeError(SECRET))

    return application


@pytest_asyncio.fixture
async def error_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=_build_error_app(settings), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


def _assert_error_shape(body: dict[str, Any], code: str) -> None:
    assert set(body) == {"error", "request_id"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert body["request_id"]


# --- catalog / mapping ---------------------------------------------------------------


def test_every_error_code_has_a_status() -> None:
    assert set(ERROR_STATUS) == set(ErrorCode)
    assert all(400 <= status <= 599 for status in ERROR_STATUS.values())


@pytest.mark.parametrize("cls", SUBCLASSES)
def test_subclass_default_code_matches_expected_status(cls: type[AppError]) -> None:
    assert cls.default_code is not None
    assert ERROR_STATUS[cls.default_code] == cls.expected_status


@pytest.mark.parametrize("cls", SUBCLASSES)
@pytest.mark.parametrize("code", list(ErrorCode))
def test_subclass_cannot_contradict_mapping(cls: type[AppError], code: ErrorCode) -> None:
    kwargs: dict[str, Any] = {"code": code, "message": "m"}
    if cls is RateLimitedError:
        kwargs["retry_after"] = 1
    if ERROR_STATUS[code] == cls.expected_status:
        assert cls(**kwargs).status_code == ERROR_STATUS[code]
    else:
        with pytest.raises(ValueError):
            cls(**kwargs)


def test_base_error_derives_status_and_rejects_contradiction() -> None:
    assert AppError(code=ErrorCode.DATABASE_UNAVAILABLE, message="m").status_code == 503
    assert AppError(code=ErrorCode.NOT_FOUND, message="m", status_code=404).status_code == 404
    with pytest.raises(ValueError):
        AppError(code=ErrorCode.NOT_FOUND, message="m", status_code=400)
    with pytest.raises(ValueError):
        AppError(message="no code")


# --- HTTP behaviour --------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": 1500.0},
        {"amount": 1500.5},
        {"amount": "1500"},
        {"amount": True},
        {"amount": -1},
        {},
    ],
)
async def test_invalid_input_returns_400(error_client: AsyncClient, payload: Any) -> None:
    response = await error_client.post("/_test/amount", json=payload)

    assert response.status_code == 400
    body = response.json()
    _assert_error_shape(body, "VALIDATION_ERROR")
    assert body["error"]["details"][0]["field"] == "body.amount"


async def test_valid_toman_amount_is_accepted(error_client: AsyncClient) -> None:
    response = await error_client.post("/_test/amount", json={"amount": 1500})

    assert response.status_code == 200
    assert response.json() == {"amount": 1500}


async def test_reservation_expired_returns_409(error_client: AsyncClient) -> None:
    response = await error_client.get("/_test/reservation-expired")

    assert response.status_code == 409
    _assert_error_shape(response.json(), "RESERVATION_EXPIRED")


async def test_rate_limited_sets_retry_after(error_client: AsyncClient) -> None:
    response = await error_client.get("/_test/rate-limited")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    _assert_error_shape(response.json(), "OTP_RATE_LIMITED")


async def test_unhandled_exception_returns_generic_500(
    error_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    error_logger = logging.getLogger("app.error")
    error_logger.addHandler(caplog.handler)
    try:
        response = await error_client.get("/_test/boom")
    finally:
        error_logger.removeHandler(caplog.handler)

    assert response.status_code == 500
    body = response.json()
    _assert_error_shape(body, "INTERNAL_SERVER_ERROR")
    assert body["error"]["message"] == "An unexpected error occurred"
    assert body["error"]["details"] == []
    assert SECRET not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text

    records = [r for r in caplog.records if r.name == "app.error"]
    assert records
    assert records[0].exc_info is not None
    assert SECRET in str(records[0].exc_info[1])
    assert getattr(records[0], "request_id", None) == body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_openapi_documents_error_statuses(settings: Settings) -> None:
    schema = create_app(settings).openapi()
    responses = schema["paths"]["/health"]["get"]["responses"]

    for status in ("400", "401", "403", "404", "409", "422", "429", "500"):
        assert responses[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
    assert responses["400"]["description"] == "Validation error"
    assert responses["422"]["description"] == "Business rule violation"
