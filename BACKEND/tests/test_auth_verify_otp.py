from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from http.cookies import SimpleCookie
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.time import utc_now
from app.db.models import AuditLog, OtpCode, Role, User, UserRole, UserSession, UserStatus
from app.modules.auth.tokens import decode_access_token, hash_refresh_token

pytestmark = pytest.mark.integration

URL = "/api/v1/auth/verify-otp"
CODE = "123456"
WRONG_CODE = "654321"

IssueOtp = Callable[..., Awaitable[OtpCode]]


async def _verify(client: AsyncClient, mobile: str, code: str = CODE) -> Response:
    return await client.post(URL, json={"mobile": mobile, "code": code})


def refresh_cookie(response: Response) -> Any:
    [header] = response.headers.get_list("set-cookie")
    cookie = SimpleCookie()
    cookie.load(header)
    return cookie["refresh_token"]


async def _one(db_engine: AsyncEngine, statement: Any) -> Any:
    async with AsyncSession(db_engine) as session:
        return (await session.scalars(statement)).one_or_none()


async def _all(db_engine: AsyncEngine, statement: Any) -> list[Any]:
    async with AsyncSession(db_engine) as session:
        return list((await session.scalars(statement)).all())


async def _add_user(
    db_engine: AsyncEngine, mobile: str, *, status: str = UserStatus.ACTIVE, deleted: bool = False
) -> User:
    user = User(phone=mobile, status=status, deleted_at=utc_now() if deleted else None)
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return user


@pytest_asyncio.fixture(autouse=True)
async def _drop_users_of_mobile(new_mobile: str, db_engine: AsyncEngine) -> AsyncIterator[None]:
    # A soft-deleted twin of a phone breaks the downgrade of 20261006_0002 (full unique),
    # which the next test session runs; remove every account these tests create.
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone == new_mobile))


def _assert_otp_invalid(response: Response) -> None:
    assert response.status_code == 401
    error = response.json()["error"]
    assert error == {"code": "OTP_INVALID", "message": "Invalid or expired code", "details": []}
    assert "set-cookie" not in response.headers


async def test_first_login_creates_customer_and_issues_tokens(
    auth_client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    db_engine: AsyncEngine,
    settings: Settings,
) -> None:
    otp = await issue_otp(new_mobile)

    response = await auth_client.post(
        URL, json={"mobile": "0" + new_mobile[3:], "code": CODE}, headers={"User-Agent": "UA/1"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"access_token", "token_type", "expires_in_seconds"}
    assert body["token_type"] == "bearer"
    assert body["expires_in_seconds"] == settings.access_token_ttl_seconds
    assert response.headers["cache-control"] == "no-store"

    cookie = refresh_cookie(response)
    assert cookie["httponly"] is True
    assert cookie["secure"] is True
    assert cookie["samesite"].lower() == "strict"
    assert cookie["path"] == "/api/v1/auth"
    assert int(cookie["max-age"]) > 29 * 24 * 3600
    assert cookie.value not in response.text

    user = await _one(db_engine, select(User).where(User.phone == new_mobile))
    assert user.status == UserStatus.ACTIVE
    assert user.mobile_verified_at is not None
    role_names = await _all(
        db_engine,
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id),
    )
    assert role_names == ["customer"]

    [stored] = await _all(db_engine, select(UserSession).where(UserSession.user_id == user.id))
    assert stored.refresh_token_hash == hash_refresh_token(cookie.value)
    assert stored.revoked_at is None
    assert stored.user_agent == "UA/1"
    assert str(stored.ip) == "198.51.100.23"
    claims = decode_access_token(body["access_token"], settings)
    assert (claims.user_id, claims.session_id) == (user.id, stored.id)

    consumed = await _one(db_engine, select(OtpCode).where(OtpCode.id == otp.id))
    assert consumed.consumed_at is not None

    [audit] = await _all(
        db_engine,
        select(AuditLog).where(AuditLog.action == "auth.login", AuditLog.entity_id == user.id),
    )
    assert audit.actor_user_id == user.id
    assert audit.metadata_["diff"]["user_created"]["after"] is True
    assert audit.metadata_["diff"]["session_id"]["after"] == str(stored.id)


async def test_existing_user_logs_in_without_a_new_account(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    existing = await _add_user(db_engine, new_mobile)
    await issue_otp(new_mobile)

    response = await _verify(auth_client, new_mobile)

    assert response.status_code == 200
    users = await _all(db_engine, select(User).where(User.phone == new_mobile))
    assert [user.id for user in users] == [existing.id]
    assert users[0].mobile_verified_at is not None
    audit = await _one(db_engine, select(AuditLog).where(AuditLog.entity_id == existing.id))
    assert audit.metadata_["diff"]["user_created"]["after"] is False


async def test_wrong_code_counts_attempts_and_fifth_failure_invalidates(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    otp = await issue_otp(new_mobile)

    for attempt in range(1, 5):
        _assert_otp_invalid(await _verify(auth_client, new_mobile, WRONG_CODE))
        stored = await _one(db_engine, select(OtpCode).where(OtpCode.id == otp.id))
        assert stored.attempt_count == attempt
        assert stored.expires_at > utc_now()

    _assert_otp_invalid(await _verify(auth_client, new_mobile, WRONG_CODE))
    stored = await _one(db_engine, select(OtpCode).where(OtpCode.id == otp.id))
    assert stored.attempt_count == 5
    assert stored.expires_at <= utc_now()
    assert stored.consumed_at is None

    # The right code no longer works once the code is exhausted.
    _assert_otp_invalid(await _verify(auth_client, new_mobile))
    assert await _one(db_engine, select(User).where(User.phone == new_mobile)) is None


async def test_expired_code_is_rejected(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str
) -> None:
    await issue_otp(new_mobile, ttl=timedelta(seconds=-1))

    _assert_otp_invalid(await _verify(auth_client, new_mobile))


async def test_code_is_single_use(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str
) -> None:
    await issue_otp(new_mobile)

    assert (await _verify(auth_client, new_mobile)).status_code == 200
    _assert_otp_invalid(await _verify(auth_client, new_mobile))


async def test_unknown_mobile_gets_the_same_error(
    auth_client: AsyncClient, new_mobile: str
) -> None:
    _assert_otp_invalid(await _verify(auth_client, new_mobile))


async def test_concurrent_verifications_consume_the_code_once(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    await issue_otp(new_mobile)

    responses = await asyncio.gather(*(_verify(auth_client, new_mobile) for _ in range(4)))

    assert sorted(response.status_code for response in responses) == [200, 401, 401, 401]
    users = await _all(db_engine, select(User).where(User.phone == new_mobile))
    assert len(users) == 1
    sessions = await _all(db_engine, select(UserSession).where(UserSession.user_id == users[0].id))
    assert len(sessions) == 1


@pytest.mark.parametrize("status", [UserStatus.INACTIVE, UserStatus.BLOCKED])
async def test_disabled_account_gets_no_tokens(
    auth_client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    db_engine: AsyncEngine,
    status: str,
) -> None:
    user = await _add_user(db_engine, new_mobile, status=status)
    otp = await issue_otp(new_mobile)

    response = await _verify(auth_client, new_mobile)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert "set-cookie" not in response.headers
    assert await _all(db_engine, select(UserSession).where(UserSession.user_id == user.id)) == []
    stored = await _one(db_engine, select(OtpCode).where(OtpCode.id == otp.id))
    assert stored.consumed_at is not None


async def test_deleted_account_mobile_gets_a_new_customer_account(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    deleted = await _add_user(db_engine, new_mobile, deleted=True)
    await issue_otp(new_mobile)

    response = await _verify(auth_client, new_mobile)

    assert response.status_code == 200
    users = await _all(db_engine, select(User).where(User.phone == new_mobile))
    [new_user] = [user for user in users if user.id != deleted.id]
    assert new_user.deleted_at is None
    assert await _all(db_engine, select(UserSession).where(UserSession.user_id == deleted.id)) == []


async def test_deleted_blocked_account_mobile_is_rejected(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    await _add_user(db_engine, new_mobile, status=UserStatus.BLOCKED, deleted=True)
    await issue_otp(new_mobile)

    response = await _verify(auth_client, new_mobile)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    users = await _all(db_engine, select(User).where(User.phone == new_mobile))
    assert len(users) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"mobile": "09121234567", "code": "12345"},
        {"mobile": "09121234567", "code": "12345a"},
        {"mobile": "0812345678", "code": "123456"},
        {"mobile": "09121234567"},
        {"mobile": "09121234567", "code": "123456", "role": "super_admin"},
    ],
)
async def test_invalid_body_is_rejected(auth_client: AsyncClient, body: dict[str, Any]) -> None:
    response = await auth_client.post(URL, json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
