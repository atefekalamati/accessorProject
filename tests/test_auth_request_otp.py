from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.time import utc_now
from app.db.models import OtpCode, User
from app.main import create_app
from app.modules.auth.otp import otp_hash_key, verify_otp_code
from app.modules.auth.sms import FakeSmsSender

pytestmark = pytest.mark.integration

URL = "/api/v1/auth/request-otp"
CLIENT_IP = "203.0.113.7"


def _unique_mobile() -> str:
    return f"+989{uuid4().int % 1_000_000_000:09d}"


@pytest_asyncio.fixture
async def clean_otp_codes(db_engine: AsyncEngine) -> None:
    # The test database is disposable; rate limits count every row in the table.
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(OtpCode))


@pytest.fixture
def otp_settings(settings: Settings, migrated_database: str) -> Settings:
    return settings.model_copy(update={"database_url": migrated_database})


@pytest.fixture
def sms_sender() -> FakeSmsSender:
    return FakeSmsSender()


async def _client(settings: Settings, sender: FakeSmsSender) -> AsyncIterator[AsyncClient]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        application.state.sms_sender = sender
        transport = ASGITransport(app=application, client=(CLIENT_IP, 50000))
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest_asyncio.fixture
async def otp_client(
    otp_settings: Settings, sms_sender: FakeSmsSender, clean_otp_codes: None
) -> AsyncIterator[AsyncClient]:
    async for client in _client(otp_settings, sms_sender):
        yield client


async def _codes(db_engine: AsyncEngine, mobile: str) -> list[OtpCode]:
    async with AsyncSession(db_engine) as session:
        statement = select(OtpCode).where(OtpCode.mobile == mobile).order_by(OtpCode.created_at)
        return list((await session.scalars(statement)).all())


async def _insert_codes(
    db_engine: AsyncEngine, count: int, *, age: timedelta, mobile: str | None = None, ip: Any
) -> None:
    created_at = utc_now() - age
    async with AsyncSession(db_engine) as session, session.begin():
        session.add_all(
            OtpCode(
                mobile=mobile or _unique_mobile(),
                code_hash="0" * 64,
                expires_at=created_at + timedelta(minutes=2),
                ip=ip,
                created_at=created_at,
            )
            for _ in range(count)
        )


def _assert_rate_limited(response: Any, low: int, high: int) -> None:
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "OTP_RATE_LIMITED"
    assert low <= int(response.headers["Retry-After"]) <= high


@pytest.mark.parametrize("raw", ["09121234567", "+989121234567", "989121234567"])
async def test_request_otp_normalizes_mobile_and_stores_hash(
    otp_client: AsyncClient,
    sms_sender: FakeSmsSender,
    otp_settings: Settings,
    db_engine: AsyncEngine,
    raw: str,
) -> None:
    response = await otp_client.post(URL, json={"mobile": raw})

    assert response.status_code == 200
    assert response.json() == {"expires_in_seconds": 120, "resend_after_seconds": 60}
    code = sms_sender.last_code("+989121234567")
    assert code is not None
    [stored] = await _codes(db_engine, "+989121234567")
    assert code not in stored.code_hash
    assert verify_otp_code(code, stored.mobile, otp_hash_key(otp_settings), stored.code_hash)
    assert stored.expires_at - stored.created_at == timedelta(seconds=120)
    assert str(stored.ip) == CLIENT_IP


async def test_request_otp_uses_random_code_when_mock_disabled(
    otp_settings: Settings, db_engine: AsyncEngine, clean_otp_codes: None
) -> None:
    sender = FakeSmsSender()
    settings = otp_settings.model_copy(update={"otp_mock_enabled": False})
    mobile = _unique_mobile()

    async for client in _client(settings, sender):
        response = await client.post(URL, json={"mobile": mobile})

    assert response.status_code == 200
    code = sender.last_code(mobile)
    assert code is not None and len(code) == 6 and code.isdigit()
    [stored] = await _codes(db_engine, mobile)
    assert verify_otp_code(code, mobile, otp_hash_key(settings), stored.code_hash)


@pytest.mark.parametrize(
    "body",
    [
        {"mobile": "0812345678"},
        {"mobile": "9121234567"},
        {"mobile": ""},
        {},
        {"mobile": "09121234567", "role": "super_admin"},
    ],
)
async def test_request_otp_rejects_invalid_body(
    otp_client: AsyncClient, sms_sender: FakeSmsSender, body: dict[str, str]
) -> None:
    response = await otp_client.post(URL, json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert sms_sender.sent == {}


async def test_request_otp_invalidates_previous_code(
    otp_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    mobile = _unique_mobile()
    assert (await otp_client.post(URL, json={"mobile": mobile})).status_code == 200
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(OtpCode)
            .where(OtpCode.mobile == mobile)
            .values(created_at=OtpCode.created_at - timedelta(seconds=61))
        )

    assert (await otp_client.post(URL, json={"mobile": mobile})).status_code == 200

    first, second = await _codes(db_engine, mobile)
    now = utc_now()
    assert first.expires_at <= now
    assert first.consumed_at is None
    assert second.expires_at > now


async def test_request_otp_resend_cooldown_returns_429(
    otp_client: AsyncClient, sms_sender: FakeSmsSender
) -> None:
    mobile = _unique_mobile()
    assert (await otp_client.post(URL, json={"mobile": mobile})).status_code == 200

    response = await otp_client.post(URL, json={"mobile": mobile})

    _assert_rate_limited(response, 55, 60)
    assert len(sms_sender.sent[mobile]) == 1


async def test_request_otp_per_mobile_limit_returns_429(
    otp_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    mobile = _unique_mobile()
    await _insert_codes(db_engine, 5, age=timedelta(minutes=30), mobile=mobile, ip=None)

    response = await otp_client.post(URL, json={"mobile": mobile})

    _assert_rate_limited(response, 1795, 1800)


async def test_request_otp_per_ip_limit_returns_429(
    otp_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    await _insert_codes(db_engine, 60, age=timedelta(minutes=10), ip=CLIENT_IP)

    response = await otp_client.post(URL, json={"mobile": _unique_mobile()})

    _assert_rate_limited(response, 2995, 3000)


async def test_request_otp_ignores_codes_outside_window(
    otp_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    mobile = _unique_mobile()
    await _insert_codes(db_engine, 5, age=timedelta(minutes=61), mobile=mobile, ip=CLIENT_IP)

    response = await otp_client.post(URL, json={"mobile": mobile})

    assert response.status_code == 200


async def test_request_otp_global_cap_returns_429_and_logs_warning(
    otp_settings: Settings,
    db_engine: AsyncEngine,
    clean_otp_codes: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sender = FakeSmsSender()
    settings = otp_settings.model_copy(update={"otp_max_global_per_hour": 3})
    await _insert_codes(db_engine, 3, age=timedelta(minutes=20), ip="198.51.100.1")

    async for client in _client(settings, sender):
        response = await client.post(URL, json={"mobile": _unique_mobile()})

    _assert_rate_limited(response, 2395, 2400)
    assert sender.sent == {}
    # create_app installs the JSON log handler, so assert on its stderr output.
    records = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line]
    assert any(
        record["message"] == "otp.global_cap_hit" and record["level"] == "WARNING"
        for record in records
    )


async def test_request_otp_response_does_not_reveal_user_existence(
    otp_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    existing = _unique_mobile()
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(User(phone=existing))

    known = await otp_client.post(URL, json={"mobile": existing})
    unknown = await otp_client.post(URL, json={"mobile": _unique_mobile()})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
