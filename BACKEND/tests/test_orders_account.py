"""The customer's own orders: GET /orders and GET /orders/{number} (ACC-01, ADR-053)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from conftest import Catalog, nested_keys
from httpx import Response
from sqlalchemy import update
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
from test_payments_init import _init

from app.core.time import utc_now
from app.db.models import InventoryReservation, Order, ProductVariant

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

SUMMARY_KEYS = {
    "id",
    "order_number",
    "status",
    "payment_status",
    "shipment_status",
    "grand_total",
    "currency",
    "item_count",
    "image_url",
    "created_at",
}
# Never shown to the customer: gateway data, actors, other people's data.
HIDDEN = {"gateway_reference", "raw_event", "actor_user_id", "redirect_url", "user_id"}


async def _ready(catalog: Catalog, buyer: MakeBuyer, quantity: int = 2) -> Buyer:
    product = await catalog.product()
    variant: ProductVariant = await catalog.variant(product, stock=(10, 0, 0))
    await catalog.image(product, is_main=True)
    return await buyer((variant, quantity))


async def _place(ready: Buyer) -> dict[str, Any]:
    response = await ready.order()
    assert response.status_code == 201, response.text
    placed: dict[str, Any] = response.json()
    return placed


async def _detail(ready: Buyer, number: str) -> Response:
    return await ready.client.get(f"{ORDERS}/{number}", headers=ready.account.headers)


async def _expire(engine: AsyncEngine, order_id: str) -> None:
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == UUID(order_id))
            .values(
                created_at=utc_now() - timedelta(minutes=40),
                expires_at=utc_now() - timedelta(minutes=1),
            )
        )


async def test_list_shows_only_own_orders_newest_first(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready = await _ready(catalog, buyer)
    first = await _place(ready)
    # One live unpaid order at a time (ADR-048): cancel the first, then order again.
    cancel = await ready.client.post(
        f"{ORDERS}/{first['id']}/cancel", headers=ready.account.headers
    )
    assert cancel.status_code == 200, cancel.text
    second = await _place(ready)
    other = await _ready(catalog, buyer)
    await _place(other)

    response = await ready.client.get(ORDERS, headers=ready.account.headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [second["id"], first["id"]]
    [latest, _older] = body["items"]
    assert set(latest) == SUMMARY_KEYS
    assert latest["item_count"] == 2
    assert latest["grand_total"] == second["grand_total"]
    assert latest["image_url"] is not None

    oldest = await ready.client.get(
        ORDERS, params={"sort": "oldest", "limit": 1}, headers=ready.account.headers
    )
    assert [item["id"] for item in oldest.json()["items"]] == [first["id"]]
    cancelled = await ready.client.get(
        ORDERS, params={"status": "cancelled"}, headers=ready.account.headers
    )
    assert [item["id"] for item in cancelled.json()["items"]] == [first["id"]]


async def test_list_errors(catalog: Catalog, buyer: MakeBuyer) -> None:
    ready = await _ready(catalog, buyer)
    client, headers = ready.client, ready.account.headers

    _error(await client.get(ORDERS), 401, "UNAUTHORIZED")
    _error(await client.get(f"{ORDERS}?x=1"), 401, "UNAUTHORIZED")
    for params in ({"x": "1"}, {"status": "lost"}, {"sort": "price"}, {"limit": "101"}):
        _error(await client.get(ORDERS, params=params, headers=headers), 400, "VALIDATION_ERROR")


async def test_detail_of_a_new_order(catalog: Catalog, buyer: MakeBuyer) -> None:
    ready = await _ready(catalog, buyer)
    placed = await _place(ready)

    response = await _detail(ready, placed["order_number"])

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    # Everything POST /orders returned, plus the account fields.
    assert {key: body[key] for key in placed} == placed
    assert body["payments"] == []
    # The three initial statuses share one moment, so their relative order is not fixed.
    assert {(row["field"], row["old_status"], row["new_status"]) for row in body["history"]} == {
        ("order", None, "pending_payment"),
        ("payment", None, "unpaid"),
        ("shipment", None, "not_shipped"),
    }
    assert body["shipment"] is None
    assert body["cancel_reason"] is None
    assert body["payment_deadline"] == placed["reservation_expires_at"]
    assert (body["can_pay"], body["can_cancel"]) == (True, True)
    assert not nested_keys(body) & HIDDEN


async def test_flags_follow_the_payment_and_the_deadline(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready = await _ready(catalog, buyer)
    placed = await _place(ready)
    number = placed["order_number"]

    # A payment under way: still payable (the same gateway session), not cancellable.
    assert (await _init(ready, UUID(placed["id"]))).status_code == 201
    paying = (await _detail(ready, number)).json()
    assert (paying["can_pay"], paying["can_cancel"]) == (True, False)
    [payment] = paying["payments"]
    assert set(payment) == {"id", "status", "amount", "created_at", "paid_at"}
    assert (payment["status"], payment["amount"]) == ("pending", placed["grand_total"])

    # Past the deadline: shown as stored, but nothing can be done (ADR-050).
    await _expire(db_engine, placed["id"])
    late = (await _detail(ready, number)).json()
    assert late["status"] == "pending_payment"
    assert (late["can_pay"], late["can_cancel"]) == (False, False)


async def test_a_cancelled_order(catalog: Catalog, buyer: MakeBuyer) -> None:
    ready = await _ready(catalog, buyer)
    placed = await _place(ready)
    await ready.client.post(f"{ORDERS}/{placed['id']}/cancel", headers=ready.account.headers)

    body = (await _detail(ready, placed["order_number"])).json()

    assert (body["status"], body["cancel_reason"]) == ("cancelled", "customer")
    assert body["payment_deadline"] is None
    assert (body["can_pay"], body["can_cancel"]) == (False, False)
    assert ("order", "pending_payment", "cancelled") in [
        (row["field"], row["old_status"], row["new_status"]) for row in body["history"]
    ]


async def test_someone_elses_or_unknown_order_is_404(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    ready = await _ready(catalog, buyer)
    other = await _ready(catalog, buyer)
    theirs = await _place(other)

    _error(await _detail(ready, theirs["order_number"]), 404, "NOT_FOUND")
    _error(await _detail(ready, "ORD-2026-999999999"), 404, "NOT_FOUND")
    _error(await _detail(ready, "not-a-number"), 400, "VALIDATION_ERROR")
    _error(await ready.client.get(f"{ORDERS}/{theirs['order_number']}"), 401, "UNAUTHORIZED")
    _error(
        await ready.client.get(
            f"{ORDERS}/{theirs['order_number']}?x=1", headers=ready.account.headers
        ),
        400,
        "VALIDATION_ERROR",
    )
    # Nothing was written by the reads.
    async with AsyncSession(db_engine) as session:
        order = await session.get(Order, UUID(theirs["id"]))
        assert order is not None and order.status == "pending_payment"
