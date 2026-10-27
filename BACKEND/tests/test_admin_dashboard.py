"""GET /admin/dashboard (ADM-04, PRD «داشبورد» ✓, D39, ADR-055).

The figures cover the whole database, so each test compares a reading before and after
adding its own rows. A run that crosses Tehran midnight (20:30 UTC) between the readings
can fail the "today" checks; the window is a few seconds a day.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog, MakeAccount, MakeOrder, count_queries
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import InventoryReservation, Payment
from app.modules.reports.service import average_amount

API = "/api/v1/admin/dashboard"
PERIODS = ("today", "last_7_days", "last_30_days")


@pytest.mark.parametrize(
    ("amount", "count", "expected"), [(0, 0, 0), (3_001, 2, 1_500), (999, 1, 999), (10, 3, 3)]
)
def test_average_order_amount_is_floored(amount: int, count: int, expected: int) -> None:
    assert average_amount(amount, count) == expected


async def _dashboard(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.get(API, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body: dict[str, Any] = response.json()
    return body


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def _sale(
    make_order: MakeOrder,
    engine: AsyncEngine,
    total: int,
    paid_at: datetime,
    *,
    payment: str = "paid",
    **order: Any,
) -> UUID:
    """An order of ``total`` toman with one payment that took the money at ``paid_at``."""
    values: dict[str, Any] = {"status": "confirmed", "payment_status": payment}
    if payment == "refund_required":
        values |= {"status": "cancelled", "cancel_reason": "expired"}
    order_id = await make_order(subtotal=total, grand_total=total, **(values | order))
    async with AsyncSession(engine) as session, session.begin():
        session.add(
            Payment(
                order_id=order_id,
                gateway="fake",
                idempotency_key=f"key-{uuid4()}",
                amount=total,
                status=payment,
                paid_at=paid_at,
                failure_reason="late_payment" if payment == "refund_required" else None,
            )
        )
    return order_id


def _delta(before: dict[str, Any], after: dict[str, Any], period: str, key: str) -> int:
    change: int = after["periods"][period][key] - before["periods"][period][key]
    return change


@pytest.mark.integration
async def test_dashboard_needs_reports_read(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    assert (await auth_client.get(API)).status_code == 401
    for role in ("customer", "support", "content_manager"):
        staff = await make_account(role)
        response = await auth_client.get(API, headers=staff.headers)
        assert response.status_code == 403, role
        assert response.json()["error"]["code"] == "FORBIDDEN"
    for role in ("admin", "super_admin"):
        staff = await make_account(role)
        await _dashboard(auth_client, staff.headers)
    admin = await make_account("admin")
    unknown = await auth_client.get(API, params={"period": "today"}, headers=admin.headers)
    assert unknown.status_code == 400


@pytest.mark.integration
async def test_only_paid_orders_count_as_sales(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_order: MakeOrder,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    before = await _dashboard(auth_client, admin.headers)
    now = utc_now()
    await _sale(make_order, db_engine, 1_000, now - timedelta(seconds=5))
    await _sale(make_order, db_engine, 2_001, now - timedelta(seconds=4))
    await _sale(
        make_order, db_engine, 50_000, now - timedelta(seconds=3), payment="refund_required"
    )
    await make_order(subtotal=7_000, grand_total=7_000)  # never paid
    await make_order(
        subtotal=9_000, grand_total=9_000, status="cancelled", cancel_reason="customer"
    )

    after = await _dashboard(auth_client, admin.headers)

    for period in PERIODS:
        assert _delta(before, after, period, "sales_count") == 2, period
        assert _delta(before, after, period, "sales_amount") == 3_001, period
        figures = after["periods"][period]
        assert figures["average_order_amount"] == average_amount(
            figures["sales_amount"], figures["sales_count"]
        )
        assert all(isinstance(value, int) for key, value in figures.items() if key != "starts_at")
    assert after["refund_required_payments"] - before["refund_required_payments"] == 1
    assert after["timezone"] == "Asia/Tehran"
    assert "phone" not in str(after) and "mobile" not in str(after)


@pytest.mark.integration
async def test_an_order_with_two_paid_payments_counts_once(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_order: MakeOrder,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    before = await _dashboard(auth_client, admin.headers)
    now = utc_now()
    order_id = await _sale(make_order, db_engine, 5_000, now - timedelta(seconds=9))
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(
            Payment(
                order_id=order_id,
                gateway="fake",
                idempotency_key=f"key-{uuid4()}",
                amount=5_000,
                status="paid",
                paid_at=now - timedelta(seconds=8),
            )
        )

    after = await _dashboard(auth_client, admin.headers)

    assert _delta(before, after, "today", "sales_count") == 1
    assert _delta(before, after, "today", "sales_amount") == 5_000


@pytest.mark.integration
async def test_periods_start_at_tehran_midnight(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_order: MakeOrder,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    before = await _dashboard(auth_client, admin.headers)
    starts = {period: _when(before["periods"][period]["starts_at"]) for period in PERIODS}
    generated = _when(before["generated_at"])
    today = starts["today"]
    # Tehran is UTC+03:30: its midnight is 20:30 UTC of the previous UTC day.
    assert (today.hour, today.minute, today.second) == (20, 30, 0)
    assert today <= generated < today + timedelta(days=1)
    assert starts["last_7_days"] == today - timedelta(days=6)
    assert starts["last_30_days"] == today - timedelta(days=29)

    second = timedelta(seconds=1)
    await _sale(make_order, db_engine, 100, today)  # the first instant of today
    await _sale(make_order, db_engine, 200, today - second)  # 23:59:59 yesterday, Tehran
    await _sale(make_order, db_engine, 400, starts["last_7_days"] - second)
    await _sale(make_order, db_engine, 800, starts["last_30_days"] - second)
    await _sale(make_order, db_engine, 1_600, generated + timedelta(days=1))  # not yet

    after = await _dashboard(auth_client, admin.headers)

    assert _when(after["periods"]["today"]["starts_at"]) == today
    assert _delta(before, after, "today", "sales_amount") == 100
    assert _delta(before, after, "last_7_days", "sales_amount") == 300
    assert _delta(before, after, "last_30_days", "sales_amount") == 700
    assert _delta(before, after, "last_30_days", "sales_count") == 3


@pytest.mark.integration
async def test_work_queues_and_stock_alerts(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    make_order: MakeOrder,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    before = await _dashboard(auth_client, admin.headers)
    now = utc_now()

    live = await make_order()
    stale = await make_order()
    async with AsyncSession(db_engine) as session, session.begin():
        session.add_all(
            [
                InventoryReservation(order_id=live, expires_at=now + timedelta(minutes=10)),
                InventoryReservation(order_id=stale, expires_at=now - timedelta(minutes=1)),
            ]
        )
    paid = now - timedelta(minutes=1)
    await _sale(make_order, db_engine, 1_000, paid)  # confirmed, not shipped
    await _sale(make_order, db_engine, 1_000, paid, shipment_status="preparing")
    await _sale(make_order, db_engine, 1_000, paid, shipment_status="shipped")
    await _sale(make_order, db_engine, 1_000, paid, status="completed", shipment_status="delivered")

    product = await catalog.product()
    await catalog.variant(product, stock=(10, 0, 3))  # in stock
    await catalog.variant(product, stock=(10, 7, 3))  # free 3 ≤ threshold 3: low
    await catalog.variant(product, stock=(4, 4, 0))  # free 0: out
    await catalog.variant(product)  # no inventory row: out
    await catalog.variant(product, stock=(0, 0, 0), is_active=False)  # inactive: ignored

    after = await _dashboard(auth_client, admin.headers)

    def change(key: str) -> int:
        difference: int = after[key] - before[key]
        return difference

    assert change("pending_payment_orders") == 1
    assert change("orders_to_ship") == 2
    assert change("refund_required_payments") == 0
    assert change("low_stock_variants") == 1
    assert change("out_of_stock_variants") == 2


@pytest.mark.integration
async def test_new_customers_are_customers_registered_in_the_period(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    before = await _dashboard(auth_client, admin.headers)
    await make_account("customer")
    await make_account("customer")
    await make_account("support")

    after = await _dashboard(auth_client, admin.headers)

    for period in PERIODS:
        assert _delta(before, after, period, "new_customers") == 2, period


@pytest.mark.integration
async def test_query_count_does_not_grow_with_orders(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_order: MakeOrder,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    await _dashboard(auth_client, admin.headers)  # warm-up
    with count_queries(auth_client) as few:
        await _dashboard(auth_client, admin.headers)
    now = utc_now()
    for index in range(5):
        await _sale(make_order, db_engine, 1_000 + index, now - timedelta(seconds=index + 1))
    with count_queries(auth_client) as many:
        await _dashboard(auth_client, admin.headers)
    assert len(many) == len(few)
