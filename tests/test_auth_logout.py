from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from http.cookies import Morsel, SimpleCookie

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import AuditLog, OtpCode, User, UserSession
from app.modules.auth.tokens import hash_refresh_token

pytestmark = pytest.mark.integration

URL = "/api/v1/auth/logout"

IssueOtp = Callable[..., Awaitable[OtpCode]]


@pytest_asyncio.fixture(autouse=True)
async def _drop_users_of_mobile(new_mobile: str, db_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone == new_mobile))


def _cookie(response: Response) -> Morsel[str]:
    [header] = response.headers.get_list("set-cookie")
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(header)
    return cookie["refresh_token"]


async def _login(client: AsyncClient, issue_otp: IssueOtp, mobile: str) -> str:
    await issue_otp(mobile)
    response = await client.post(
        "/api/v1/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
    )
    assert response.status_code == 200
    return _cookie(response).value


async def _post(client: AsyncClient, url: str, token: str | None) -> Response:
    # The Secure cookie is never replayed over http://testserver; send it explicitly.
    client.cookies.clear()
    headers = {"Cookie": f"refresh_token={token}"} if token is not None else {}
    return await client.post(url, headers=headers)


async def _session_of(db_engine: AsyncEngine, token: str) -> UserSession:
    async with AsyncSession(db_engine) as session:
        statement = select(UserSession).where(
            UserSession.refresh_token_hash == hash_refresh_token(token)
        )
        return (await session.scalars(statement)).one()


async def _logout_audits(db_engine: AsyncEngine, user_id: object) -> list[AuditLog]:
    async with AsyncSession(db_engine) as session:
        statement = select(AuditLog).where(
            AuditLog.action == "auth.logout", AuditLog.entity_id == user_id
        )
        return list((await session.scalars(statement)).all())


def _assert_cookie_cleared(response: Response) -> None:
    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"
    cookie = _cookie(response)
    assert cookie.value == ""
    assert cookie["max-age"] == "0"
    assert cookie["path"] == "/api/v1/auth"
    assert cookie["secure"] is True
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "strict"


async def test_logout_revokes_the_session_and_clears_the_cookie(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    token = await _login(auth_client, issue_otp, new_mobile)

    response = await _post(auth_client, URL, token)

    _assert_cookie_cleared(response)
    user_session = await _session_of(db_engine, token)
    assert user_session.revoked_at is not None
    [audit] = await _logout_audits(db_engine, user_session.user_id)
    assert audit.actor_user_id == user_session.user_id
    assert audit.metadata_["diff"]["session_id"]["after"] == str(user_session.id)


async def test_refresh_after_logout_is_unauthorized(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str
) -> None:
    token = await _login(auth_client, issue_otp, new_mobile)
    await _post(auth_client, URL, token)

    response = await _post(auth_client, "/api/v1/auth/refresh", token)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_repeated_logout_is_idempotent_and_audited_once(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    token = await _login(auth_client, issue_otp, new_mobile)
    await _post(auth_client, URL, token)

    response = await _post(auth_client, URL, token)

    _assert_cookie_cleared(response)
    user_session = await _session_of(db_engine, token)
    assert len(await _logout_audits(db_engine, user_session.user_id)) == 1
    # A revoked token at logout is not reuse: no refresh_reuse audit is written.
    async with AsyncSession(db_engine) as session:
        reuse = await session.scalar(
            select(func.count()).where(
                AuditLog.action == "auth.refresh_reuse",
                AuditLog.entity_id == user_session.user_id,
            )
        )
    assert reuse == 0


@pytest.mark.parametrize("token", [None, "", "unknown-token"])
async def test_logout_without_a_valid_cookie_still_succeeds(
    auth_client: AsyncClient, token: str | None
) -> None:
    response = await _post(auth_client, URL, token)

    _assert_cookie_cleared(response)


async def test_logout_keeps_sessions_of_other_devices(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    first = await _login(auth_client, issue_otp, new_mobile)
    second = await _login(auth_client, issue_otp, new_mobile)

    await _post(auth_client, URL, first)

    assert (await _session_of(db_engine, first)).revoked_at is not None
    assert (await _session_of(db_engine, second)).revoked_at is None
    refreshed = await _post(auth_client, "/api/v1/auth/refresh", second)
    assert refreshed.status_code == 200


async def test_logout_after_rotation_revokes_the_current_session(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    original = await _login(auth_client, issue_otp, new_mobile)
    rotated = _cookie(await _post(auth_client, "/api/v1/auth/refresh", original)).value

    response = await _post(auth_client, URL, rotated)

    _assert_cookie_cleared(response)
    assert (await _session_of(db_engine, rotated)).revoked_at is not None
    assert (await _post(auth_client, "/api/v1/auth/refresh", rotated)).status_code == 401
