from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from http.cookies import Morsel, SimpleCookie
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.time import utc_now
from app.db.models import AuditLog, OtpCode, User, UserSession, UserStatus
from app.modules.auth.tokens import decode_access_token, hash_refresh_token

pytestmark = pytest.mark.integration

URL = "/api/v1/auth/refresh"

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


async def _refresh(client: AsyncClient, token: str | None, **kwargs: Any) -> Response:
    # The Secure cookie is never replayed over http://testserver; send it explicitly.
    client.cookies.clear()
    headers = {"Cookie": f"refresh_token={token}"} if token is not None else {}
    return await client.post(URL, headers=headers, **kwargs)


async def _session_of(db_engine: AsyncEngine, token: str) -> UserSession:
    async with AsyncSession(db_engine) as session:
        statement = select(UserSession).where(
            UserSession.refresh_token_hash == hash_refresh_token(token)
        )
        return (await session.scalars(statement)).one()


async def _family(db_engine: AsyncEngine, family_id: Any) -> list[UserSession]:
    async with AsyncSession(db_engine) as session:
        statement = select(UserSession).where(UserSession.family_id == family_id)
        return list((await session.scalars(statement)).all())


def _assert_unauthorized(response: Response) -> None:
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert "set-cookie" not in response.headers


async def test_refresh_rotates_the_token_within_its_family(
    auth_client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    db_engine: AsyncEngine,
    settings: Settings,
) -> None:
    first = await _login(auth_client, issue_otp, new_mobile)

    response = await _refresh(auth_client, first)

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"access_token", "token_type", "expires_in_seconds"}
    cookie = _cookie(response)
    assert cookie["httponly"] is True and cookie["secure"] is True
    assert cookie["samesite"].lower() == "strict"
    assert cookie["path"] == "/api/v1/auth"
    second = cookie.value
    assert second != first and second not in response.text

    old, new = await _session_of(db_engine, first), await _session_of(db_engine, second)
    assert old.revoked_at is not None
    assert new.revoked_at is None
    assert new.family_id == old.family_id and new.user_id == old.user_id
    assert new.expires_at > old.expires_at
    claims = decode_access_token(body["access_token"], settings)
    assert (claims.user_id, claims.session_id) == (new.user_id, new.id)

    # The rotated token keeps working; each use rotates again.
    assert (await _refresh(auth_client, second)).status_code == 200


@pytest.mark.parametrize("token", [None, "", "unknown-token"])
async def test_missing_or_unknown_cookie_is_rejected(
    auth_client: AsyncClient, token: str | None
) -> None:
    _assert_unauthorized(await _refresh(auth_client, token))


async def test_refresh_token_outside_the_cookie_is_ignored(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    token = await _login(auth_client, issue_otp, new_mobile)
    auth_client.cookies.clear()

    _assert_unauthorized(await auth_client.post(URL, json={"refresh_token": token}))
    _assert_unauthorized(await auth_client.post(URL, headers={"Authorization": f"Bearer {token}"}))
    assert (await _session_of(db_engine, token)).revoked_at is None


async def test_reuse_of_a_rotated_token_revokes_the_family(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    first = await _login(auth_client, issue_otp, new_mobile)
    other_login = await _login(auth_client, issue_otp, new_mobile)
    second = _cookie(await _refresh(auth_client, first)).value

    _assert_unauthorized(await _refresh(auth_client, first))

    family = await _family(db_engine, (await _session_of(db_engine, first)).family_id)
    assert len(family) == 2
    assert all(session.revoked_at is not None for session in family)
    _assert_unauthorized(await _refresh(auth_client, second))
    # Another login (family) of the same user is untouched.
    assert (await _refresh(auth_client, other_login)).status_code == 200

    async with AsyncSession(db_engine) as session:
        statement = select(AuditLog).where(
            AuditLog.action == "auth.refresh_reuse", AuditLog.entity_id == family[0].user_id
        )
        audits = list((await session.scalars(statement)).all())
    assert len(audits) == 2
    first_audit = min(audits, key=lambda audit: audit.created_at)
    diff = first_audit.metadata_["diff"]
    assert diff["family_id"]["after"] == str(family[0].family_id)
    assert diff["revoked_sessions"]["after"] == 1
    assert first_audit.actor_user_id is None


async def test_expired_session_is_rejected(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    token = await _login(auth_client, issue_otp, new_mobile)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(UserSession)
            .where(UserSession.refresh_token_hash == hash_refresh_token(token))
            .values(expires_at=utc_now() - timedelta(seconds=1))
        )

    _assert_unauthorized(await _refresh(auth_client, token))


@pytest.mark.parametrize(
    "values",
    [
        {"status": UserStatus.INACTIVE},
        {"status": UserStatus.BLOCKED},
        {"deleted_at": utc_now()},
    ],
)
async def test_disabled_or_deleted_user_cannot_refresh(
    auth_client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    db_engine: AsyncEngine,
    values: dict[str, Any],
) -> None:
    token = await _login(auth_client, issue_otp, new_mobile)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(update(User).where(User.phone == new_mobile).values(**values))

    _assert_unauthorized(await _refresh(auth_client, token))

    stored = await _session_of(db_engine, token)
    assert stored.revoked_at is not None
    assert len(await _family(db_engine, stored.family_id)) == 1


async def test_concurrent_refreshes_with_one_token_revoke_the_family(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    token = await _login(auth_client, issue_otp, new_mobile)
    auth_client.cookies.clear()
    headers = {"Cookie": f"refresh_token={token}"}

    responses = await asyncio.gather(*(auth_client.post(URL, headers=headers) for _ in range(2)))

    assert sorted(response.status_code for response in responses) == [200, 401]
    # Strict reuse detection (no grace period, ADR-017): the winner's new token dies too.
    family = await _family(db_engine, (await _session_of(db_engine, token)).family_id)
    assert len(family) == 2
    assert all(session.revoked_at is not None for session in family)
