"""Customer return requests (ORD-08, PRD «مرجوعی» ✓, ADR-063)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog
from httpx import Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_create import (
    ORDERS,
    Buyer,
    MakeBuyer,
    _error,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)

from app.core.errors import BusinessRuleError
from app.core.time import utc_now
from app.db.models import (
    AuditLog,
    IdempotencyKey,
    Order,
    ReturnItem,
    ReturnRequest,
    ReturnStatus,
    ReturnStatusHistory,
    Shipment,
)
from app.modules.orders.cancel import order_advisory_lock
from app.modules.returns.state import (
    OPEN_STATUSES,
    TRANSITIONS,
    can_transition,
    check_transition,
    return_deadline,
    returnable_quantity,
    window_open,
)

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

RETURNS = "/api/v1/returns"
WINDOW = timedelta(days=7)  # RETURN_WINDOW_DAYS default
# Never shown to the customer.
HIDDEN = {
    "admin_note",
    "decided_by",
    "decided_at",
    "refunded_by",
    "refund_reference",
    "inspection_note",
    "condition",
    "refundable",
    "inventory_movement_id",
    "actor_user_id",
    "user_id",
}


class Delivered:
    """A placed order of ``buyer`` marked delivered, with its line ids."""

    def __init__(self, ready: Buyer, number: str, order_id: UUID, lines: list[dict[str, Any]]):
        self.ready, self.number, self.order_id, self.lines = ready, number, order_id, lines

    @property
    def headers(self) -> dict[str, str]:
        return dict(self.ready.account.headers)

    def line(self, index: int = 0) -> str:
        return str(self.lines[index]["order_item_id"])

    async def create(
        self, body: dict[str, Any] | None = None, key: str | None = None, number: str | None = None
    ) -> Response:
        headers = self.headers | {"Idempotency-Key": key or str(uuid4())}
        return await self.ready.client.post(
            f"{ORDERS}/{number or self.number}/returns",
            json=body if body is not None else self.body(),
            headers=headers,
        )

    def body(self, quantity: int = 1, index: int = 0, **extra: Any) -> dict[str, Any]:
        return {
            "items": [{"order_item_id": self.line(index), "quantity": quantity}],
            "reason": "defective",
        } | extra


async def _set_delivered(
    engine: AsyncEngine, order_id: UUID, *, at: datetime | None, row: bool = True
) -> None:
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(status="completed", payment_status="paid", shipment_status="delivered")
        )
        if row:
            shipped = (at or utc_now()) - timedelta(days=1)
            session.add(
                Shipment(
                    order_id=order_id, tracking_code="TRK-1", shipped_at=shipped, delivered_at=at
                )
            )


async def _order(
    catalog: Catalog,
    buyer: MakeBuyer,
    engine: AsyncEngine,
    *,
    quantities: tuple[int, ...] = (3,),
    delivered_at: datetime | None = None,
    deliver: bool = True,
    row: bool = True,
) -> Delivered:
    product = await catalog.product()
    variants = [await catalog.variant(product, stock=(20, 0, 0)) for _ in quantities]
    ready = await buyer(*zip(variants, quantities, strict=True))
    placed = await ready.order()
    assert placed.status_code == 201, placed.text
    number, order_id = placed.json()["order_number"], UUID(placed.json()["id"])
    if deliver:
        at = delivered_at or utc_now() - timedelta(days=1)
        await _set_delivered(engine, order_id, at=at, row=row)
    detail = await ready.client.get(f"{ORDERS}/{number}", headers=ready.account.headers)
    assert detail.status_code == 200, detail.text
    return Delivered(ready, number, order_id, detail.json()["returnable_items"])


async def _count(engine: AsyncEngine, model: Any, *where: Any) -> int:
    async with AsyncSession(engine) as session:
        return int(await session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


# --- pure rules ------------------------------------------------------------------------


def test_transition_table() -> None:
    for current, allowed in TRANSITIONS.items():
        for new in TRANSITIONS:
            assert can_transition(current, new) == (new in allowed)
    assert can_transition(ReturnStatus.REQUESTED, ReturnStatus.CANCELLED)
    assert {status.value for status in OPEN_STATUSES} == {
        "requested",
        "approved",
        "received",
        "inspected",
        "refund_required",
    }
    with pytest.raises(BusinessRuleError):
        check_transition("approved", ReturnStatus.CANCELLED)
    check_transition("requested", ReturnStatus.CANCELLED)


def test_window_and_quantity_helpers() -> None:
    delivered = datetime(2026, 11, 1, 12, tzinfo=utc_now().tzinfo)
    deadline = return_deadline(delivered, 7)
    assert deadline == delivered + WINDOW
    assert window_open(delivered, 7, deadline - timedelta(microseconds=1))
    assert not window_open(delivered, 7, deadline)  # exclusive end
    with pytest.raises(ValueError):
        return_deadline(delivered.replace(tzinfo=None), 7)
    with pytest.raises(ValueError):
        return_deadline(delivered, 0)
    assert returnable_quantity(3, 1) == 2
    assert returnable_quantity(3, 5) == 0
    with pytest.raises(ValueError):
        returnable_quantity(-1, 0)


# --- create ----------------------------------------------------------------------------


async def test_create_records_request_items_history_and_audit(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order = await _order(catalog, buyer, db_engine, quantities=(3, 2))
    body = {
        "items": [
            {"order_item_id": order.line(1), "quantity": 2},
            {"order_item_id": order.line(0), "quantity": 1},
        ],
        "reason": "wrong_item",
        "note": "  Wrong colour\nplease swap  ",
    }

    response = await order.create(body)

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    created = response.json()
    assert created["status"] == "requested"
    assert created["order_number"] == order.number
    assert created["note"] == "Wrong colour\nplease swap"
    assert created["reject_reason"] is None and created["refund_amount"] is None
    assert [(item["order_item_id"], item["quantity"]) for item in created["items"]] == [
        (order.line(0), 1),
        (order.line(1), 2),
    ]
    assert [row["status"] for row in created["history"]] == ["requested"]
    assert not _keys(created) & HIDDEN
    return_id = UUID(created["id"])
    assert await _count(db_engine, ReturnItem, ReturnItem.return_request_id == return_id) == 2
    async with AsyncSession(db_engine) as session:
        audit = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == return_id, AuditLog.action == "return.requested"
                )
            )
        ).one()
        stored = await session.get(ReturnRequest, return_id)
    assert audit.actor_user_id == order.ready.account.id
    assert "Wrong colour" not in str(audit.metadata_)  # the note is never audited
    assert stored is not None and stored.user_id == order.ready.account.id

    detail = await order.ready.client.get(f"{ORDERS}/{order.number}", headers=order.headers)
    facts = detail.json()
    assert facts["can_return"] is True
    # Line positions follow the cart, not the order of ``quantities``.
    claimed = {order.line(0): 1, order.line(1): 2}
    purchased = {item["position"]: item["quantity"] for item in facts["items"]}
    assert [line["returnable_quantity"] for line in facts["returnable_items"]] == [
        purchased[line["position"]] - claimed[str(line["order_item_id"])]
        for line in facts["returnable_items"]
    ]


async def test_replay_reuse_and_failed_key_retry(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order = await _order(catalog, buyer, db_engine, quantities=(3, 2))
    key = str(uuid4())
    two_lines: dict[str, Any] = {
        "items": [
            {"order_item_id": order.line(0), "quantity": 1},
            {"order_item_id": order.line(1), "quantity": 1},
        ],
        "reason": "defective",
    }
    first = await order.create(two_lines, key)
    # Same lines in another order: the same request.
    swapped = two_lines | {"items": list(reversed(two_lines["items"]))}
    again = await order.create(swapped, key)

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert await _count(db_engine, ReturnRequest, ReturnRequest.order_id == order.order_id) == 1
    _error(await order.create(order.body(2), key), 422, "IDEMPOTENCY_KEY_REUSED")

    # A refused request stores nothing: the same key works once the body is fixed.
    other = str(uuid4())
    _error(await order.create(order.body(9), other), 422, "BUSINESS_RULE_VIOLATION")
    assert await _count(db_engine, IdempotencyKey, IdempotencyKey.key == other) == 0
    assert (await order.create(order.body(1), other)).status_code == 201

    # A replay answers the original even after a cancel.
    cancel_url = f"{RETURNS}/{first.json()['id']}/cancel"
    assert (await order.ready.client.post(cancel_url, headers=order.headers)).status_code == 200
    replay = await order.create(two_lines, key)
    assert replay.status_code == 201 and replay.json() == first.json()


async def test_the_same_key_three_times_creates_one_request(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order = await _order(catalog, buyer, db_engine)
    key = str(uuid4())

    responses = await asyncio.gather(*(order.create(order.body(), key) for _ in range(3)))

    assert [response.status_code for response in responses] == [201, 201, 201]
    assert len({response.json()["id"] for response in responses}) == 1
    assert await _count(db_engine, ReturnRequest, ReturnRequest.order_id == order.order_id) == 1


async def test_two_requests_cannot_over_claim_a_line(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order = await _order(catalog, buyer, db_engine, quantities=(3,))

    responses = await asyncio.gather(order.create(order.body(2)), order.create(order.body(2)))

    assert sorted(response.status_code for response in responses) == [201, 422]
    refused = next(response for response in responses if response.status_code == 422)
    detail = _error(refused, 422, "BUSINESS_RULE_VIOLATION", "quantity_exceeds_returnable")
    assert detail["details"][0]["returnable_quantity"] == 1


async def test_create_racing_an_order_lock_does_not_deadlock(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    """The customer order cancel takes the same locks (advisory, then the order row) as the
    payment callback and the expiry job; a create racing it finishes either way."""
    order = await _order(catalog, buyer, db_engine)
    cancel_url = f"{ORDERS}/{order.order_id}/cancel"

    created, cancel = await asyncio.wait_for(
        asyncio.gather(order.create(), order.ready.client.post(cancel_url, headers=order.headers)),
        timeout=30,
    )

    assert created.status_code == 201
    assert cancel.status_code == 422  # a delivered order cannot be cancelled


async def test_create_waits_for_a_held_order_lock(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    """Another transaction holding the order's locks in the ADR-048 order (advisory, then
    the row ``FOR UPDATE``, as the payment callback and the expiry job do) makes a create
    wait, and it completes once that transaction ends: same order, no deadlock."""
    order = await _order(catalog, buyer, db_engine)
    async with AsyncSession(db_engine) as holder:
        async with holder.begin():
            await holder.execute(order_advisory_lock(order.order_id))
            await holder.execute(select(Order).where(Order.id == order.order_id).with_for_update())
            pending = asyncio.ensure_future(order.create())
            done, _ = await asyncio.wait({pending}, timeout=1.0)
            assert not done  # blocked behind the held locks
        created = await asyncio.wait_for(pending, timeout=30)

    assert created.status_code == 201


async def test_quantity_rules(catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine) -> None:
    order = await _order(catalog, buyer, db_engine, quantities=(2,))
    other = await _order(catalog, buyer, db_engine, quantities=(1,))
    foreign_line = {"items": [{"order_item_id": other.line(), "quantity": 1}], "reason": "other"}

    _error(await order.create(foreign_line), 422, "BUSINESS_RULE_VIOLATION", "item_not_in_order")
    first = await order.create(order.body(2))
    assert first.status_code == 201
    _error(
        await order.create(order.body(1)),
        422,
        "BUSINESS_RULE_VIOLATION",
        "quantity_exceeds_returnable",
    )
    # Everything claimed: the order shows nothing left to return.
    facts = (await order.ready.client.get(f"{ORDERS}/{order.number}", headers=order.headers)).json()
    assert facts["can_return"] is False and facts["return_deadline"] is not None
    assert [line["returnable_quantity"] for line in facts["returnable_items"]] == [0]
    # A cancelled request gives its quantity back.
    cancel_url = f"{RETURNS}/{first.json()['id']}/cancel"
    await order.ready.client.post(cancel_url, headers=order.headers)
    assert (await order.create(order.body(2))).status_code == 201


async def test_delivery_and_window_rules(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    not_delivered = await _order(catalog, buyer, db_engine, deliver=False)
    _error(await not_delivered.create(), 422, "BUSINESS_RULE_VIOLATION", "order_not_delivered")
    no_row = await _order(catalog, buyer, db_engine, row=False)
    _error(await no_row.create(), 422, "BUSINESS_RULE_VIOLATION", "order_not_delivered")

    nearly = utc_now() - WINDOW + timedelta(minutes=5)
    almost = await _order(catalog, buyer, db_engine, delivered_at=nearly)
    assert (await almost.create()).status_code == 201
    past = utc_now() - WINDOW - timedelta(seconds=1)
    closed = await _order(catalog, buyer, db_engine, delivered_at=past)
    _error(await closed.create(), 422, "BUSINESS_RULE_VIOLATION", "return_window_closed")

    for order, deadline_set in ((not_delivered, False), (no_row, False), (closed, True)):
        url = f"{ORDERS}/{order.number}"
        facts = (await order.ready.client.get(url, headers=order.headers)).json()
        assert facts["can_return"] is False
        assert (facts["return_deadline"] is not None) is deadline_set
        assert all(line["returnable_quantity"] == 0 for line in facts["returnable_items"])


async def test_validation_errors(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order = await _order(catalog, buyer, db_engine)
    line = {"order_item_id": order.line(), "quantity": 1}
    bad_bodies: list[dict[str, Any]] = [
        {"items": [], "reason": "defective"},
        {"items": [line] * 51, "reason": "defective"},
        {"items": [line, line], "reason": "defective"},
        {"items": [line | {"quantity": 0}], "reason": "defective"},
        {"items": [line | {"quantity": -1}], "reason": "defective"},
        {"items": [line | {"quantity": True}], "reason": "defective"},
        {"items": [line | {"quantity": 1.0}], "reason": "defective"},
        {"items": [line | {"quantity": "1"}], "reason": "defective"},
        {"items": [line], "reason": "lost"},
        {"items": [line], "reason": ""},
        {"items": [line], "reason": "defective", "note": "x" * 1001},
        {"items": [line], "reason": "defective", "note": "   "},
        {"items": [line], "reason": "defective", "note": "bad\x07bell"},
        {"items": [line], "reason": "defective", "refund_amount": 1},
        {"items": [line], "reason": "defective", "status": "approved"},
        {"items": [line | {"refund_amount": 5}], "reason": "defective"},
    ]
    for body in bad_bodies:
        _error(await order.create(body), 400, "VALIDATION_ERROR")
    missing_key = await order.ready.client.post(
        f"{ORDERS}/{order.number}/returns", json=order.body(), headers=order.headers
    )
    _error(missing_key, 400, "VALIDATION_ERROR")
    malformed = await order.create(number="not-a-number")
    assert malformed.status_code in (400, 404)
    assert await _count(db_engine, ReturnRequest, ReturnRequest.order_id == order.order_id) == 0


async def test_auth_and_ownership(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order = await _order(catalog, buyer, db_engine)
    stranger = await _order(catalog, buyer, db_engine)
    created = (await order.create()).json()
    client = order.ready.client
    one = f"{RETURNS}/{created['id']}"

    # 401 before the missing Idempotency-Key 400.
    no_auth = await client.post(f"{ORDERS}/{order.number}/returns", json=order.body())
    _error(no_auth, 401, "UNAUTHORIZED")
    for response in (
        await client.get(RETURNS),
        await client.get(one),
        await client.post(f"{one}/cancel"),
    ):
        assert response.status_code == 401

    key = str(uuid4())
    foreign = await stranger.create(order.body(), key, number=order.number)
    _error(foreign, 404, "NOT_FOUND")
    assert await _count(db_engine, IdempotencyKey, IdempotencyKey.key == key) == 0
    for response in (
        await client.get(one, headers=stranger.headers),
        await client.post(f"{one}/cancel", headers=stranger.headers),
        await client.get(f"{RETURNS}/{uuid4()}", headers=order.headers),
    ):
        _error(response, 404, "NOT_FOUND")
    listed = await client.get(RETURNS, headers=stranger.headers)
    assert listed.json()["items"] == []


# --- list, detail, cancel ----------------------------------------------------------------


async def test_list_and_detail(catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine) -> None:
    order = await _order(catalog, buyer, db_engine, quantities=(3,))
    first = (await order.create(order.body(1))).json()
    second = (await order.create(order.body(2))).json()
    client, headers = order.ready.client, order.headers

    listed = await client.get(RETURNS, headers=headers)
    assert listed.status_code == 200 and listed.headers["cache-control"] == "no-store"
    page = listed.json()
    assert page["total"] == 2
    assert [item["id"] for item in page["items"]] == [second["id"], first["id"]]
    assert page["items"][0]["item_count"] == 2
    oldest = (await client.get(RETURNS, params={"sort": "oldest"}, headers=headers)).json()
    assert [item["id"] for item in oldest["items"]] == [first["id"], second["id"]]
    await client.post(f"{RETURNS}/{first['id']}/cancel", headers=headers)
    only = (await client.get(RETURNS, params={"status": "cancelled"}, headers=headers)).json()
    assert [item["id"] for item in only["items"]] == [first["id"]]
    bad_queries: list[dict[str, Any]] = [
        {"sort": "price"},
        {"status": "lost"},
        {"limit": 1000},
        {"foo": "1"},
    ]
    for params in bad_queries:
        _error(await client.get(RETURNS, params=params, headers=headers), 400, "VALIDATION_ERROR")

    detail = await client.get(f"{RETURNS}/{second['id']}", headers=headers)
    assert detail.status_code == 200 and detail.headers["cache-control"] == "no-store"
    assert detail.json() == second
    _error(
        await client.get(f"{RETURNS}/{second['id']}", params={"x": "1"}, headers=headers),
        400,
        "VALIDATION_ERROR",
    )


async def test_cancel_rules(catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine) -> None:
    order = await _order(catalog, buyer, db_engine, quantities=(3,))
    created = (await order.create()).json()
    url = f"{RETURNS}/{created['id']}/cancel"
    client, headers = order.ready.client, order.headers
    return_id = UUID(created["id"])

    first = await client.post(url, headers=headers)
    again = await client.post(url, headers=headers)

    assert (first.status_code, again.status_code) == (200, 200)
    assert first.json()["status"] == again.json()["status"] == "cancelled"
    assert [row["status"] for row in again.json()["history"]] == ["requested", "cancelled"]
    audits = await _count(
        db_engine, AuditLog, AuditLog.entity_id == return_id, AuditLog.action == "return.cancelled"
    )
    assert audits == 1

    approved = (await order.create()).json()
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(ReturnRequest)
            .where(ReturnRequest.id == UUID(approved["id"]))
            .values(status="approved", decided_at=utc_now())
        )
    _error(
        await client.post(f"{RETURNS}/{approved['id']}/cancel", headers=headers),
        422,
        "INVALID_STATE_TRANSITION",
    )


async def test_concurrent_cancels_change_once(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order = await _order(catalog, buyer, db_engine)
    created = (await order.create()).json()
    url = f"{RETURNS}/{created['id']}/cancel"
    return_id = UUID(created["id"])

    responses = await asyncio.gather(
        *(order.ready.client.post(url, headers=order.headers) for _ in range(3))
    )

    assert [response.status_code for response in responses] == [200, 200, 200]
    history = await _count(
        db_engine, ReturnStatusHistory, ReturnStatusHistory.return_request_id == return_id
    )
    audits = await _count(
        db_engine, AuditLog, AuditLog.entity_id == return_id, AuditLog.action == "return.cancelled"
    )
    assert (history, audits) == (2, 1)


async def test_create_while_an_earlier_request_is_cancelled(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    order = await _order(catalog, buyer, db_engine, quantities=(2,))
    earlier = (await order.create(order.body(2))).json()
    cancel_url = f"{RETURNS}/{earlier['id']}/cancel"

    created, cancelled = await asyncio.gather(
        order.create(order.body(1)), order.ready.client.post(cancel_url, headers=order.headers)
    )

    assert cancelled.status_code == 200
    # Either the create saw the cancel (201) or ran first while the line was full (422).
    assert created.status_code in (201, 422)
    after = await order.create(order.body(1))
    assert after.status_code == 201 or created.status_code == 201


# --- database backstops -----------------------------------------------------------------


async def test_database_checks(catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine) -> None:
    order = await _order(catalog, buyer, db_engine)
    created = (await order.create()).json()
    return_id = UUID(created["id"])
    inspected_without_refund = {
        "condition": "sellable",
        "accepted_quantity": 1,
        "refundable": False,
        "refund_amount": 10,
    }
    bad_updates: list[tuple[Any, dict[str, Any]]] = [
        (ReturnRequest, {"status": "rejected", "decided_at": utc_now()}),  # no reject_reason
        (ReturnRequest, {"status": "approved"}),  # no decided_at
        (ReturnRequest, {"status": "refunded", "decided_at": utc_now()}),  # no refund record
        (ReturnRequest, {"note": " padded "}),
        (ReturnRequest, {"reason": "lost"}),
        (ReturnItem, {"accepted_quantity": 5}),  # over quantity, and no condition
        (ReturnItem, inspected_without_refund),
        (ReturnItem, {"quantity": 0}),
    ]
    for model, values in bad_updates:
        where = (
            model.id == return_id
            if model is ReturnRequest
            else model.return_request_id == return_id
        )
        with pytest.raises(IntegrityError):
            async with AsyncSession(db_engine) as session, session.begin():
                await session.execute(update(model).where(where).values(**values))


async def test_the_schema_accepts_the_review_and_refund_path(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    """The CHECKs let through every step ORD-09 and ORD-10 will take."""
    order = await _order(catalog, buyer, db_engine, quantities=(3,))
    created = (await order.create(order.body(2))).json()
    rejected = (await order.create(order.body(1))).json()
    return_id, staff = UUID(created["id"]), order.ready.account.id
    now = utc_now()
    steps: list[tuple[Any, dict[str, Any]]] = [
        (ReturnRequest, {"status": "approved", "decided_at": now, "decided_by": staff}),
        (ReturnRequest, {"status": "received", "received_at": now, "admin_note": "Box opened"}),
        (
            ReturnItem,
            {
                "condition": "sellable",
                "accepted_quantity": 2,
                "refundable": True,
                "refund_amount": 120_000,
                "inspection_note": "Like new",
            },
        ),
        (ReturnRequest, {"status": "inspected", "inspected_at": now}),
        (ReturnRequest, {"status": "refund_required", "refund_amount": 120_000}),
        (
            ReturnRequest,
            {
                "status": "refunded",
                "refund_reference": f"RF-{uuid4().hex[:8]}",
                "refunded_at": now,
                "refunded_by": staff,
            },
        ),
    ]
    for model, values in steps:
        where = (
            model.id == return_id
            if model is ReturnRequest
            else model.return_request_id == return_id
        )
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(update(model).where(where).values(**values))
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(ReturnRequest)
            .where(ReturnRequest.id == UUID(rejected["id"]))
            .values(status="rejected", decided_at=now, reject_reason="Worn item")
        )
    # A zero-accepted damaged line without refund also fits (ORD-09 sets a condition).
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(ReturnItem)
            .where(ReturnItem.return_request_id == UUID(rejected["id"]))
            .values(condition="damaged", accepted_quantity=0, refundable=False)
        )

    shown = await order.ready.client.get(f"{RETURNS}/{rejected['id']}", headers=order.headers)
    assert shown.json()["reject_reason"] == "Worn item"
    refunded = await order.ready.client.get(f"{RETURNS}/{return_id}", headers=order.headers)
    assert refunded.json()["status"] == "refunded" and refunded.json()["refund_amount"] == 120_000
    assert not _keys(refunded.json()) & HIDDEN
