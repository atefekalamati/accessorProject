"""Staff return review, receipt and inspection (ORD-09, PRD «مرجوعی» ✓, ADR-063)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Account, Catalog, MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_create import (
    MakeBuyer,
    _error,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)
from test_returns import Delivered, _count, _keys, _order

from app.core.time import utc_now
from app.db.models import (
    AuditLog,
    InventoryItem,
    InventoryMovement,
    OrderItem,
    ProductVariant,
    ReturnItem,
    ReturnRequest,
    ReturnStatusHistory,
)
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID
from app.shared.inventory import MAX_STOCK_QUANTITY

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

ADMIN = "/api/v1/admin/returns"
RETURNS = "/api/v1/returns"
ACTIONS = ("approve", "reject", "receive", "inspect")


class Staff:
    def __init__(self, client: AsyncClient, account: Account) -> None:
        self.client, self.account = client, account

    async def act(
        self, return_id: str, action: str, body: dict[str, Any] | None = None
    ) -> Response:
        if body is None:
            body = {"reject_reason": "Outside policy"} if action == "reject" else {}
        return await self.client.post(
            f"{ADMIN}/{return_id}/{action}", json=body, headers=self.account.headers
        )

    async def get(self, path: str = "", **params: Any) -> Response:
        return await self.client.get(ADMIN + path, params=params, headers=self.account.headers)


@pytest.fixture
async def staff(auth_client: AsyncClient, make_account: MakeAccount) -> Staff:
    return Staff(auth_client, await make_account("support"))


async def _requested(
    catalog: Catalog,
    buyer: MakeBuyer,
    engine: AsyncEngine,
    *,
    quantities: tuple[int, ...] = (3,),
    claim: tuple[int, ...] | None = None,
) -> tuple[Delivered, str]:
    order = await _order(catalog, buyer, engine, quantities=quantities)
    claim = claim or tuple(1 for _ in quantities)
    body = {
        "items": [{"order_item_id": order.line(i), "quantity": q} for i, q in enumerate(claim)],
        "reason": "defective",
    }
    created = await order.create(body)
    assert created.status_code == 201, created.text
    return order, created.json()["id"]


async def _received(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, engine: AsyncEngine, **kwargs: Any
) -> tuple[Delivered, str]:
    order, return_id = await _requested(catalog, buyer, engine, **kwargs)
    for action in ("approve", "receive"):
        response = await staff.act(return_id, action)
        assert response.status_code == 200, response.text
    return order, return_id


def _line(order: Delivered, index: int = 0, **fields: Any) -> dict[str, Any]:
    return {"order_item_id": order.line(index), "condition": "sellable", "accepted_quantity": 1} | (
        fields
    )


async def _variant(engine: AsyncEngine, order_item_id: str) -> UUID:
    async with AsyncSession(engine) as session:
        found = await session.scalar(
            select(OrderItem.variant_id).where(OrderItem.id == UUID(order_item_id))
        )
    assert found is not None
    return found


async def _stock(engine: AsyncEngine, variant_id: UUID) -> tuple[int, int]:
    async with AsyncSession(engine) as session:
        item = (
            await session.scalars(
                select(InventoryItem).where(
                    InventoryItem.variant_id == variant_id,
                    InventoryItem.warehouse_id == DEFAULT_WAREHOUSE_ID,
                )
            )
        ).one()
        return item.total_quantity, item.reserved_quantity


async def _movements(engine: AsyncEngine, return_id: str) -> list[InventoryMovement]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(InventoryMovement).where(
                    InventoryMovement.reference_type == "return",
                    InventoryMovement.reference_id == UUID(return_id),
                )
            )
        )


async def _audits(engine: AsyncEngine, return_id: str, action: str) -> list[AuditLog]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == UUID(return_id), AuditLog.action == action
                )
            )
        )


def _lines(audit: AuditLog) -> Any:
    return audit.metadata_["diff"]["lines"]["after"]


async def _history(engine: AsyncEngine, return_id: str) -> int:
    return await _count(
        engine, ReturnStatusHistory, ReturnStatusHistory.return_request_id == UUID(return_id)
    )


# --- transitions -----------------------------------------------------------------------


async def test_approve_receive_inspect_restocks_sellable_units(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _requested(catalog, buyer, db_engine, claim=(2,))
    variant_id = await _variant(db_engine, order.line())
    before = await _stock(db_engine, variant_id)

    approved = await staff.act(return_id, "approve", {"admin_note": " checked photos "})
    assert approved.status_code == 200, approved.text
    assert approved.headers["cache-control"] == "no-store"
    body = approved.json()
    assert (body["status"], body["admin_note"]) == ("approved", "checked photos")
    assert body["decided_by"] == str(staff.account.id) and body["decided_at"] is not None
    # Repeating the same transition answers 200 unchanged: no new history or audit.
    again = await staff.act(return_id, "approve", {"admin_note": "other"})
    assert again.status_code == 200 and again.json()["admin_note"] == "checked photos"
    assert len(await _audits(db_engine, return_id, "return.approved")) == 1

    received = await staff.act(return_id, "receive")
    assert received.status_code == 200 and received.json()["received_at"] is not None
    assert (await staff.act(return_id, "receive")).status_code == 200
    assert await _history(db_engine, return_id) == 3  # requested, approved, received

    inspected = await staff.act(
        return_id,
        "inspect",
        {"items": [_line(order, accepted_quantity=2, note=" box opened ")], "admin_note": "ok"},
    )
    assert inspected.status_code == 200, inspected.text
    detail = inspected.json()
    assert detail["status"] == "inspected" and detail["inspected_at"] is not None
    [item] = detail["items"]
    assert (item["condition"], item["accepted_quantity"], item["refundable"]) == (
        "sellable",
        2,
        True,
    )
    assert item["inspection_note"] == "box opened"
    [movement] = await _movements(db_engine, return_id)
    assert item["inventory_movement_id"] == str(movement.id)
    assert (movement.movement_type, movement.quantity, movement.created_by) == (
        "return",
        2,
        staff.account.id,
    )
    assert await _stock(db_engine, variant_id) == (before[0] + 2, before[1])
    [audit] = await _audits(db_engine, return_id, "return.inspected")
    assert _lines(audit) == [
        {
            "order_item_id": order.line(),
            "condition": "sellable",
            "accepted_quantity": 2,
            "refundable": True,
            "restocked": 2,
            "restock_skipped": False,
        }
    ]
    assert "box opened" not in str(audit.metadata_) and "admin_note" not in str(audit.metadata_)
    for action in ("return.approved", "return.received"):
        assert len(await _audits(db_engine, return_id, action)) == 1

    # Inspecting again (retry) is 422 and restocks nothing.
    retry = await staff.act(return_id, "inspect", {"items": [_line(order, accepted_quantity=2)]})
    _error(retry, 422, "INVALID_STATE_TRANSITION")
    assert len(await _movements(db_engine, return_id)) == 1

    # The customer sees the outcome but none of the staff fields.
    mine = await order.ready.client.get(f"{RETURNS}/{return_id}", headers=order.headers)
    assert mine.json()["status"] == "inspected"
    assert not {"admin_note", "inspection_note", "decided_by"} & _keys(mine.json())
    staff_view = await staff.get(f"/{return_id}")
    assert staff_view.status_code == 200 and staff_view.headers["cache-control"] == "no-store"
    assert staff_view.json() == detail
    assert not {"phone", "mobile"} & _keys(detail)
    assert [row["actor_user_id"] for row in detail["history"]][1:] == [str(staff.account.id)] * 3


async def test_reject_and_invalid_transitions(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _requested(catalog, buyer, db_engine)
    _error(await staff.act(return_id, "receive"), 422, "INVALID_STATE_TRANSITION")
    _error(
        await staff.act(return_id, "inspect", {"items": [_line(order)]}),
        422,
        "INVALID_STATE_TRANSITION",
    )

    rejected = await staff.act(
        return_id, "reject", {"reject_reason": " Used item ", "admin_note": "worn"}
    )
    assert rejected.status_code == 200, rejected.text
    assert (rejected.json()["status"], rejected.json()["reject_reason"]) == (
        "rejected",
        "Used item",
    )
    repeat = await staff.act(return_id, "reject", {"reject_reason": "Another reason"})
    assert repeat.status_code == 200 and repeat.json()["reject_reason"] == "Used item"
    assert len(await _audits(db_engine, return_id, "return.rejected")) == 1
    for action in ("approve", "receive"):
        _error(await staff.act(return_id, action), 422, "INVALID_STATE_TRANSITION")
    mine = await order.ready.client.get(f"{RETURNS}/{return_id}", headers=order.headers)
    assert mine.json()["reject_reason"] == "Used item"

    # A customer-cancelled request cannot be approved.
    other, cancelled = await _requested(catalog, buyer, db_engine)
    await other.ready.client.post(f"{RETURNS}/{cancelled}/cancel", headers=other.headers)
    _error(await staff.act(cancelled, "approve"), 422, "INVALID_STATE_TRANSITION")
    _error(await staff.act(cancelled, "reject"), 422, "INVALID_STATE_TRANSITION")


async def test_body_validation(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _requested(catalog, buyer, db_engine)
    bad: list[tuple[str, dict[str, Any]]] = [
        ("approve", {"admin_note": "  "}),
        ("approve", {"admin_note": "x" * 2001}),
        ("approve", {"status": "refunded"}),
        ("reject", {}),
        ("reject", {"reject_reason": " "}),
        ("reject", {"reject_reason": "x" * 1001}),
        ("reject", {"reject_reason": "bad\x00"}),
        ("receive", {"received_at": "2026-01-01T00:00:00Z"}),
    ]
    for action, body in bad:
        _error(await staff.act(return_id, action, body), 400, "VALIDATION_ERROR")
    _error(
        await staff.client.post(
            f"{ADMIN}/{return_id}/approve",
            params={"x": "1"},
            json={},
            headers=staff.account.headers,
        ),
        400,
        "VALIDATION_ERROR",
    )
    assert await _history(db_engine, return_id) == 1


async def test_inspect_validation(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _received(
        staff, catalog, buyer, db_engine, quantities=(3, 2), claim=(2, 1)
    )
    first, second = _line(order, 0), _line(order, 1)
    bad: list[dict[str, Any]] = [
        {"items": []},
        {"items": [first]},  # a line missing
        {"items": [first, second, _line(order, 0)]},  # duplicate
        {"items": [first, second | {"order_item_id": str(uuid4())}]},  # foreign line
        {"items": [first | {"accepted_quantity": 3}, second]},  # more than requested
        {"items": [first | {"accepted_quantity": -1}, second]},
        {"items": [first | {"accepted_quantity": "1"}, second]},
        {"items": [first | {"refundable": False}, second]},  # sellable is refundable
        {"items": [first | {"condition": "damaged"}, second]},  # damaged must say
        {"items": [first | {"condition": "lost"}, second]},
        {"items": [first | {"note": " "}, second]},
        {"items": [first | {"note": "x" * 2001}, second]},
        {"items": [first | {"refund_amount": 1}, second]},
        {"items": [first, second], "status": "closed"},
    ]
    for body in bad:
        _error(await staff.act(return_id, "inspect", body), 400, "VALIDATION_ERROR")
    assert await _history(db_engine, return_id) == 3
    assert await _movements(db_engine, return_id) == []


async def test_damaged_and_zero_lines_restock_nothing(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _received(
        staff, catalog, buyer, db_engine, quantities=(3, 2), claim=(2, 1)
    )
    variants = [await _variant(db_engine, order.line(i)) for i in (0, 1)]
    before = [await _stock(db_engine, v) for v in variants]

    inspected = await staff.act(
        return_id,
        "inspect",
        {
            "items": [
                _line(order, 0, condition="damaged", accepted_quantity=2, refundable=False),
                _line(order, 1, accepted_quantity=0),
            ]
        },
    )

    assert inspected.status_code == 200, inspected.text
    items = inspected.json()["items"]
    assert [(i["condition"], i["refundable"], i["inventory_movement_id"]) for i in items] == [
        ("damaged", False, None),
        ("sellable", True, None),
    ]
    assert await _movements(db_engine, return_id) == []
    assert [await _stock(db_engine, v) for v in variants] == before


async def test_two_lines_of_one_variant_get_a_movement_each(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order = await _order(catalog, buyer, db_engine, quantities=(3, 2))
    variant_id = await _variant(db_engine, order.line(0))
    # The schema allows two lines of one variant; make the second line point at the first.
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(OrderItem)
            .where(OrderItem.id == UUID(order.line(1)))
            .values(variant_id=variant_id)
        )
    body = {
        "items": [
            {"order_item_id": order.line(0), "quantity": 2},
            {"order_item_id": order.line(1), "quantity": 1},
        ],
        "reason": "defective",
    }
    created = await order.create(body)
    assert created.status_code == 201, created.text
    return_id = created.json()["id"]
    for action in ("approve", "receive"):
        assert (await staff.act(return_id, action)).status_code == 200
    before = await _stock(db_engine, variant_id)

    inspected = await staff.act(
        return_id, "inspect", {"items": [_line(order, 0, accepted_quantity=2), _line(order, 1)]}
    )

    assert inspected.status_code == 200, inspected.text
    movements = await _movements(db_engine, return_id)
    assert sorted(m.quantity for m in movements) == [1, 2]
    linked = {i["order_item_id"]: i["inventory_movement_id"] for i in inspected.json()["items"]}
    by_id = {str(m.id): m.quantity for m in movements}
    assert {line: by_id[str(m)] for line, m in linked.items()} == {
        order.line(0): 2,
        order.line(1): 1,
    }
    assert await _stock(db_engine, variant_id) == (before[0] + 3, before[1])
    [audit] = await _audits(db_engine, return_id, "return.inspected")
    assert {line["order_item_id"]: line["restocked"] for line in _lines(audit)} == {
        order.line(0): 2,
        order.line(1): 1,
    }


async def test_deleted_variant_is_inspected_without_restock(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _received(staff, catalog, buyer, db_engine)
    variant_id = await _variant(db_engine, order.line())
    before = await _stock(db_engine, variant_id)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(ProductVariant)
            .where(ProductVariant.id == variant_id)
            .values(deleted_at=utc_now())
        )

    inspected = await staff.act(return_id, "inspect", {"items": [_line(order)]})

    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["items"][0]["inventory_movement_id"] is None
    assert await _movements(db_engine, return_id) == []
    assert await _stock(db_engine, variant_id) == before
    [audit] = await _audits(db_engine, return_id, "return.inspected")
    [line] = _lines(audit)
    assert (line["restocked"], line["restock_skipped"]) == (0, True)


async def test_stock_limit_writes_nothing(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _received(staff, catalog, buyer, db_engine)
    variant_id = await _variant(db_engine, order.line())
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(InventoryItem)
            .where(InventoryItem.variant_id == variant_id)
            .values(total_quantity=MAX_STOCK_QUANTITY)
        )

    response = await staff.act(return_id, "inspect", {"items": [_line(order)]})

    _error(response, 422, "BUSINESS_RULE_VIOLATION")
    assert response.json()["error"]["details"][0]["type"] == "stock_limit"
    assert await _movements(db_engine, return_id) == []
    assert await _history(db_engine, return_id) == 3
    async with AsyncSession(db_engine) as session:
        found = await session.get(ReturnRequest, UUID(return_id))
        items = list(
            await session.scalars(
                select(ReturnItem).where(ReturnItem.return_request_id == UUID(return_id))
            )
        )
    assert found is not None and found.status == "received"
    assert [item.condition for item in items] == [None]


# --- concurrency -------------------------------------------------------------------------


async def test_concurrent_inspects_restock_once(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _received(staff, catalog, buyer, db_engine, claim=(2,))
    variant_id = await _variant(db_engine, order.line())
    before = await _stock(db_engine, variant_id)
    body = {"items": [_line(order, accepted_quantity=2)]}

    responses = await asyncio.gather(*(staff.act(return_id, "inspect", body) for _ in range(3)))

    assert sorted(r.status_code for r in responses) == [200, 422, 422]
    assert len(await _movements(db_engine, return_id)) == 1
    assert await _stock(db_engine, variant_id) == (before[0] + 2, before[1])
    assert len(await _audits(db_engine, return_id, "return.inspected")) == 1


async def test_approve_racing_customer_cancel_has_one_winner(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _requested(catalog, buyer, db_engine)

    approve, cancel = await asyncio.gather(
        staff.act(return_id, "approve"),
        order.ready.client.post(f"{RETURNS}/{return_id}/cancel", headers=order.headers),
    )

    assert sorted([approve.status_code, cancel.status_code]) == [200, 422]
    async with AsyncSession(db_engine) as session:
        found = await session.get(ReturnRequest, UUID(return_id))
    assert found is not None
    assert found.status == ("approved" if approve.status_code == 200 else "cancelled")
    assert await _history(db_engine, return_id) == 2


async def test_inspect_racing_an_order_and_a_stock_adjustment(
    staff: Staff,
    catalog: Catalog,
    buyer: MakeBuyer,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
) -> None:
    order, return_id = await _received(staff, catalog, buyer, db_engine)
    variant_id = await _variant(db_engine, order.line())
    async with AsyncSession(db_engine) as session:
        variant = await session.get(ProductVariant, variant_id)
    assert variant is not None
    other = await buyer((variant, 1))
    fingerprint = (await other.quote())["fingerprint"]
    admin = await make_account("admin")
    before = await _stock(db_engine, variant_id)

    inspected, placed, adjusted = await asyncio.wait_for(
        asyncio.gather(
            staff.act(return_id, "inspect", {"items": [_line(order)]}),
            other.order(fingerprint=fingerprint),
            staff.client.patch(
                f"/api/v1/admin/inventory/{variant_id}",
                json={"adjustment_type": "increase", "quantity": 1, "reason": "count"},
                headers=admin.headers,
            ),
        ),
        timeout=30,
    )

    assert (inspected.status_code, placed.status_code, adjusted.status_code) == (200, 201, 200), (
        inspected.text,
        placed.text,
        adjusted.text,
    )
    assert await _stock(db_engine, variant_id) == (before[0] + 2, before[1] + 1)


# --- access, list ------------------------------------------------------------------------


async def test_auth_and_permissions(
    staff: Staff,
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    order, return_id = await _requested(catalog, buyer, db_engine)
    routes: list[tuple[str, str]] = [("GET", ""), ("GET", f"/{return_id}")] + [
        ("POST", f"/{return_id}/{action}") for action in ACTIONS
    ]
    customer = order.headers
    content = (await make_account("content_manager")).headers
    for method, path in routes:
        assert (await auth_client.request(method, ADMIN + path, json={})).status_code == 401
        for headers in (customer, content):
            response = await auth_client.request(method, ADMIN + path, json={}, headers=headers)
            _error(response, 403, "FORBIDDEN")
    missing = str(uuid4())
    _error(await staff.get(f"/{missing}"), 404, "NOT_FOUND")
    for action in ACTIONS:
        body = {"items": [_line(order)]} if action == "inspect" else None
        _error(await staff.act(missing, action, body), 404, "NOT_FOUND")
    # Admin and super admin act too.
    for role in ("admin", "super_admin"):
        account = await make_account(role)
        listed = await auth_client.get(ADMIN, headers=account.headers)
        assert listed.status_code == 200
    assert await _history(db_engine, return_id) == 1


async def test_list_filters_and_sort(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, first = await _requested(catalog, buyer, db_engine, quantities=(3,), claim=(1,))
    second = (await order.create(order.body(2))).json()["id"]
    await staff.act(first, "approve")

    newest = await staff.get(limit=100)
    assert newest.status_code == 200 and newest.headers["cache-control"] == "no-store"
    ids = [row["id"] for row in newest.json()["items"]]
    assert ids.index(second) < ids.index(first)
    row = next(row for row in newest.json()["items"] if row["id"] == second)
    assert (row["order_number"], row["item_count"], row["status"]) == (
        order.number,
        2,
        "requested",
    )
    oldest = [row["id"] for row in (await staff.get(sort="oldest", limit=100)).json()["items"]]
    mine = [i for i in oldest if i in (first, second)]
    assert mine == [first, second] or len(mine) < 2  # older rows may fill the page
    approved = (await staff.get(status="approved", limit=100)).json()["items"]
    assert first in {row["id"] for row in approved}
    assert all(row["status"] == "approved" for row in approved)
    for params in ({"sort": "price"}, {"status": "lost"}, {"limit": 1000}, {"foo": "1"}):
        _error(await staff.get(**params), 400, "VALIDATION_ERROR")
    _error(await staff.get(f"/{first}", x="1"), 400, "VALIDATION_ERROR")
