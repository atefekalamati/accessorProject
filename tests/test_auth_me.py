from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from http.cookies import SimpleCookie
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import AuditLog, OtpCode, User, UserRole, UserStatus
from app.db.seed import ROLE_PERMISSIONS, role_id

pytestmark = pytest.mark.integration

ME_URL = "/api/v1/auth/me"
PROFILE_URL = "/api/v1/users/me"

IssueOtp = Callable[..., Awaitable[OtpCode]]


@pytest_asyncio.fixture(autouse=True)
async def _drop_users_of_mobile(new_mobile: str, db_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone == new_mobile))


async def _login(client: AsyncClient, issue_otp: IssueOtp, mobile: str) -> Response:
    await issue_otp(mobile)
    response = await client.post(
        "/api/v1/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
    )
    assert response.status_code == 200
    return response


async def _access(client: AsyncClient, issue_otp: IssueOtp, mobile: str) -> dict[str, str]:
    response = await _login(client, issue_otp, mobile)
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _patch(client: AsyncClient, headers: dict[str, str], body: Any) -> Response:
    return await client.patch(PROFILE_URL, headers=headers, json=body)


async def _user(db_engine: AsyncEngine, mobile: str) -> User:
    async with AsyncSession(db_engine) as session:
        return (await session.scalars(select(User).where(User.phone == mobile))).one()


async def _profile_audits(db_engine: AsyncEngine, user_id: UUID) -> list[AuditLog]:
    async with AsyncSession(db_engine) as session:
        statement = (
            select(AuditLog)
            .where(AuditLog.action == "user.profile_updated", AuditLog.entity_id == user_id)
            .order_by(AuditLog.created_at)
        )
        return list((await session.scalars(statement)).all())


def _assert_validation_error(response: Response) -> None:
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- GET /auth/me ---------------------------------------------------------------------


async def test_me_returns_profile_roles_and_permissions(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)

    response = await auth_client.get(ME_URL, headers=headers)

    assert response.status_code == 200
    user = await _user(db_engine, new_mobile)
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["mobile"] == new_mobile
    assert "phone" not in body
    assert body["first_name"] is None and body["last_name"] is None and body["email"] is None
    assert body["status"] == "active"
    assert body["mobile_verified_at"] is not None
    assert body["roles"] == ["customer"]
    assert body["permissions"] == []


async def test_me_reads_roles_from_the_database(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)
    user = await _user(db_engine, new_mobile)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(UserRole).where(UserRole.user_id == user.id))
        session.add(UserRole(user_id=user.id, role_id=role_id("support")))

    body = (await auth_client.get(ME_URL, headers=headers)).json()

    assert body["roles"] == ["support"]
    assert body["permissions"] == sorted(ROLE_PERMISSIONS["support"])


async def test_me_without_token_is_unauthorized(auth_client: AsyncClient) -> None:
    response = await auth_client.get(ME_URL)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_me_of_a_blocked_user_is_forbidden(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(User).where(User.phone == new_mobile).values(status=UserStatus.BLOCKED)
        )

    assert (await auth_client.get(ME_URL, headers=headers)).status_code == 403
    assert (await _patch(auth_client, headers, {"first_name": "Ali"})).status_code == 403


# --- PATCH /users/me ------------------------------------------------------------------


async def test_patch_updates_trims_names_and_lowercases_email(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)

    response = await _patch(
        auth_client,
        headers,
        {"first_name": "  Ali  ", "last_name": "\tRezaei\n", "email": "  Ali.Rezaei@Example.COM "},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["first_name"], body["last_name"]) == ("Ali", "Rezaei")
    assert body["email"] == "ali.rezaei@example.com"
    assert body["roles"] == ["customer"]
    user = await _user(db_engine, new_mobile)
    assert (user.first_name, user.last_name, user.email) == (
        "Ali",
        "Rezaei",
        "ali.rezaei@example.com",
    )


async def test_patch_changes_only_sent_fields_and_null_clears_email(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)
    await _patch(
        auth_client, headers, {"first_name": "Ali", "last_name": "Rezaei", "email": "a@b.co"}
    )

    response = await _patch(auth_client, headers, {"email": None})

    assert response.status_code == 200
    user = await _user(db_engine, new_mobile)
    assert (user.first_name, user.last_name, user.email) == ("Ali", "Rezaei", None)


async def test_empty_patch_changes_nothing_and_is_not_audited(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)

    response = await _patch(auth_client, headers, {})

    assert response.status_code == 200
    assert await _profile_audits(db_engine, (await _user(db_engine, new_mobile)).id) == []


@pytest.mark.parametrize(
    "body",
    [
        {"mobile": "+989121234567"},
        {"phone": "+989121234567"},
        {"role": "super_admin"},
        {"roles": ["super_admin"]},
        {"status": "active"},
        {"mobile_verified_at": "2026-01-01T00:00:00Z"},
        {"verified": True},
        {"id": "00000000-0000-0000-0000-000000000000"},
        {"first_name": "Ali", "role": "admin"},
    ],
)
async def test_patch_rejects_system_fields(
    auth_client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    db_engine: AsyncEngine,
    body: dict[str, Any],
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)
    before = await _user(db_engine, new_mobile)

    response = await _patch(auth_client, headers, body)

    _assert_validation_error(response)
    after = await _user(db_engine, new_mobile)
    assert (after.phone, after.status, after.mobile_verified_at, after.first_name) == (
        before.phone,
        before.status,
        before.mobile_verified_at,
        before.first_name,
    )
    roles = (await auth_client.get(ME_URL, headers=headers)).json()["roles"]
    assert roles == ["customer"]


@pytest.mark.parametrize(
    "body",
    [
        {"first_name": ""},
        {"first_name": "   "},
        {"last_name": "\t\n"},
        {"first_name": None},
        {"last_name": None},
        {"first_name": "a" * 101},
        {"last_name": 42},
        {"email": ""},
        {"email": "not-an-email"},
        {"email": "a@b"},
        {"email": "a@@b.com"},
        {"email": f"{'a' * 64}@{'b' * 186}.com"},
        {"email": 123},
    ],
)
async def test_patch_rejects_invalid_values(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, body: dict[str, Any]
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)

    _assert_validation_error(await _patch(auth_client, headers, body))


async def test_patch_accepts_names_at_the_length_limit(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)

    response = await _patch(auth_client, headers, {"first_name": "ع" * 100})

    assert response.status_code == 200
    assert response.json()["first_name"] == "ع" * 100


async def test_patch_without_token_is_unauthorized(auth_client: AsyncClient) -> None:
    response = await _patch(auth_client, {}, {"first_name": "Ali"})

    assert response.status_code == 401


async def test_profile_update_is_audited_with_a_redacted_diff(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)
    await _patch(auth_client, headers, {"first_name": "Ali", "email": "ali.rezaei@example.com"})

    # Same first name again: only the email change is recorded.
    await _patch(auth_client, headers, {"first_name": "Ali", "email": "zahra@example.org"})

    user = await _user(db_engine, new_mobile)
    first, second = await _profile_audits(db_engine, user.id)
    assert first.actor_user_id == user.id
    assert first.metadata_["diff"] == {
        "email": {"before": None, "after": "a***i@example.com", "changed": True},
        "first_name": {"before": None, "after": "Ali", "changed": True},
    }
    assert second.metadata_["diff"] == {
        "email": {"before": "a***i@example.com", "after": "z***a@example.org", "changed": True},
    }
    assert "ali.rezaei" not in str(first.metadata_)


async def test_email_change_is_audited_even_when_masks_collide(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    headers = await _access(auth_client, issue_otp, new_mobile)
    await _patch(auth_client, headers, {"email": "ali@example.com"})

    await _patch(auth_client, headers, {"email": "amir.ali@example.com"})

    user = await _user(db_engine, new_mobile)
    _, second = await _profile_audits(db_engine, user.id)
    assert second.metadata_["diff"] == {
        "email": {"before": "a***i@example.com", "after": "a***i@example.com", "changed": True},
    }
    assert "amir" not in str(second.metadata_)


# --- Cache-Control --------------------------------------------------------------------


async def test_auth_and_profile_responses_are_not_cacheable(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str
) -> None:
    login = await _login(auth_client, issue_otp, new_mobile)
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(login.headers["set-cookie"])
    refresh_token = cookie["refresh_token"].value
    auth_client.cookies.clear()

    refreshed = await auth_client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={refresh_token}"}
    )
    cookie.load(refreshed.headers["set-cookie"])
    headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}
    me = await auth_client.get(ME_URL, headers=headers)
    patched = await _patch(auth_client, headers, {"first_name": "Ali"})
    auth_client.cookies.clear()
    logout = await auth_client.post(
        "/api/v1/auth/logout",
        headers={"Cookie": f"refresh_token={cookie['refresh_token'].value}"},
    )

    for response in (login, refreshed, me, patched, logout):
        assert response.status_code in (200, 204), response.request.url
        assert response.headers["cache-control"] == "no-store", response.request.url
