from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.errors import ConflictError
from app.core.time import utc_now
from app.db.models import AuditLog, OtpCode, Role, User, UserRole, UserSession, UserStatus
from app.db.seed import role_id
from app.modules.admin.repository import AdminUserRepository
from app.modules.admin.service import AdminUserService
from app.modules.auth.repository import SessionRepository, UserRepository
from app.modules.auth.service import CurrentUser

pytestmark = pytest.mark.integration

IssueOtp = Callable[..., Awaitable[OtpCode]]
USERS_URL = "/api/v1/admin/users"
STAFF_ROLES = ("support", "content_manager", "admin", "super_admin")


def unique_mobile() -> str:
    return f"+989{uuid4().int % 1_000_000_000:09d}"


@dataclass(frozen=True, slots=True)
class Account:
    id: UUID
    mobile: str
    access_token: str
    refresh_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@pytest_asyncio.fixture
async def created_mobiles(db_engine: AsyncEngine) -> AsyncIterator[list[str]]:
    mobiles: list[str] = []
    yield mobiles
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone.in_(mobiles)))


@pytest.fixture
def make_account(
    auth_client: AsyncClient,
    issue_otp: IssueOtp,
    db_engine: AsyncEngine,
    created_mobiles: list[str],
) -> Callable[..., Awaitable[Account]]:
    """Log a new user in through verify-otp, then give them ``roles`` in the database."""

    async def _make(*roles: str, mobile: str | None = None) -> Account:
        mobile = mobile or unique_mobile()
        created_mobiles.append(mobile)
        await issue_otp(mobile)
        response = await auth_client.post(
            "/api/v1/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
        )
        assert response.status_code == 200
        cookie: SimpleCookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        async with AsyncSession(db_engine) as session, session.begin():
            user_id: UUID = (
                await session.scalars(select(User.id).where(User.phone == mobile))
            ).one()
            if roles:
                await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
                session.add_all(UserRole(user_id=user_id, role_id=role_id(name)) for name in roles)
        return Account(
            id=user_id,
            mobile=mobile,
            access_token=response.json()["access_token"],
            refresh_token=cookie["refresh_token"].value,
        )

    return _make


MakeAccount = Callable[..., Awaitable[Account]]


async def _patch_status(client: AsyncClient, actor: Account, target: UUID, status: str) -> Response:
    return await client.patch(
        f"{USERS_URL}/{target}/status", json={"status": status}, headers=actor.headers
    )


async def _patch_roles(
    client: AsyncClient, actor: Account, target: UUID, roles: list[str]
) -> Response:
    return await client.patch(
        f"{USERS_URL}/{target}/role", json={"roles": roles}, headers=actor.headers
    )


async def _status_of(db_engine: AsyncEngine, user_id: UUID) -> str:
    async with AsyncSession(db_engine) as session:
        status: str = (await session.scalars(select(User.status).where(User.id == user_id))).one()
        return status


async def _roles_of(db_engine: AsyncEngine, user_id: UUID) -> list[str]:
    async with AsyncSession(db_engine) as session:
        statement = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.name)
        )
        return list((await session.scalars(statement)).all())


async def _audits(db_engine: AsyncEngine, user_id: UUID, action: str) -> list[AuditLog]:
    async with AsyncSession(db_engine) as session:
        statement = (
            select(AuditLog)
            .where(AuditLog.entity_id == user_id, AuditLog.action == action)
            .order_by(AuditLog.created_at)
        )
        return list((await session.scalars(statement)).all())


def _assert_error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


# --- GET /admin/users ---------------------------------------------------------------


async def test_list_users_paginates_and_filters_by_mobile(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    prefix = unique_mobile()[:-3]
    accounts = [await make_account(mobile=f"{prefix}{index:03d}") for index in range(3)]

    response = await auth_client.get(
        USERS_URL, params={"mobile": prefix, "limit": 2, "sort": "oldest"}, headers=admin.headers
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["total"], body["page"], body["limit"], body["pages"]) == (3, 1, 2, 2)
    assert [item["id"] for item in body["items"]] == [str(a.id) for a in accounts[:2]]
    assert body["items"][0]["mobile"] == accounts[0].mobile
    assert body["items"][0]["roles"] == ["customer"]

    second = await auth_client.get(
        USERS_URL,
        params={"mobile": prefix, "limit": 2, "page": 2, "sort": "oldest"},
        headers=admin.headers,
    )
    assert [item["id"] for item in second.json()["items"]] == [str(accounts[2].id)]

    # A local-format number (leading 0) finds the same user.
    local = "0" + accounts[1].mobile.removeprefix("+98")
    by_local = await auth_client.get(USERS_URL, params={"mobile": local}, headers=admin.headers)
    assert [item["id"] for item in by_local.json()["items"]] == [str(accounts[1].id)]


async def test_list_users_filters_by_status_and_role(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    prefix = unique_mobile()[:-3]
    support = await make_account("support", mobile=f"{prefix}001")
    blocked = await make_account(mobile=f"{prefix}002")
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(User).where(User.id == blocked.id).values(status=UserStatus.BLOCKED)
        )

    async def ids(**params: str) -> list[str]:
        response = await auth_client.get(
            USERS_URL, params={"mobile": prefix, **params}, headers=admin.headers
        )
        assert response.status_code == 200
        return [item["id"] for item in response.json()["items"]]

    assert await ids(role="support") == [str(support.id)]
    assert await ids(status="blocked") == [str(blocked.id)]
    assert await ids(status="active", role="customer") == []


async def test_list_users_excludes_soft_deleted(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    target = await make_account()
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(update(User).where(User.id == target.id).values(deleted_at=utc_now()))

    response = await auth_client.get(
        USERS_URL, params={"mobile": target.mobile}, headers=admin.headers
    )
    assert response.json()["total"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "101"},
        {"page": "0"},
        {"page": "1001"},
        {"status": "deleted"},
        {"role": "warehouse_manager"},
        {"sort": "phone"},
        {"mobile": "09a1"},
        {"mobile": "12"},
        {"deleted": "true"},
    ],
)
async def test_list_users_rejects_invalid_or_unknown_parameters(
    auth_client: AsyncClient, make_account: MakeAccount, params: dict[str, str]
) -> None:
    admin = await make_account("admin")
    response = await auth_client.get(USERS_URL, params=params, headers=admin.headers)
    _assert_error(response, 400, "VALIDATION_ERROR")


async def test_list_users_accepts_limit_100(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    response = await auth_client.get(USERS_URL, params={"limit": 100}, headers=admin.headers)
    assert response.status_code == 200
    assert response.json()["limit"] == 100


async def test_list_users_requires_authentication(auth_client: AsyncClient) -> None:
    response = await auth_client.get(USERS_URL)
    _assert_error(response, 401, "UNAUTHORIZED")


@pytest.mark.parametrize("roles", [(), ("support",), ("content_manager",)])
async def test_list_users_forbidden_without_users_read(
    auth_client: AsyncClient, make_account: MakeAccount, roles: tuple[str, ...]
) -> None:
    account = await make_account(*roles)
    response = await auth_client.get(USERS_URL, headers=account.headers)
    _assert_error(response, 403, "FORBIDDEN")


# --- PATCH /admin/users/{id}/status ---------------------------------------------------


@pytest.mark.parametrize("status", ["inactive", "blocked"])
async def test_admin_deactivates_customer_and_revokes_all_sessions(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    issue_otp: IssueOtp,
    db_engine: AsyncEngine,
    status: str,
) -> None:
    admin = await make_account("admin")
    customer = await make_account()
    # A second login gives the customer a second session family.
    await issue_otp(customer.mobile)
    second = await auth_client.post(
        "/api/v1/auth/verify-otp", json={"mobile": customer.mobile, "code": "123456"}
    )
    assert second.status_code == 200

    response = await _patch_status(auth_client, admin, customer.id, status)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == status
    assert response.headers["cache-control"] == "no-store"
    assert await _status_of(db_engine, customer.id) == status

    async with AsyncSession(db_engine) as session:
        active = await session.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.user_id == customer.id, UserSession.revoked_at.is_(None))
        )
    assert active == 0
    me = await auth_client.get("/api/v1/auth/me", headers=customer.headers)
    assert me.status_code in {401, 403}
    auth_client.cookies.set("refresh_token", customer.refresh_token, path="/api/v1/auth")
    refreshed = await auth_client.post("/api/v1/auth/refresh")
    auth_client.cookies.clear()
    _assert_error(refreshed, 401, "UNAUTHORIZED")

    (audit,) = await _audits(db_engine, customer.id, "user.status_changed")
    assert audit.actor_user_id == admin.id
    assert audit.metadata_["diff"] == {
        "status": {"before": "active", "after": status, "changed": True},
        "revoked_sessions": {"before": None, "after": 2, "changed": True},
    }


async def test_reactivation_keeps_sessions_revoked_and_is_audited(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    customer = await make_account()
    assert (await _patch_status(auth_client, admin, customer.id, "blocked")).status_code == 200

    response = await _patch_status(auth_client, admin, customer.id, "active")
    assert response.status_code == 200
    assert await _status_of(db_engine, customer.id) == "active"
    # Old tokens stay dead: their session was revoked by the block.
    me = await auth_client.get("/api/v1/auth/me", headers=customer.headers)
    _assert_error(me, 401, "UNAUTHORIZED")
    audits = await _audits(db_engine, customer.id, "user.status_changed")
    assert [a.metadata_["diff"]["status"]["after"] for a in audits] == ["blocked", "active"]


async def test_unchanged_status_is_a_no_op_without_audit(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    customer = await make_account()
    response = await _patch_status(auth_client, admin, customer.id, "active")
    assert response.status_code == 200
    assert await _audits(db_engine, customer.id, "user.status_changed") == []
    me = await auth_client.get("/api/v1/auth/me", headers=customer.headers)
    assert me.status_code == 200


@pytest.mark.parametrize("staff_role", STAFF_ROLES)
async def test_admin_cannot_change_status_of_staff(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
    staff_role: str,
) -> None:
    admin = await make_account("admin")
    # Customer plus a staff role: any staff role makes the target super-admin-only.
    target = await make_account("customer", staff_role)
    response = await _patch_status(auth_client, admin, target.id, "blocked")
    _assert_error(response, 403, "FORBIDDEN")
    assert await _status_of(db_engine, target.id) == "active"
    assert await _audits(db_engine, target.id, "user.status_changed") == []


@pytest.mark.parametrize("staff_role", STAFF_ROLES)
async def test_super_admin_can_change_status_of_staff(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
    staff_role: str,
) -> None:
    super_admin = await make_account("super_admin")
    target = await make_account(staff_role)
    response = await _patch_status(auth_client, super_admin, target.id, "inactive")
    assert response.status_code == 200, response.text
    assert await _status_of(db_engine, target.id) == "inactive"


async def test_admin_can_change_status_of_user_without_roles(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    target = await make_account()
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(UserRole).where(UserRole.user_id == target.id))
    response = await _patch_status(auth_client, admin, target.id, "blocked")
    assert response.status_code == 200


@pytest.mark.parametrize("roles", [("admin",), ("super_admin",)])
async def test_status_change_of_self_is_rejected(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
    roles: tuple[str, ...],
) -> None:
    actor = await make_account(*roles)
    response = await _patch_status(auth_client, actor, actor.id, "inactive")
    _assert_error(response, 422, "BUSINESS_RULE_VIOLATION")
    assert await _status_of(db_engine, actor.id) == "active"


@pytest.mark.parametrize("roles", [(), ("support",), ("content_manager",)])
async def test_status_change_requires_users_manage(
    auth_client: AsyncClient, make_account: MakeAccount, roles: tuple[str, ...]
) -> None:
    actor = await make_account(*roles)
    target = await make_account()
    response = await _patch_status(auth_client, actor, target.id, "blocked")
    _assert_error(response, 403, "FORBIDDEN")


async def test_status_change_unknown_or_deleted_user_is_not_found(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    _assert_error(await _patch_status(auth_client, admin, uuid4(), "blocked"), 404, "NOT_FOUND")
    target = await make_account()
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(update(User).where(User.id == target.id).values(deleted_at=utc_now()))
    _assert_error(await _patch_status(auth_client, admin, target.id, "blocked"), 404, "NOT_FOUND")


@pytest.mark.parametrize(
    "body",
    [{}, {"status": "deleted"}, {"status": "blocked", "role": "admin"}, {"status": None}],
)
async def test_status_change_rejects_invalid_body(
    auth_client: AsyncClient, make_account: MakeAccount, body: dict[str, Any]
) -> None:
    admin = await make_account("admin")
    target = await make_account()
    response = await auth_client.patch(
        f"{USERS_URL}/{target.id}/status", json=body, headers=admin.headers
    )
    _assert_error(response, 400, "VALIDATION_ERROR")


async def test_status_change_rejects_malformed_user_id(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    response = await auth_client.patch(
        f"{USERS_URL}/not-a-uuid/status", json={"status": "blocked"}, headers=admin.headers
    )
    _assert_error(response, 400, "VALIDATION_ERROR")


async def test_status_change_requires_authentication(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(f"{USERS_URL}/{uuid4()}/status", json={"status": "blocked"})
    _assert_error(response, 401, "UNAUTHORIZED")


# --- PATCH /admin/users/{id}/role -------------------------------------------------------


async def test_super_admin_replaces_roles_with_audit(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    super_admin = await make_account("super_admin")
    target = await make_account()

    response = await _patch_roles(auth_client, super_admin, target.id, ["support", "customer"])
    assert response.status_code == 200, response.text
    assert response.json()["roles"] == ["customer", "support"]
    assert response.headers["cache-control"] == "no-store"
    assert await _roles_of(db_engine, target.id) == ["customer", "support"]

    # The target's existing token immediately carries the new permissions (ADR-018).
    me = await auth_client.get("/api/v1/auth/me", headers=target.headers)
    assert "orders:read" in me.json()["permissions"]

    (audit,) = await _audits(db_engine, target.id, "user.roles_changed")
    assert audit.actor_user_id == super_admin.id
    assert audit.metadata_["diff"] == {
        "roles": {"before": ["customer"], "after": ["customer", "support"], "changed": True}
    }


async def test_super_admin_can_grant_and_revoke_super_admin(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    super_admin = await make_account("super_admin")
    target = await make_account()
    granted = await _patch_roles(auth_client, super_admin, target.id, ["super_admin"])
    assert granted.status_code == 200
    revoked = await _patch_roles(auth_client, super_admin, target.id, ["customer"])
    assert revoked.status_code == 200
    assert await _roles_of(db_engine, target.id) == ["customer"]


async def test_unchanged_roles_are_a_no_op_without_audit(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    super_admin = await make_account("super_admin")
    target = await make_account()
    response = await _patch_roles(auth_client, super_admin, target.id, ["customer"])
    assert response.status_code == 200
    assert await _audits(db_engine, target.id, "user.roles_changed") == []


@pytest.mark.parametrize("target_roles", [["super_admin"], ["admin"], ["customer"]])
async def test_admin_cannot_change_roles(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
    target_roles: list[str],
) -> None:
    admin = await make_account("admin")
    target = await make_account()
    # Neither another user nor themself, to any role (no escalation to super admin).
    for user_id in (target.id, admin.id):
        response = await _patch_roles(auth_client, admin, user_id, target_roles)
        _assert_error(response, 403, "FORBIDDEN")
    assert await _roles_of(db_engine, admin.id) == ["admin"]
    assert await _roles_of(db_engine, target.id) == ["customer"]


@pytest.mark.parametrize("roles", [(), ("support",), ("content_manager",)])
async def test_role_change_forbidden_for_other_roles(
    auth_client: AsyncClient, make_account: MakeAccount, roles: tuple[str, ...]
) -> None:
    actor = await make_account(*roles)
    target = await make_account()
    _assert_error(await _patch_roles(auth_client, actor, target.id, ["admin"]), 403, "FORBIDDEN")


async def test_role_change_of_self_is_rejected(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    super_admin = await make_account("super_admin")
    response = await _patch_roles(auth_client, super_admin, super_admin.id, ["customer"])
    _assert_error(response, 422, "BUSINESS_RULE_VIOLATION")
    assert await _roles_of(db_engine, super_admin.id) == ["super_admin"]


@pytest.mark.parametrize(
    "roles",
    [
        ["warehouse_manager"],
        ["legacy_role"],
        ["finance_manager"],
        [],
        ["customer", "customer"],
        ["customer", "support", "content_manager", "admin", "super_admin", "customer"],
    ],
)
async def test_role_change_accepts_only_default_roles(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
    roles: list[str],
) -> None:
    super_admin = await make_account("super_admin")
    target = await make_account()
    # A role row in the database does not make a role assignable.
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(Role(name="legacy_role", description="Legacy", is_system=False))
    try:
        response = await _patch_roles(auth_client, super_admin, target.id, roles)
        _assert_error(response, 400, "VALIDATION_ERROR")
        assert await _roles_of(db_engine, target.id) == ["customer"]
    finally:
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(Role).where(Role.name == "legacy_role"))


async def test_role_change_unknown_or_deleted_user_is_not_found(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    super_admin = await make_account("super_admin")
    _assert_error(
        await _patch_roles(auth_client, super_admin, uuid4(), ["admin"]), 404, "NOT_FOUND"
    )
    target = await make_account()
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(update(User).where(User.id == target.id).values(deleted_at=utc_now()))
    response = await _patch_roles(auth_client, super_admin, target.id, ["admin"])
    _assert_error(response, 404, "NOT_FOUND")


async def test_role_change_requires_authentication(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(f"{USERS_URL}/{uuid4()}/role", json={"roles": ["admin"]})
    _assert_error(response, 401, "UNAUTHORIZED")


# --- last super admin (concurrent removal) ---------------------------------------------


@pytest_asyncio.fixture
async def only_super_admins(db_engine: AsyncEngine) -> AsyncIterator[list[UUID]]:
    """Hide every other super admin for the test; restore their role afterwards."""
    super_admin_id = role_id("super_admin")
    async with AsyncSession(db_engine) as session, session.begin():
        others = list(
            (
                await session.scalars(
                    select(UserRole.user_id).where(UserRole.role_id == super_admin_id)
                )
            ).all()
        )
        await session.execute(delete(UserRole).where(UserRole.role_id == super_admin_id))
    yield others
    async with AsyncSession(db_engine) as session, session.begin():
        existing = set((await session.scalars(select(User.id).where(User.id.in_(others)))).all())
        session.add_all(
            UserRole(user_id=user_id, role_id=super_admin_id)
            for user_id in others
            if user_id in existing
        )


def _service(session: AsyncSession) -> AdminUserService:
    return AdminUserService(
        session, AdminUserRepository(session), UserRepository(session), SessionRepository(session)
    )


def _stale_super_admin(user_id: UUID) -> CurrentUser:
    """The actor as authenticated before a concurrent request demoted them."""
    return CurrentUser(
        id=user_id,
        session_id=uuid4(),
        status=UserStatus.ACTIVE,
        roles=frozenset({"super_admin"}),
        permissions=frozenset({"users:manage", "users:manage_roles"}),
    )


@pytest.mark.usefixtures("only_super_admins")
async def test_last_super_admin_cannot_be_demoted_or_deactivated(
    make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    first = await make_account("super_admin")
    second = await make_account("super_admin")
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        # first demotes second; second's in-flight request then tries to remove first.
        await _service(session).change_roles(
            _stale_super_admin(first.id), second.id, ["admin"], None
        )
        with pytest.raises(ConflictError):
            await _service(session).change_roles(
                _stale_super_admin(second.id), first.id, ["admin"], None
            )
        with pytest.raises(ConflictError):
            await _service(session).change_status(
                _stale_super_admin(second.id), first.id, UserStatus.BLOCKED, None
            )
    assert await _roles_of(db_engine, first.id) == ["super_admin"]
    assert await _status_of(db_engine, first.id) == "active"
    assert await _audits(db_engine, first.id, "user.roles_changed") == []
