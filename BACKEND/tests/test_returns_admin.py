"""Staff return review, inspection and refund (ORD-09, ORD-10, PRD «مرجوعی» ✓, ADR-063)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Account, Catalog, MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_admin_refunds import _late_paid
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
    Order,
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
ACTIONS = ("approve", "reject", "receive", "inspect", "refund")


class Staff:
    def __init__(self, client: AsyncClient, account: Account) -> None:
        self.client, self.account = client, account

    async def act(
        self, return_id: str, action: str, body: dict[str, Any] | None = None
    ) -> Response:
        if body is None:
            body = {
                "reject": {"reject_reason": "Outside policy"},
                "refund": {"refund_reference": f"BANK-{uuid4().hex[:12]}"},
            }.get(action, {})
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
    assert detail["status"] == "refund_required" and detail["inspected_at"] is not None
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
            "refund_amount": item["refund_amount"],
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
    assert mine.json()["status"] == "refund_required"
    assert not {"admin_note", "inspection_note", "decided_by"} & _keys(mine.json())
    staff_view = await staff.get(f"/{return_id}")
    assert staff_view.status_code == 200 and staff_view.headers["cache-control"] == "no-store"
    assert staff_view.json() == detail
    assert not {"phone", "mobile"} & _keys(detail)
    assert [row["actor_user_id"] for row in detail["history"]][1:] == [str(staff.account.id)] * 4


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
    for action in ACTIONS[:-1]:  # refund needs payments:refund (support: 403 above)
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


# --- refund (ORD-10) -------------------------------------------------------------------


async def _lines_of(engine: AsyncEngine, order: Delivered) -> dict[str, OrderItem]:
    async with AsyncSession(engine) as session:
        rows = await session.scalars(select(OrderItem).where(OrderItem.order_id == order.order_id))
        return {str(line.id): line for line in rows}


async def test_inspection_sets_server_refund_amounts(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _received(
        staff, catalog, buyer, db_engine, quantities=(3, 2), claim=(2, 2)
    )
    lines = await _lines_of(db_engine, order)

    inspected = await staff.act(
        return_id,
        "inspect",
        {
            "items": [
                _line(order, 0, accepted_quantity=2),
                _line(order, 1, condition="damaged", accepted_quantity=2, refundable=True),
            ]
        },
    )

    assert inspected.status_code == 200, inspected.text
    body = inspected.json()
    # floor(final_line_total × 2 ÷ purchased): a partial line rounds down, a whole one is exact.
    expected = {
        line_id: line.final_line_total * 2 // line.quantity for line_id, line in lines.items()
    }
    assert sorted(line.quantity for line in lines.values()) == [2, 3]
    assert {item["order_item_id"]: item["refund_amount"] for item in body["items"]} == expected
    whole = next(line for line in lines.values() if line.quantity == 2)
    assert expected[str(whole.id)] == whole.final_line_total
    expected_total = sum(expected.values())
    assert (body["status"], body["refund_amount"]) == ("refund_required", expected_total)
    assert [row["new_status"] for row in body["history"]][-2:] == ["inspected", "refund_required"]
    [audit] = await _audits(db_engine, return_id, "return.inspected")
    assert audit.metadata_["diff"]["refund_amount"]["after"] == expected_total
    mine = await order.ready.client.get(f"{RETURNS}/{return_id}", headers=order.headers)
    assert mine.json()["refund_amount"] == expected_total


async def test_nothing_refundable_closes_the_request(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _received(staff, catalog, buyer, db_engine)

    inspected = await staff.act(
        return_id, "inspect", {"items": [_line(order, condition="damaged", refundable=False)]}
    )

    assert inspected.status_code == 200, inspected.text
    assert (inspected.json()["status"], inspected.json()["refund_amount"]) == ("closed", 0)


@pytest.fixture
async def treasurer(auth_client: AsyncClient, make_account: MakeAccount) -> Staff:
    return Staff(auth_client, await make_account("admin"))


async def _refund_required(
    staff: Staff, catalog: Catalog, buyer: MakeBuyer, engine: AsyncEngine
) -> tuple[Delivered, str]:
    order, return_id = await _received(staff, catalog, buyer, engine)
    inspected = await staff.act(return_id, "inspect", {"items": [_line(order)]})
    assert inspected.json()["status"] == "refund_required", inspected.text
    return order, return_id


async def test_refund_record_is_idempotent_and_keeps_the_payment(
    staff: Staff, treasurer: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _refund_required(staff, catalog, buyer, db_engine)
    reference = f"BANK-{uuid4().hex[:10]}"

    # Support reviews returns but cannot record money (payments:refund).
    _error(await staff.act(return_id, "refund"), 403, "FORBIDDEN")
    bad: list[dict[str, Any]] = [
        {},
        {"refund_reference": " "},
        {"refund_reference": "x" * 101},
        {"refund_reference": "BAD\x00"},
        {"refund_reference": reference, "amount": 1},  # the amount is the server's
        {"refund_reference": reference, "note": "n" * 501},
    ]
    for body in bad:
        _error(await treasurer.act(return_id, "refund", body), 400, "VALIDATION_ERROR")

    refunded = await treasurer.act(return_id, "refund", {"refund_reference": f" {reference} "})
    assert refunded.status_code == 200, refunded.text
    body = refunded.json()
    assert (body["status"], body["refund_reference"], body["refunded_by"]) == (
        "refunded",
        reference,
        str(treasurer.account.id),
    )
    assert body["refunded_at"] is not None and body["refund_amount"] > 0
    again = await treasurer.act(return_id, "refund", {"refund_reference": reference})
    assert again.status_code == 200 and again.json() == body
    other = await treasurer.act(return_id, "refund", {"refund_reference": "BANK-OTHER"})
    _error(other, 409, "CONFLICT")
    assert other.json()["error"]["details"][0]["type"] == "already_refunded"
    assert len(await _audits(db_engine, return_id, "return.refunded")) == 1

    async with AsyncSession(db_engine) as session:
        found = await session.get(Order, order.order_id)
    assert found is not None and found.payment_status == "paid"  # partial: unchanged
    mine = await order.ready.client.get(f"{RETURNS}/{return_id}", headers=order.headers)
    assert (mine.json()["status"], mine.json()["refund_amount"]) == (
        "refunded",
        body["refund_amount"],
    )
    assert "refund_reference" not in _keys(mine.json())


async def test_refund_from_other_statuses_is_422(
    staff: Staff, treasurer: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _received(staff, catalog, buyer, db_engine)
    _error(await treasurer.act(return_id, "refund"), 422, "INVALID_STATE_TRANSITION")
    await staff.act(
        return_id, "inspect", {"items": [_line(order, condition="damaged", refundable=False)]}
    )
    _error(await treasurer.act(return_id, "refund"), 422, "INVALID_STATE_TRANSITION")
    _error(await treasurer.act(str(uuid4()), "refund"), 404, "NOT_FOUND")


async def test_refund_reference_is_unique(
    staff: Staff, treasurer: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, first = await _refund_required(staff, catalog, buyer, db_engine)
    _, second = await _refund_required(staff, catalog, buyer, db_engine)
    reference = f"BANK-{uuid4().hex[:10]}"
    assert (
        await treasurer.act(first, "refund", {"refund_reference": reference})
    ).status_code == 200

    taken = await treasurer.act(second, "refund", {"refund_reference": reference})

    _error(taken, 409, "CONFLICT")
    assert taken.json()["error"]["details"][0]["type"] == "refund_reference_taken"
    assert len(await _audits(db_engine, second, "return.refunded")) == 0


async def test_concurrent_refund_records_change_once(
    staff: Staff, treasurer: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    _, return_id = await _refund_required(staff, catalog, buyer, db_engine)
    _, other_id = await _refund_required(staff, catalog, buyer, db_engine)
    same = f"BANK-{uuid4().hex[:10]}"

    different = await asyncio.gather(
        *(
            treasurer.act(return_id, "refund", {"refund_reference": f"BANK-{uuid4().hex[:10]}"})
            for _ in range(3)
        )
    )
    shared = await asyncio.gather(
        *(treasurer.act(other_id, "refund", {"refund_reference": same}) for _ in range(2))
    )

    assert sorted(r.status_code for r in different) == [200, 409, 409]
    assert [r.status_code for r in shared] == [200, 200]
    for request_id in (return_id, other_id):
        assert len(await _audits(db_engine, request_id, "return.refunded")) == 1


async def test_one_reference_on_two_returns_at_once(
    staff: Staff, treasurer: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    """Two orders, so no shared lock: the unique index decides (savepoint path)."""
    _, first = await _refund_required(staff, catalog, buyer, db_engine)
    _, second = await _refund_required(staff, catalog, buyer, db_engine)
    reference = f"BANK-{uuid4().hex[:10]}"

    responses = await asyncio.gather(
        *(treasurer.act(i, "refund", {"refund_reference": reference}) for i in (first, second))
    )

    assert sorted(r.status_code for r in responses) == [200, 409]
    lost = next(r for r in responses if r.status_code == 409)
    assert lost.json()["error"]["details"][0]["type"] == "refund_reference_taken"
    audits = [len(await _audits(db_engine, i, "return.refunded")) for i in (first, second)]
    assert sorted(audits) == [0, 1]


async def test_a_reference_is_one_refund_across_payments_and_returns(
    staff: Staff,
    treasurer: Staff,
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    _, first = await _refund_required(staff, catalog, buyer, db_engine)
    _, second = await _refund_required(staff, catalog, buyer, db_engine)
    _ready, _order_id, payment = await _late_paid(auth_client, catalog, buyer, db_engine)
    _r2, _o2, other_payment = await _late_paid(auth_client, catalog, buyer, db_engine)
    on_payment, on_return = f"BANK-{uuid4().hex[:10]}", f"BANK-{uuid4().hex[:10]}"

    async def refund_payment(payment_id: UUID, reference: str) -> Response:
        return await auth_client.post(
            f"/api/v1/admin/payments/{payment_id}/refund",
            json={"refund_reference": reference},
            headers=treasurer.account.headers,
        )

    assert (await refund_payment(payment.id, on_payment)).status_code == 200
    taken = await treasurer.act(first, "refund", {"refund_reference": on_payment})
    _error(taken, 409, "CONFLICT")
    assert taken.json()["error"]["details"][0]["type"] == "refund_reference_taken"

    assert (
        await treasurer.act(second, "refund", {"refund_reference": on_return})
    ).status_code == 200
    reverse = await refund_payment(other_payment.id, on_return)
    _error(reverse, 409, "CONFLICT")
    assert reverse.json()["error"]["details"][0]["type"] == "refund_reference_taken"


async def test_no_return_refund_once_the_order_is_refunded(
    staff: Staff, treasurer: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order, return_id = await _refund_required(staff, catalog, buyer, db_engine)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(Order).where(Order.id == order.order_id).values(payment_status="refunded")
        )

    response = await treasurer.act(return_id, "refund")

    _error(response, 422, "BUSINESS_RULE_VIOLATION")
    assert response.json()["error"]["details"][0]["type"] == "order_not_paid"
    assert len(await _audits(db_engine, return_id, "return.refunded")) == 0


async def test_sales_report_shows_return_refunds_apart(
    staff: Staff, treasurer: Staff, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    today = utc_now().date()
    params = {"from": str(today - timedelta(days=1)), "to": str(today + timedelta(days=2))}

    async def report() -> dict[str, Any]:
        response = await treasurer.client.get(
            "/api/v1/admin/reports/sales", params=params, headers=treasurer.account.headers
        )
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result

    before = await report()
    _, return_id = await _refund_required(staff, catalog, buyer, db_engine)
    refunded = await treasurer.act(return_id, "refund")
    assert refunded.status_code == 200, refunded.text
    after = await report()

    assert after["return_refunds"] == {
        "count": before["return_refunds"]["count"] + 1,
        "amount": before["return_refunds"]["amount"] + refunded.json()["refund_amount"],
    }
    assert after["totals"] == before["totals"]  # sales are not reduced
