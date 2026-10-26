"""Admin shipping methods: CRUD, validation, audit, access, public effect (ADDR-03/04)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.errors import AppError
from app.core.time import utc_now
from app.db.models import AuditLog, ShippingMethod
from app.db.seed import ROLE_PERMISSIONS
from app.modules.shipping.repository import ShippingRepository
from app.shared.money import MAX_PRICE_TOMAN

pytestmark = pytest.mark.integration

URL = "/api/v1/admin/shipping-methods"
PUBLIC_URL = "/api/v1/shipping-methods"


def _error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    return body


def _title() -> str:
    return f"Ship {uuid4().hex[:10]}"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(db_engine: AsyncEngine) -> AsyncIterator[None]:
    started = utc_now()
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(ShippingMethod).where(ShippingMethod.created_at >= started))


async def _create(client: AsyncClient, headers: dict[str, str], **fields: Any) -> dict[str, Any]:
    body = {"title": _title(), "cost": 30_000} | fields
    response = await client.post(URL, json=body, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _audits(engine: AsyncEngine, method_id: str) -> list[AuditLog]:
    async with AsyncSession(engine) as session:
        statement = (
            select(AuditLog)
            .where(AuditLog.entity_id == method_id)
            .order_by(AuditLog.created_at, AuditLog.id)
        )
        return list(await session.scalars(statement))


# --- create --------------------------------------------------------------------------


async def test_create_trims_ignores_system_fields_and_audits_a_full_snapshot(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    title = _title()
    forged = str(uuid4())

    response = await auth_client.post(
        URL,
        json={
            "title": f"  {title} ",
            "description": " 3-5 days ",
            "cost": 45_000,
            "free_shipping_threshold": 1_000_000,
            "display_order": 3,
            # Server-owned fields are ignored.
            "id": forged,
            "deleted_at": "2020-01-01T00:00:00Z",
            "created_at": "2020-01-01T00:00:00Z",
        },
        headers=admin.headers,
    )

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["id"] != forged
    assert (body["title"], body["description"], body["cost"]) == (title, "3-5 days", 45_000)
    assert (body["free_shipping_threshold"], body["is_active"], body["display_order"]) == (
        1_000_000,
        True,
        3,
    )
    [audit] = await _audits(db_engine, body["id"])
    assert audit.action == "shipping_method.created"
    assert audit.actor_user_id == admin.id
    assert {key for key, value in audit.metadata_["diff"].items() if value["changed"]} == {
        "title",
        "description",
        "cost",
        "free_shipping_threshold",
        "is_active",
        "display_order",
    }
    detail = await auth_client.get(f"{URL}/{body['id']}", headers=admin.headers)
    assert detail.status_code == 200 and detail.json() == body


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "   "},
        {"title": "x" * 101},
        {"title": 5},
        {"description": "   "},
        {"description": "x" * 501},
        {"cost": -1},
        {"cost": MAX_PRICE_TOMAN + 1},
        {"cost": 10.0},
        {"cost": "30000"},
        {"cost": True},
        {"cost": None},
        {"free_shipping_threshold": 0},
        {"free_shipping_threshold": 1.5},
        {"free_shipping_threshold": MAX_PRICE_TOMAN + 1},
        {"is_active": "yes"},
        {"display_order": -1},
        {"display_order": 1_000_001},
        {"colour": "red"},
    ],
)
async def test_create_rejects_invalid_bodies(
    auth_client: AsyncClient, make_account: MakeAccount, fields: dict[str, Any]
) -> None:
    admin = await make_account("admin")
    body = {"title": _title(), "cost": 30_000} | fields
    response = await auth_client.post(URL, json=body, headers=admin.headers)
    _error(response, 400, "VALIDATION_ERROR")


async def test_missing_required_fields_are_400(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    for body in ({"title": _title()}, {"cost": 1}):
        _error(
            await auth_client.post(URL, json=body, headers=admin.headers), 400, "VALIDATION_ERROR"
        )


async def test_zero_cost_and_limits_are_accepted(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    free = await _create(auth_client, admin.headers, cost=0)
    top = await _create(
        auth_client,
        admin.headers,
        cost=MAX_PRICE_TOMAN,
        free_shipping_threshold=MAX_PRICE_TOMAN,
        display_order=1_000_000,
    )
    assert free["cost"] == 0
    assert (top["cost"], top["free_shipping_threshold"]) == (MAX_PRICE_TOMAN, MAX_PRICE_TOMAN)


# --- list and detail -----------------------------------------------------------------


async def test_list_filters_orders_and_hides_deleted(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    prefix = f"L{uuid4().hex[:8]}"
    late = await _create(auth_client, admin.headers, title=f"{prefix} C", display_order=2)
    tie_b = await _create(auth_client, admin.headers, title=f"{prefix} B", display_order=1)
    tie_a = await _create(
        auth_client, admin.headers, title=f"{prefix} A", display_order=1, is_active=False
    )
    gone = await _create(auth_client, admin.headers, title=f"{prefix} D")
    await auth_client.delete(f"{URL}/{gone['id']}", headers=admin.headers)

    listing = await auth_client.get(URL, params={"q": prefix}, headers=admin.headers)
    active = await auth_client.get(
        URL, params={"q": prefix, "state": "active"}, headers=admin.headers
    )
    inactive = await auth_client.get(
        URL, params={"q": prefix.lower(), "state": "inactive"}, headers=admin.headers
    )
    paged = await auth_client.get(
        URL, params={"q": prefix, "limit": 1, "page": 2}, headers=admin.headers
    )

    assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
    assert [item["id"] for item in listing.json()["items"]] == [
        tie_a["id"],
        tie_b["id"],
        late["id"],
    ]
    assert listing.json()["total"] == 3
    assert [item["id"] for item in active.json()["items"]] == [tie_b["id"], late["id"]]
    assert [item["id"] for item in inactive.json()["items"]] == [tie_a["id"]]
    assert [item["id"] for item in paged.json()["items"]] == [tie_b["id"]]


async def test_search_text_is_literal(auth_client: AsyncClient, make_account: MakeAccount) -> None:
    admin = await make_account("admin")
    marker = uuid4().hex[:8]
    await _create(auth_client, admin.headers, title=f"{marker} 100% fast")
    await _create(auth_client, admin.headers, title=f"{marker} 1000 slow")
    response = await auth_client.get(URL, params={"q": f"{marker} 100%"}, headers=admin.headers)
    assert [item["title"] for item in response.json()["items"]] == [f"{marker} 100% fast"]


async def test_list_rejects_bad_query(auth_client: AsyncClient, make_account: MakeAccount) -> None:
    admin = await make_account("admin")
    for params in (
        {"q": "  "},
        {"q": "x" * 101},
        {"state": "paused"},
        {"sort": "title"},
        {"limit": 0},
        {"page": 0},
    ):
        _error(
            await auth_client.get(URL, params=params, headers=admin.headers),
            400,
            "VALIDATION_ERROR",
        )


async def test_detail_delete_and_missing_ids(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    method = await _create(auth_client, admin.headers, cost=12_000)
    url = f"{URL}/{method['id']}"

    detail = await auth_client.get(url, headers=admin.headers)
    first = await auth_client.delete(url, headers=admin.headers)
    second = await auth_client.delete(url, headers=admin.headers)

    assert detail.status_code == 200 and detail.headers["cache-control"] == "no-store"
    assert first.status_code == 204 and first.headers["cache-control"] == "no-store"
    _error(second, 404, "NOT_FOUND")
    _error(await auth_client.get(url, headers=admin.headers), 404, "NOT_FOUND")
    _error(await auth_client.patch(url, json={"cost": 1}, headers=admin.headers), 404, "NOT_FOUND")
    missing = f"{URL}/{uuid4()}"
    _error(await auth_client.get(missing, headers=admin.headers), 404, "NOT_FOUND")
    _error(
        await auth_client.patch(missing, json={"cost": 1}, headers=admin.headers),
        404,
        "NOT_FOUND",
    )
    _error(await auth_client.delete(missing, headers=admin.headers), 404, "NOT_FOUND")
    bad = f"{URL}/not-a-uuid"
    for response in (
        await auth_client.get(bad, headers=admin.headers),
        await auth_client.patch(bad, json={"cost": 1}, headers=admin.headers),
        await auth_client.delete(bad, headers=admin.headers),
    ):
        _error(response, 400, "VALIDATION_ERROR")
    audits = await _audits(db_engine, method["id"])
    assert [audit.action for audit in audits] == [
        "shipping_method.created",
        "shipping_method.deleted",
    ]
    deleted = audits[1].metadata_["diff"]
    assert deleted["cost"]["before"] == 12_000
    assert deleted["is_active"]["before"] is True
    # Soft deleted: the row stays for order snapshots and the future Shipment FK.
    async with AsyncSession(db_engine) as session:
        stored = await session.get(ShippingMethod, UUID(method["id"]))
    assert stored is not None and stored.deleted_at is not None


# --- update --------------------------------------------------------------------------


async def test_update_audits_only_changes(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    method = await _create(
        auth_client, admin.headers, description="old", free_shipping_threshold=500_000
    )
    url = f"{URL}/{method['id']}"

    changed = await auth_client.patch(
        url,
        json={
            "cost": 40_000,
            "free_shipping_threshold": None,
            "description": None,
            "title": method["title"],
            "id": str(uuid4()),
        },
        headers=admin.headers,
    )
    unchanged = await auth_client.patch(url, json={"cost": 40_000}, headers=admin.headers)

    assert changed.status_code == 200, changed.text
    assert changed.headers["cache-control"] == "no-store"
    body = changed.json()
    assert (body["id"], body["cost"], body["free_shipping_threshold"], body["description"]) == (
        method["id"],
        40_000,
        None,
        None,
    )
    assert unchanged.status_code == 200
    audits = await _audits(db_engine, method["id"])
    assert [audit.action for audit in audits] == [
        "shipping_method.created",
        "shipping_method.updated",
    ]
    assert audits[1].metadata_["diff"] == {
        "cost": {"before": 30_000, "after": 40_000, "changed": True},
        "free_shipping_threshold": {"before": 500_000, "after": None, "changed": True},
        "description": {"before": "old", "after": None, "changed": True},
    }


async def test_update_rejects_invalid_bodies(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    method = await _create(auth_client, admin.headers)
    url = f"{URL}/{method['id']}"
    for body in (
        {},
        {"id": str(uuid4())},
        {"title": None},
        {"title": "   "},
        {"description": "   "},
        {"cost": "30000"},
        {"cost": None},
        {"is_active": None},
        {"display_order": None},
        {"cost": -5},
        {"cost": 1.0},
        {"free_shipping_threshold": 0},
        {"unknown": 1},
    ):
        _error(
            await auth_client.patch(url, json=body, headers=admin.headers), 400, "VALIDATION_ERROR"
        )


async def test_concurrent_updates_are_serialized_in_the_audit_chain(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    method = await _create(auth_client, admin.headers, cost=10_000)
    url = f"{URL}/{method['id']}"

    responses = await asyncio.gather(
        auth_client.patch(url, json={"cost": 20_000}, headers=admin.headers),
        auth_client.patch(url, json={"cost": 30_000}, headers=admin.headers),
    )

    assert [response.status_code for response in responses] == [200, 200]
    updates = [
        audit.metadata_["diff"]["cost"]
        for audit in await _audits(db_engine, method["id"])
        if audit.action == "shipping_method.updated"
    ]
    # Whatever order the lock granted, the second edit saw the first one's result.
    pairs = {(update["before"], update["after"]) for update in updates}
    assert pairs in ({(10_000, 20_000), (20_000, 30_000)}, {(10_000, 30_000), (30_000, 20_000)})
    final = await auth_client.get(url, headers=admin.headers)
    assert final.json()["cost"] in {20_000, 30_000} - {before for before, _ in pairs}


# --- authorization -------------------------------------------------------------------


def test_only_admins_hold_shipping_manage() -> None:
    holders = {role for role, keys in ROLE_PERMISSIONS.items() if "shipping:manage" in keys}
    assert holders == {"admin", "super_admin"}


async def test_every_endpoint_needs_shipping_manage_before_validation(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    target = f"{URL}/{uuid4()}"
    calls: list[tuple[str, str, Any]] = [
        ("GET", URL, None),
        ("GET", target, None),
        ("POST", URL, {"cost": "x"}),
        ("PATCH", target, {"cost": "x"}),
        ("DELETE", target, None),
    ]

    async def call(method: str, url: str, body: Any, headers: dict[str, str]) -> Response:
        return await auth_client.request(method, url, json=body, headers=headers)

    for method, url, body in calls:
        _error(await call(method, url, body, {}), 401, "UNAUTHORIZED")
    for role in ("support", "content_manager", "customer"):
        actor = await make_account(role)
        for method, url, body in calls:
            _error(await call(method, url, body, actor.headers), 403, "FORBIDDEN")
    super_admin = await make_account("super_admin")
    created = await _create(auth_client, super_admin.headers)
    assert created["is_active"] is True


# --- effect on the public list and checkout lookup (ADDR-04) -------------------------


async def test_admin_changes_reach_the_public_list_and_checkout_lookup(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    method = await _create(auth_client, admin.headers, cost=25_000)
    url = f"{URL}/{method['id']}"

    async def public() -> dict[str, Any] | None:
        response = await auth_client.get(PUBLIC_URL)
        assert response.status_code == 200
        found = [item for item in response.json() if item["id"] == method["id"]]
        return found[0] if found else None

    async def selectable() -> bool:
        async with AsyncSession(db_engine) as session, session.begin():
            try:
                await ShippingRepository(session).get_selectable(UUID(method["id"]))
            except AppError as error:
                assert error.status_code == 422
                return False
            return True

    listed = await public()
    assert listed is not None and listed["cost"] == 25_000
    assert set(listed) == {"id", "title", "description", "cost", "free_shipping_threshold"}

    await auth_client.patch(url, json={"cost": 35_000}, headers=admin.headers)
    repriced = await public()
    assert repriced is not None and repriced["cost"] == 35_000

    await auth_client.patch(url, json={"is_active": False}, headers=admin.headers)
    assert await public() is None and not await selectable()

    await auth_client.patch(url, json={"is_active": True}, headers=admin.headers)
    assert await public() is not None and await selectable()

    await auth_client.delete(url, headers=admin.headers)
    assert await public() is None and not await selectable()
