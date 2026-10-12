from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from http.cookies import SimpleCookie
from typing import Annotated, Any
from uuid import UUID

import jwt
import pytest
import pytest_asyncio
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.time import utc_now
from app.db.models import OtpCode, User, UserRole, UserSession, UserStatus
from app.db.seed import ALL_PERMISSION_KEYS, DEFAULT_ROLES, ROLE_PERMISSIONS, role_id, seed_rbac
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.auth.service import CurrentUser
from app.modules.auth.tokens import JWT_ALGORITHM, create_access_token

pytestmark = pytest.mark.integration

IssueOtp = Callable[..., Awaitable[OtpCode]]
TEST_PREFIX = "/api/v1/_test"


def _build_test_router() -> APIRouter:
    """Routes that exist only in this test app, one per permission key."""
    router = APIRouter(prefix="/_test")

    @router.get("/me")
    async def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict[str, Any]:
        return {
            "id": str(user.id),
            "roles": sorted(user.roles),
            "permissions": sorted(user.permissions),
        }

    @router.post("/write")
    async def write(
        user: Annotated[CurrentUser, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> dict[str, str]:
        # A service opening its own transaction after authentication on the same session.
        async with session.begin():
            await session.execute(text("SELECT 1"))
        return {"id": str(user.id)}

    for key in sorted(ALL_PERMISSION_KEYS):
        # A default, not Annotated: string annotations cannot see the loop variable.
        async def guarded(
            user: CurrentUser = Depends(require_permission(key)),  # noqa: B008
        ) -> dict[str, str]:
            return {"id": str(user.id)}

        router.add_api_route(f"/perm/{key}", guarded, methods=["GET"])
    return router


@pytest_asyncio.fixture
async def client(settings: Settings, db_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    async with AsyncSession(db_engine) as session, session.begin():
        await seed_rbac(session)
    database_url = db_engine.url.render_as_string(hide_password=False)
    application = create_app(settings.model_copy(update={"database_url": database_url}))
    application.include_router(_build_test_router(), prefix="/api/v1")
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client


@pytest_asyncio.fixture(autouse=True)
async def _drop_users_of_mobile(new_mobile: str, db_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone == new_mobile))


async def _login(client: AsyncClient, issue_otp: IssueOtp, mobile: str) -> tuple[str, str]:
    """Access token and refresh token of a fresh customer session."""
    await issue_otp(mobile)
    response = await client.post(
        "/api/v1/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
    )
    assert response.status_code == 200
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return response.json()["access_token"], cookie["refresh_token"].value


async def _get(client: AsyncClient, path: str, token: str | None) -> Response:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return await client.get(f"{TEST_PREFIX}{path}", headers=headers)


async def _user_id(db_engine: AsyncEngine, mobile: str) -> UUID:
    async with AsyncSession(db_engine) as session:
        user_id: UUID = (await session.scalars(select(User.id).where(User.phone == mobile))).one()
        return user_id


async def _set_roles(db_engine: AsyncEngine, user_id: UUID, *roles: str) -> None:
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        session.add_all(UserRole(user_id=user_id, role_id=role_id(name)) for name in roles)


async def _update_user(db_engine: AsyncEngine, user_id: UUID, **values: Any) -> None:
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(update(User).where(User.id == user_id).values(**values))


def _assert_unauthorized(response: Response) -> None:
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.headers["www-authenticate"] == "Bearer"


def _assert_forbidden(response: Response) -> None:
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_valid_token_returns_the_user_from_the_database(
    client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)

    response = await _get(client, "/me", access)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(await _user_id(db_engine, new_mobile))
    assert body["roles"] == ["customer"]
    assert body["permissions"] == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer not-a-jwt"},
    ],
)
async def test_missing_or_malformed_token_is_unauthorized(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get(f"{TEST_PREFIX}/me", headers=headers)

    _assert_unauthorized(response)


async def test_tampered_expired_or_foreign_tokens_are_unauthorized(
    client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    db_engine: AsyncEngine,
    settings: Settings,
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)
    claims = jwt.decode(access, options={"verify_signature": False})
    user_id, session_id = UUID(claims["sub"]), UUID(claims["sid"])
    secret = settings.jwt_secret.get_secret_value()
    past = utc_now() - timedelta(hours=1)

    tampered = access[:-2] + ("AA" if not access.endswith("AA") else "BB")
    expired = create_access_token(user_id, session_id, settings, past)
    wrong_type = jwt.encode({**claims, "typ": "refresh"}, secret, algorithm=JWT_ALGORITHM)
    wrong_secret = jwt.encode(claims, "x" * 40, algorithm=JWT_ALGORITHM)
    alg_none = jwt.encode(claims, None, algorithm="none")
    unknown_session = create_access_token(user_id, UUID(int=0), settings, utc_now())

    for token in (tampered, expired, wrong_type, wrong_secret, alg_none, unknown_session):
        _assert_unauthorized(await _get(client, "/me", token))


async def test_access_token_dies_with_its_session(
    client: AsyncClient, issue_otp: IssueOtp, new_mobile: str
) -> None:
    access, refresh = await _login(client, issue_otp, new_mobile)
    client.cookies.clear()

    logout = await client.post(
        "/api/v1/auth/logout", headers={"Cookie": f"refresh_token={refresh}"}
    )

    assert logout.status_code == 204
    _assert_unauthorized(await _get(client, "/me", access))


async def test_access_token_of_a_rotated_session_is_unauthorized(
    client: AsyncClient, issue_otp: IssueOtp, new_mobile: str
) -> None:
    access, refresh = await _login(client, issue_otp, new_mobile)
    client.cookies.clear()

    rotated = await client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={refresh}"}
    )

    assert rotated.status_code == 200
    _assert_unauthorized(await _get(client, "/me", access))
    assert (await _get(client, "/me", rotated.json()["access_token"])).status_code == 200


async def test_expired_session_is_unauthorized(
    client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)
    user_id = await _user_id(db_engine, new_mobile)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(expires_at=utc_now() - timedelta(seconds=1))
        )

    _assert_unauthorized(await _get(client, "/me", access))


async def test_soft_deleted_user_is_unauthorized(
    client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)
    await _update_user(db_engine, await _user_id(db_engine, new_mobile), deleted_at=utc_now())

    _assert_unauthorized(await _get(client, "/me", access))


@pytest.mark.parametrize("status", [UserStatus.INACTIVE, UserStatus.BLOCKED])
async def test_inactive_or_blocked_user_is_forbidden_on_every_request(
    client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    db_engine: AsyncEngine,
    status: UserStatus,
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)
    user_id = await _user_id(db_engine, new_mobile)
    await _set_roles(db_engine, user_id, "super_admin")
    assert (await _get(client, "/me", access)).status_code == 200

    await _update_user(db_engine, user_id, status=status)

    _assert_forbidden(await _get(client, "/me", access))
    _assert_forbidden(await _get(client, "/perm/orders:read", access))

    await _update_user(db_engine, user_id, status=UserStatus.ACTIVE)
    assert (await _get(client, "/me", access)).status_code == 200


@pytest.mark.parametrize("role", [role.name for role in DEFAULT_ROLES])
async def test_permission_matrix_for_every_role(
    client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    db_engine: AsyncEngine,
    role: str,
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)
    await _set_roles(db_engine, await _user_id(db_engine, new_mobile), role)
    allowed = ROLE_PERMISSIONS[role]

    for key in sorted(ALL_PERMISSION_KEYS):
        response = await _get(client, f"/perm/{key}", access)
        if key in allowed:
            assert response.status_code == 200, (role, key)
        else:
            _assert_forbidden(response)


async def test_permission_check_without_token_is_unauthorized(client: AsyncClient) -> None:
    _assert_unauthorized(await _get(client, "/perm/orders:read", None))


async def test_role_change_takes_effect_without_a_new_token(
    client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)
    user_id = await _user_id(db_engine, new_mobile)
    _assert_forbidden(await _get(client, "/perm/pricing:update", access))

    await _set_roles(db_engine, user_id, "admin")
    assert (await _get(client, "/perm/pricing:update", access)).status_code == 200

    await _set_roles(db_engine, user_id, "customer")
    _assert_forbidden(await _get(client, "/perm/pricing:update", access))


async def test_multiple_roles_grant_the_union_of_permissions(
    client: AsyncClient, issue_otp: IssueOtp, new_mobile: str, db_engine: AsyncEngine
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)
    await _set_roles(db_engine, await _user_id(db_engine, new_mobile), "support", "content_manager")

    assert (await _get(client, "/perm/orders:read", access)).status_code == 200
    assert (await _get(client, "/perm/content:manage", access)).status_code == 200
    _assert_forbidden(await _get(client, "/perm/pricing:update", access))


async def test_client_supplied_role_or_permission_is_ignored(
    client: AsyncClient,
    issue_otp: IssueOtp,
    new_mobile: str,
    settings: Settings,
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)
    claims = jwt.decode(access, options={"verify_signature": False})
    secret = settings.jwt_secret.get_secret_value()
    forged = jwt.encode(
        {**claims, "role": "super_admin", "permissions": sorted(ALL_PERMISSION_KEYS)},
        secret,
        algorithm=JWT_ALGORITHM,
    )

    response = await client.get(
        f"{TEST_PREFIX}/perm/pricing:update?role=super_admin",
        headers={"Authorization": f"Bearer {forged}", "X-Role": "super_admin"},
    )

    _assert_forbidden(response)


async def test_services_can_open_a_transaction_after_authentication(
    client: AsyncClient, issue_otp: IssueOtp, new_mobile: str
) -> None:
    access, _ = await _login(client, issue_otp, new_mobile)

    response = await client.post(
        f"{TEST_PREFIX}/write", headers={"Authorization": f"Bearer {access}"}
    )

    assert response.status_code == 200
