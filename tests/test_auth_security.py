"""Consolidated auth security suite (AUTH-12).

Every test names the rule it enforces as ``<ADR>.<rule>`` in its docstring. Rules already
covered elsewhere are mapped in tasks/phase-02/AUTH-12-auth-security-tests.md; this file
holds the cross-cutting checks that no single endpoint suite owns.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from http.cookies import SimpleCookie
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import cast, delete, func, select
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.db.models import AuditLog, OtpCode, User, UserRole, UserSession
from app.db.seed import role_id
from app.main import create_app

pytestmark = pytest.mark.integration

IssueOtp = Callable[..., Awaitable[OtpCode]]
AUTH_PREFIX = "/api/v1/auth"
MOCK_CODE = "123456"


@pytest_asyncio.fixture(autouse=True)
async def _drop_users_of_mobile(new_mobile: str, db_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone == new_mobile))


def _refresh_cookie(response: Response) -> SimpleCookie:
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie


def _assert_refresh_cookie(response: Response) -> str:
    """The refresh cookie's attributes per ADR-017; returns its value."""
    morsel = _refresh_cookie(response)["refresh_token"]
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"].lower() == "strict"
    assert morsel["path"] == AUTH_PREFIX
    return morsel.value


async def _user_id(db_engine: AsyncEngine, mobile: str) -> UUID:
    async with AsyncSession(db_engine) as session:
        user_id: UUID = (await session.scalars(select(User.id).where(User.phone == mobile))).one()
        return user_id


async def test_tokens_travel_only_where_allowed(auth_client: AsyncClient, new_mobile: str) -> None:
    """ADR-017.cookie, ADR-012: refresh only in an HttpOnly/Secure/Strict cookie scoped to
    /api/v1/auth; never in any response body; token responses are not cacheable."""
    requested = await auth_client.post(f"{AUTH_PREFIX}/request-otp", json={"mobile": new_mobile})
    assert requested.status_code == 200
    assert "set-cookie" not in requested.headers

    verified = await auth_client.post(
        f"{AUTH_PREFIX}/verify-otp", json={"mobile": new_mobile, "code": MOCK_CODE}
    )
    assert verified.status_code == 200
    first = _assert_refresh_cookie(verified)
    assert first not in verified.text
    assert verified.headers["cache-control"] == "no-store"
    access = verified.json()["access_token"]

    auth_client.cookies.set("refresh_token", first, path=AUTH_PREFIX)
    refreshed = await auth_client.post(f"{AUTH_PREFIX}/refresh")
    assert refreshed.status_code == 200
    second = _assert_refresh_cookie(refreshed)
    assert second != first
    assert first not in refreshed.text and second not in refreshed.text
    assert refreshed.headers["cache-control"] == "no-store"

    headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}
    me = await auth_client.get(f"{AUTH_PREFIX}/me", headers=headers)
    assert me.status_code == 200
    assert second not in me.text and access not in me.text

    auth_client.cookies.set("refresh_token", second, path=AUTH_PREFIX)
    logout = await auth_client.post(f"{AUTH_PREFIX}/logout")
    auth_client.cookies.clear()
    assert logout.status_code == 204
    assert second not in logout.text
    cleared = _refresh_cookie(logout)["refresh_token"]
    assert cleared.value == ""
    assert cleared["path"] == AUTH_PREFIX


async def test_no_plaintext_otp_or_refresh_token_in_the_database(
    auth_client: AsyncClient, new_mobile: str, db_engine: AsyncEngine
) -> None:
    """ADR-016/ADR-017.hashing: otp_codes, sessions and audit_logs never hold the raw OTP
    or refresh token; checked directly on the tables, every column cast to text."""
    await auth_client.post(f"{AUTH_PREFIX}/request-otp", json={"mobile": new_mobile})
    verified = await auth_client.post(
        f"{AUTH_PREFIX}/verify-otp", json={"mobile": new_mobile, "code": MOCK_CODE}
    )
    refresh_token = _refresh_cookie(verified)["refresh_token"].value
    auth_client.cookies.set("refresh_token", refresh_token, path=AUTH_PREFIX)
    rotated = await auth_client.post(f"{AUTH_PREFIX}/refresh")
    auth_client.cookies.clear()
    rotated_token = _refresh_cookie(rotated)["refresh_token"].value
    user_id = await _user_id(db_engine, new_mobile)

    async with AsyncSession(db_engine) as session:
        otp_rows = (
            await session.execute(select(OtpCode.__table__).where(OtpCode.mobile == new_mobile))
        ).all()
        session_rows = (
            await session.execute(
                select(UserSession.__table__).where(UserSession.user_id == user_id)
            )
        ).all()
        audit_rows = (
            await session.scalars(
                select(cast(AuditLog.metadata_, TEXT)).where(AuditLog.entity_id == user_id)
            )
        ).all()

    assert otp_rows and len(session_rows) == 2 and audit_rows
    stored = [str(value) for row in (*otp_rows, *session_rows) for value in row] + list(audit_rows)
    for secret in (MOCK_CODE, refresh_token, rotated_token):
        assert not any(secret in value for value in stored), secret


_PATH_PARAM = re.compile(r"\{[a-z_]+\}")


def _admin_endpoints(settings: Settings) -> list[tuple[str, str]]:
    """``(method, path)`` of every /admin operation, with path parameters filled in.

    Read from the OpenAPI schema, so routes in included routers are listed as well.
    """
    paths = create_app(settings).openapi()["paths"]
    return sorted(
        (method.upper(), _PATH_PARAM.sub("00000000-0000-0000-0000-000000000000", path))
        for path, operations in paths.items()
        if path.startswith("/api/v1/admin")
        for method in operations
    )


async def _login(client: AsyncClient, issue_otp: IssueOtp, mobile: str) -> dict[str, str]:
    await issue_otp(mobile)
    response = await client.post(
        f"{AUTH_PREFIX}/verify-otp", json={"mobile": mobile, "code": MOCK_CODE}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_routes_are_discovered(settings: Settings) -> None:
    """Guards the two tests below: they must see every /admin route (AUTH-11, CAT-10)."""
    endpoints = _admin_endpoints(settings)
    assert {method for method, _path in endpoints} == {"GET", "POST", "PATCH", "DELETE"}
    assert ("DELETE", "/api/v1/admin/categories/00000000-0000-0000-0000-000000000000") in endpoints
    assert len(endpoints) >= 7


async def test_every_admin_route_requires_authentication(
    auth_client: AsyncClient, settings: Settings
) -> None:
    """ADR-018.authn: every /admin route answers 401 with WWW-Authenticate before any
    validation, for whatever admin routes exist now or later."""
    for method, path in _admin_endpoints(settings):
        response = await auth_client.request(method, path, params={"unknown": "1"}, json={})
        assert response.status_code == 401, (method, path)
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("roles", [("customer",), ()])
async def test_customer_is_forbidden_on_every_admin_route(
    auth_client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    db_engine: AsyncEngine,
    settings: Settings,
    roles: tuple[str, ...],
) -> None:
    """ADR-018.permission: a customer (or a user with no role) gets 403 on every /admin
    route; a role sent by the client in the query or body changes nothing."""
    headers = await _login(auth_client, issue_otp, new_mobile)
    user_id = await _user_id(db_engine, new_mobile)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        session.add_all(UserRole(user_id=user_id, role_id=role_id(name)) for name in roles)

    for method, path in _admin_endpoints(settings):
        response = await auth_client.request(
            method,
            path,
            headers={**headers, "X-Role": "super_admin"},
            params={"role": "super_admin"},
            json={"roles": ["super_admin"], "status": "active"},
        )
        assert response.status_code == 403, (method, path)
        assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_customer_sees_and_edits_only_their_own_account(
    auth_client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    """ADR-018.ownership: /auth/me and /users/me resolve the caller from the token only;
    an id, mobile or role in the request cannot point them at another account."""
    other = "+989" + new_mobile[4:][::-1]
    try:
        own_headers = await _login(auth_client, issue_otp, new_mobile)
        await _login(auth_client, issue_otp, other)
        own_id = await _user_id(db_engine, new_mobile)
        other_id = await _user_id(db_engine, other)

        me = await auth_client.get(
            f"{AUTH_PREFIX}/me", headers=own_headers, params={"user_id": str(other_id)}
        )
        assert me.json()["id"] == str(own_id)
        assert me.json()["mobile"] == new_mobile

        foreign = await auth_client.patch(
            "/api/v1/users/me", headers=own_headers, json={"id": str(other_id), "first_name": "X"}
        )
        assert foreign.status_code == 400
        renamed = await auth_client.patch(
            "/api/v1/users/me", headers=own_headers, json={"first_name": "Own"}
        )
        assert renamed.json()["id"] == str(own_id)
        async with AsyncSession(db_engine) as session:
            other_name = await session.scalar(select(User.first_name).where(User.id == other_id))
            audits = await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.entity_id == other_id, AuditLog.action == "user.profile_updated")
            )
        assert other_name is None
        assert audits == 0
    finally:
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(User).where(User.phone == other))
