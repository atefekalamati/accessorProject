"""Admin inventory endpoints: list, PATCH, reservations, history (INV-08, ADR-038)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Catalog, MakeAccount, count_queries, new_order
from httpx import AsyncClient, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import (
    AuditLog,
    InventoryItem,
    InventoryMovement,
    ProductVariant,
    Warehouse,
)
from app.db.models.inventory import WarehouseStatus
from app.modules.inventory.reservation import ReservationService, ReserveLine
from app.modules.inventory.stock import StockLevel, stock_status

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("order_factory")]

URL = "/api/v1/admin/inventory"
PAST = timedelta(minutes=20)


def _error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    return body


async def _reserve(
    engine: AsyncEngine, variant_id: UUID, quantity: int, *, now: datetime | None = None
) -> UUID:
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        result = await ReservationService(session).reserve(
            order_id=await new_order(),
            lines=[ReserveLine(variant_id, quantity)],
            user_id=None,
            now=now,
        )
    return result.reservation_id


async def _count(engine: AsyncEngine, model: Any, *criteria: Any) -> int:
    async with AsyncSession(engine) as session:
        return int(
            await session.scalar(select(func.count()).select_from(model).where(*criteria)) or 0
        )


async def _actions(engine: AsyncEngine, entity_id: UUID) -> list[str]:
    async with AsyncSession(engine) as session:
        statement = (
            select(AuditLog.action)
            .where(AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.created_at)
        )
        return list(await session.scalars(statement))


async def _item(engine: AsyncEngine, variant_id: UUID) -> InventoryItem:
    async with AsyncSession(engine) as session:
        statement = select(InventoryItem).where(InventoryItem.variant_id == variant_id)
        return (await session.scalars(statement)).one()


@pytest_asyncio.fixture
async def inactive_warehouse(db_engine: AsyncEngine) -> AsyncIterator[UUID]:
    warehouse = Warehouse(name="Closed", status=WarehouseStatus.INACTIVE, is_default=False)
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        session.add(warehouse)
    yield warehouse.id
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            delete(InventoryItem).where(InventoryItem.warehouse_id == warehouse.id)
        )
        await session.execute(delete(Warehouse).where(Warehouse.id == warehouse.id))


# --- list ----------------------------------------------------------------------------


async def test_list_shows_effective_stock_per_variant(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    db_engine: AsyncEngine,
    inactive_warehouse: UUID,
) -> None:
    admin = await make_account("admin")
    product = await catalog.product(title="Gold chain")
    plenty = await catalog.variant(product, stock=(10, 0, 2))
    low = await catalog.variant(product, stock=(2, 0, 2))
    none = await catalog.variant(product)
    sold = await catalog.variant(product, stock=(4, 0, 0))
    closed = await catalog.variant(product)
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(
            InventoryItem(
                warehouse_id=inactive_warehouse,
                product_id=product.id,
                variant_id=closed.id,
                total_quantity=50,
            )
        )
    await _reserve(db_engine, sold.id, 4)
    # Expired but not swept: it holds nothing.
    await _reserve(db_engine, plenty.id, 5, now=utc_now() - PAST)

    response = await auth_client.get(
        URL, params={"product_id": str(product.id)}, headers=admin.headers
    )

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["total"] == 5
    rows = {row["variant_id"]: row for row in body["items"]}
    expected = {
        plenty.id: (10, 0, 10, 2, "in_stock"),
        low.id: (2, 0, 2, 2, "low_stock"),
        none.id: (0, 0, 0, 0, "out_of_stock"),
        sold.id: (4, 4, 0, 0, "out_of_stock"),
        closed.id: (0, 0, 0, 0, "out_of_stock"),
    }
    for variant_id, (total, reserved, free, threshold, status) in expected.items():
        row = rows[str(variant_id)]
        assert (
            row["total"],
            row["reserved"],
            row["free"],
            row["low_stock_threshold"],
            row["stock_status"],
        ) == (total, reserved, free, threshold, status)
        assert row["product_title"] == "Gold chain"
    assert rows[str(none.id)]["updated_at"] is None


async def test_list_status_matches_the_pure_rule(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    """The SQL status equals ``stock_status`` for every counter combination."""
    admin = await make_account("admin")
    product = await catalog.product()
    cases = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (5, 2, 3), (5, 1, 3), (5, 0, 5), (9, 3, 5)]
    variants = [await catalog.variant(product, stock=stock) for stock in cases]

    response = await auth_client.get(
        URL, params={"product_id": str(product.id), "limit": 50}, headers=admin.headers
    )

    rows = {row["variant_id"]: row for row in response.json()["items"]}
    for variant, (total, reserved, threshold) in zip(variants, cases, strict=True):
        level = StockLevel(total=total, reserved=reserved, low_stock_threshold=threshold)
        assert rows[str(variant.id)]["stock_status"] == stock_status(level).value
    for status in ("in_stock", "low_stock", "out_of_stock"):
        filtered = await auth_client.get(
            URL,
            params={"product_id": str(product.id), "stock_status": status},
            headers=admin.headers,
        )
        expected = {key for key, row in rows.items() if row["stock_status"] == status}
        assert {row["variant_id"] for row in filtered.json()["items"]} == expected


async def test_list_search_sort_and_soft_delete(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    admin = await make_account("admin")
    product = await catalog.product(title="Pearl_100% ring")
    first = await catalog.variant(product, stock=(1, 0, 0))
    second = await catalog.variant(product, stock=(7, 0, 0))
    gone = await catalog.variant(product, stock=(3, 0, 0))
    await catalog.set(ProductVariant, gone.id, deleted_at=utc_now())
    params = {"product_id": str(product.id)}

    by_free = await auth_client.get(
        URL, params=params | {"sort": "free_desc"}, headers=admin.headers
    )
    assert [row["variant_id"] for row in by_free.json()["items"]] == [
        str(second.id),
        str(first.id),
    ]
    # Wildcards in q match literally.
    literal = await auth_client.get(URL, params={"q": "_100%"}, headers=admin.headers)
    assert {row["product_id"] for row in literal.json()["items"]} == {str(product.id)}
    wildcard = await auth_client.get(URL, params=params | {"q": "%x%"}, headers=admin.headers)
    assert wildcard.json()["total"] == 0
    by_sku = await auth_client.get(URL, params={"q": first.sku.lower()}, headers=admin.headers)
    assert [row["variant_id"] for row in by_sku.json()["items"]] == [str(first.id)]
    unknown = await auth_client.get(URL, params={"product_id": str(uuid4())}, headers=admin.headers)
    assert (unknown.status_code, unknown.json()["total"]) == (200, 0)


async def test_list_rejects_bad_query(auth_client: AsyncClient, make_account: MakeAccount) -> None:
    admin = await make_account("admin")
    for params in (
        {"page_size": 5},
        {"sort": "price"},
        {"stock_status": "plenty"},
        {"product_id": "nope"},
        {"q": "   "},
        {"limit": 1000},
    ):
        response = await auth_client.get(URL, params=params, headers=admin.headers)
        _error(response, 400, "VALIDATION_ERROR")


# --- PATCH ---------------------------------------------------------------------------


async def test_patch_adjusts_and_sets_threshold_in_one_call(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(5, 0, 0))

    response = await auth_client.patch(
        f"{URL}/{variant.id}",
        json={
            "adjustment_type": "increase",
            "quantity": 3,
            "low_stock_threshold": 4,
            "reason": " restock ",
            # Server-owned fields are ignored, never applied.
            "total": 999,
            "reserved_quantity": 5,
            "stock_status": "in_stock",
        },
        headers=admin.headers,
    )

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["total"], body["reserved"], body["free"], body["low_stock_threshold"]) == (
        8,
        0,
        8,
        4,
    )
    item = await _item(db_engine, variant.id)
    assert (item.total_quantity, item.reserved_quantity, item.low_stock_threshold) == (8, 0, 4)
    assert await _actions(db_engine, item.id) == [
        "inventory.threshold_updated",
        "inventory.adjusted",
    ]
    async with AsyncSession(db_engine) as session:
        [movement] = await session.scalars(
            select(InventoryMovement).where(InventoryMovement.inventory_item_id == item.id)
        )
    assert (movement.movement_type, movement.quantity, movement.reason) == (
        "increase",
        3,
        "restock",
    )
    assert movement.created_by == admin.id


async def test_threshold_only_patch_creates_a_missing_item(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product())

    response = await auth_client.patch(
        f"{URL}/{variant.id}",
        json={"low_stock_threshold": 2, "reason": "alert early"},
        headers=admin.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total"], body["low_stock_threshold"], body["stock_status"]) == (
        0,
        2,
        "out_of_stock",
    )
    item = await _item(db_engine, variant.id)
    assert (
        await _count(db_engine, InventoryMovement, InventoryMovement.inventory_item_id == item.id)
        == 0
    )
    assert await _actions(db_engine, item.id) == ["inventory.threshold_updated"]


async def test_patch_response_excludes_expired_holds(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    await _reserve(db_engine, variant.id, 4, now=utc_now() - PAST)

    response = await auth_client.patch(
        f"{URL}/{variant.id}",
        json={"low_stock_threshold": 1, "reason": "check"},
        headers=admin.headers,
    )

    assert (response.json()["reserved"], response.json()["free"]) == (0, 5)
    assert (await _item(db_engine, variant.id)).reserved_quantity == 0


async def test_unchanged_patch_is_a_noop(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 1))

    response = await auth_client.patch(
        f"{URL}/{variant.id}",
        json={
            "adjustment_type": "correction",
            "quantity": 5,
            "low_stock_threshold": 1,
            "reason": "stocktake",
        },
        headers=admin.headers,
    )

    assert response.status_code == 200, response.text
    item = await _item(db_engine, variant.id)
    assert await _actions(db_engine, item.id) == []
    assert (
        await _count(db_engine, InventoryMovement, InventoryMovement.inventory_item_id == item.id)
        == 0
    )


async def test_expected_total_guards_a_repeated_submit(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    payload = {"adjustment_type": "increase", "quantity": 2, "reason": "x", "expected_total": 5}

    first = await auth_client.patch(f"{URL}/{variant.id}", json=payload, headers=admin.headers)
    again = await auth_client.patch(f"{URL}/{variant.id}", json=payload, headers=admin.headers)

    assert first.status_code == 200, first.text
    body = _error(again, 409, "CONFLICT")
    assert body["details"][0]["type"] == "stale_total"
    item = await _item(db_engine, variant.id)
    assert item.total_quantity == 7
    assert await _actions(db_engine, item.id) == ["inventory.adjusted"]


async def test_patch_errors(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    product = await catalog.product()
    variant = await catalog.variant(product, stock=(5, 0, 0))
    gone = await catalog.variant(product, stock=(5, 0, 0))
    await catalog.set(ProductVariant, gone.id, deleted_at=utc_now())
    await _reserve(db_engine, variant.id, 3)
    url = f"{URL}/{variant.id}"

    for body in (
        {"reason": "nothing to do"},
        {"adjustment_type": "increase", "reason": "no quantity"},
        {"quantity": 1, "reason": "no type"},
        {"adjustment_type": "increase", "quantity": 1},
        {"adjustment_type": "increase", "quantity": 1, "reason": "   "},
        {"adjustment_type": "increase", "quantity": 0, "reason": "zero"},
        {"adjustment_type": "increase", "quantity": 1.0, "reason": "float"},
        {"adjustment_type": "increase", "quantity": "1", "reason": "string"},
        {"adjustment_type": "increase", "quantity": True, "reason": "bool"},
        {"adjustment_type": "reserve", "quantity": 1, "reason": "internal type"},
        {"low_stock_threshold": -1, "reason": "negative"},
        {"low_stock_threshold": 1_000_001, "reason": "above the cap"},
        {"low_stock_threshold": 1, "reason": "x", "expected_total": False},
        {"low_stock_threshold": 1, "reason": "x", "colour": "red"},
    ):
        _error(
            await auth_client.patch(url, json=body, headers=admin.headers), 400, "VALIDATION_ERROR"
        )
    for target in (uuid4(), gone.id):
        response = await auth_client.patch(
            f"{URL}/{target}",
            json={"adjustment_type": "increase", "quantity": 1, "reason": "x"},
            headers=admin.headers,
        )
        _error(response, 404, "NOT_FOUND")
    _error(
        await auth_client.patch(
            url,
            json={"adjustment_type": "decrease", "quantity": 3, "reason": "x"},
            headers=admin.headers,
        ),
        409,
        "INSUFFICIENT_STOCK",
    )
    _error(
        await auth_client.patch(
            url,
            json={"adjustment_type": "increase", "quantity": 1_000_000, "reason": "x"},
            headers=admin.headers,
        ),
        422,
        "BUSINESS_RULE_VIOLATION",
    )
    # A combined PATCH is all-or-nothing: the threshold is not kept when the decrease fails.
    _error(
        await auth_client.patch(
            url,
            json={
                "low_stock_threshold": 9,
                "adjustment_type": "decrease",
                "quantity": 3,
                "reason": "x",
            },
            headers=admin.headers,
        ),
        409,
        "INSUFFICIENT_STOCK",
    )
    item = await _item(db_engine, variant.id)
    assert (item.total_quantity, item.reserved_quantity, item.low_stock_threshold) == (5, 3, 0)
    assert await _actions(db_engine, item.id) == []


async def test_concurrent_patches_serialize(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))

    responses = await asyncio.gather(
        *(
            auth_client.patch(
                f"{URL}/{variant.id}",
                json={"adjustment_type": "decrease", "quantity": 2, "reason": "damaged"},
                headers=admin.headers,
            )
            for _ in range(4)
        )
    )

    assert sorted(response.status_code for response in responses) == [200, 200, 409, 409]
    item = await _item(db_engine, variant.id)
    assert item.total_quantity == 1
    assert (
        await _count(db_engine, InventoryMovement, InventoryMovement.inventory_item_id == item.id)
        == 2
    )


# --- reservations --------------------------------------------------------------------


async def test_reservations_show_expiry_without_the_job(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), stock=(10, 0, 0))
    active = await _reserve(db_engine, variant.id, 2)
    expired = await _reserve(db_engine, variant.id, 3, now=utc_now() - PAST)
    params = {"variant_id": str(variant.id)}

    response = await auth_client.get(f"{URL}/reservations", params=params, headers=admin.headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    rows = {row["id"]: row for row in response.json()["items"]}
    assert rows[str(active)]["status"] == "active"
    assert rows[str(expired)]["status"] == "expired"
    assert [item["status"] for item in rows[str(expired)]["items"]] == ["expired"]
    [line] = rows[str(active)]["items"]
    assert (line["variant_id"], line["sku"], line["quantity"], line["status"]) == (
        str(variant.id),
        variant.sku,
        2,
        "active",
    )
    for status, expected in (("active", active), ("expired", expired)):
        filtered = await auth_client.get(
            f"{URL}/reservations", params=params | {"status": status}, headers=admin.headers
        )
        assert [row["id"] for row in filtered.json()["items"]] == [str(expected)]
    committed = await auth_client.get(
        f"{URL}/reservations", params=params | {"status": "committed"}, headers=admin.headers
    )
    assert committed.json()["total"] == 0


async def test_reservation_list_has_no_n_plus_one(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), stock=(20, 0, 0))
    params = {"variant_id": str(variant.id)}
    await _reserve(db_engine, variant.id, 1)
    with count_queries(auth_client) as one:
        await auth_client.get(f"{URL}/reservations", params=params, headers=admin.headers)
    for _ in range(4):
        await _reserve(db_engine, variant.id, 1)
    with count_queries(auth_client) as five:
        response = await auth_client.get(
            f"{URL}/reservations", params=params, headers=admin.headers
        )
    assert response.json()["total"] == 5
    assert len(five) == len(one)


async def test_reservations_reject_bad_query(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    for params in ({"status": "done"}, {"order_id": "x"}, {"variant_id": "x"}, {"sort": "new"}):
        response = await auth_client.get(
            f"{URL}/reservations", params=params, headers=admin.headers
        )
        _error(response, 400, "VALIDATION_ERROR")


# --- history -------------------------------------------------------------------------


async def test_history_lists_movements_newest_first(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    admin = await make_account("admin")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    for quantity in (1, 2, 3):
        response = await auth_client.patch(
            f"{URL}/{variant.id}",
            json={"adjustment_type": "increase", "quantity": quantity, "reason": f"r{quantity}"},
            headers=admin.headers,
        )
        assert response.status_code == 200, response.text

    page = await auth_client.get(
        f"{URL}/{variant.id}/history", params={"limit": 2}, headers=admin.headers
    )
    rest = await auth_client.get(
        f"{URL}/{variant.id}/history", params={"limit": 2, "page": 2}, headers=admin.headers
    )

    assert page.status_code == 200, page.text
    assert page.headers["cache-control"] == "no-store"
    assert page.json()["total"] == 3
    rows = page.json()["items"] + rest.json()["items"]
    assert [row["quantity"] for row in rows] == [3, 2, 1]
    assert [(row["total_before"], row["total_after"]) for row in rows] == [
        (8, 11),
        (6, 8),
        (5, 6),
    ]
    assert rows[0]["created_by"] == str(admin.id)
    assert rows[0]["reason"] == "r3"


async def test_history_of_unstocked_deleted_and_missing_variants(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    admin = await make_account("admin")
    product = await catalog.product()
    unstocked = await catalog.variant(product)
    deleted = await catalog.variant(product, stock=(1, 0, 0))
    await catalog.set(ProductVariant, deleted.id, deleted_at=utc_now())

    for variant_id in (unstocked.id, deleted.id):
        response = await auth_client.get(f"{URL}/{variant_id}/history", headers=admin.headers)
        assert (response.status_code, response.json()["total"]) == (200, 0)
    _error(
        await auth_client.get(f"{URL}/{uuid4()}/history", headers=admin.headers), 404, "NOT_FOUND"
    )
    _error(
        await auth_client.get(f"{URL}/not-a-uuid/history", headers=admin.headers),
        400,
        "VALIDATION_ERROR",
    )
    _error(
        await auth_client.get(
            f"{URL}/{unstocked.id}/history", params={"q": "x"}, headers=admin.headers
        ),
        400,
        "VALIDATION_ERROR",
    )


# --- authorization -------------------------------------------------------------------


async def test_endpoints_need_inventory_permissions_before_validation(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    target = uuid4()
    calls = [
        ("GET", URL, {"bogus": "1"}),
        ("GET", f"{URL}/reservations", {"bogus": "1"}),
        ("GET", f"{URL}/{target}/history", {"bogus": "1"}),
        ("PATCH", f"{URL}/{target}", None),
    ]

    async def call(method: str, url: str, params: Any, headers: dict[str, str]) -> Response:
        if method == "GET":
            return await auth_client.get(url, params=params, headers=headers)
        return await auth_client.patch(url, json={"quantity": "x"}, headers=headers)

    for method, url, params in calls:
        _error(await call(method, url, params, {}), 401, "UNAUTHORIZED")
    for role in ("content_manager", "support", "customer"):
        actor = await make_account(role)
        for method, url, params in calls:
            _error(await call(method, url, params, actor.headers), 403, "FORBIDDEN")


# --- error coverage map (CAT-12 style) -----------------------------------------------

STATUSES = (400, 401, 403, 404, 409, 422)
AUTH = "test_endpoints_need_inventory_permissions_before_validation"
READ_ONLY = "n/a: read-only, no state to conflict with"
COLLECTION = "n/a: collection endpoint, nothing to look up"
COVERAGE: dict[tuple[str, str], dict[int, str]] = {
    ("GET", "/admin/inventory"): {
        400: "test_list_rejects_bad_query",
        404: COLLECTION,
        409: READ_ONLY,
        422: READ_ONLY,
    },
    ("GET", "/admin/inventory/reservations"): {
        400: "test_reservations_reject_bad_query",
        404: COLLECTION,
        409: READ_ONLY,
        422: READ_ONLY,
    },
    ("GET", "/admin/inventory/{variant_id}/history"): {
        400: "test_history_of_unstocked_deleted_and_missing_variants",
        404: "test_history_of_unstocked_deleted_and_missing_variants",
        409: READ_ONLY,
        422: READ_ONLY,
    },
    ("PATCH", "/admin/inventory/{variant_id}"): {
        400: "test_patch_errors",
        404: "test_patch_errors",
        409: "test_patch_errors",
        422: "test_patch_errors",
    },
}


def test_coverage_map_matches_the_inventory_routes(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    routes = {
        (method.upper(), path.removeprefix("/api/v1"))
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(URL)
        for method in operations
    }
    assert routes == set(COVERAGE)


@pytest.mark.parametrize("endpoint", sorted(COVERAGE), ids=" ".join)
def test_every_status_is_tested_or_explained(endpoint: tuple[str, str]) -> None:
    cells = {401: AUTH, 403: AUTH} | COVERAGE[endpoint]
    assert sorted(cells) == list(STATUSES)
    for status, cell in cells.items():
        assert cell.startswith("n/a: ") or callable(globals().get(cell)), f"{endpoint} {status}"
