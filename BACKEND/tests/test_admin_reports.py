"""Sales reports (ADM-05, PRD «گزارش‌ها» ✓, D39, ADR-055).

Integration tests date their sales in March-May 2024, around Nowruz 1403 (2024-03-20),
so no other test's rows fall in their ranges.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog, MakeAccount, MakeOrder
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.errors import BadRequestError
from app.db.models import OrderItem, Payment, Product, ProductVariant
from app.modules.reports.calendar import GroupBy, buckets, to_jalali
from app.modules.reports.service import check_range

API = "/api/v1/admin/reports"

# --- calendar (pure) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2024, 3, 19), (1402, 12, 29)),
        (date(2024, 3, 20), (1403, 1, 1)),
        (date(2025, 3, 20), (1403, 12, 30)),  # 1403 is a leap year
        (date(2025, 3, 21), (1404, 1, 1)),
        (date(2026, 3, 21), (1405, 1, 1)),
        (date(2026, 10, 27), (1405, 8, 5)),
        (date(2024, 2, 29), (1402, 12, 10)),
    ],
)
def test_to_jalali_known_dates(day: date, expected: tuple[int, int, int]) -> None:
    assert to_jalali(day) == expected


def test_to_jalali_advances_one_day_at_a_time() -> None:
    day = date(2019, 1, 1)
    previous = to_jalali(day)
    while day < date(2033, 1, 1):
        day += timedelta(days=1)
        current = to_jalali(day)
        if current[2] != 1:
            assert current == (previous[0], previous[1], previous[2] + 1), day
            previous = current
            continue
        month_length = 31 if previous[1] <= 6 else 30 if previous[1] <= 11 else previous[2]
        assert previous[2] == month_length, day
        if previous[1] == 12:
            assert previous[2] in (29, 30) and current == (previous[0] + 1, 1, 1), day
        else:
            assert current == (previous[0], previous[1] + 1, 1), day
        previous = current


def _spans(start: date, end: date, group_by: GroupBy) -> list[tuple[str, date, date]]:
    return [(b.label, b.starts_on, b.ends_before) for b in buckets(start, end, group_by)]


def test_weeks_start_on_saturday_and_are_clipped_to_the_range() -> None:
    # 2024-03-16 is a Saturday.
    assert _spans(date(2024, 3, 14), date(2024, 3, 25), GroupBy.WEEK) == [
        ("1402-12-24", date(2024, 3, 14), date(2024, 3, 16)),
        ("1402-12-26", date(2024, 3, 16), date(2024, 3, 23)),
        ("1403-01-04", date(2024, 3, 23), date(2024, 3, 25)),
    ]


def test_months_are_jalali() -> None:
    assert _spans(date(2024, 3, 1), date(2024, 5, 1), GroupBy.MONTH) == [
        ("1402-12", date(2024, 3, 1), date(2024, 3, 20)),
        ("1403-01", date(2024, 3, 20), date(2024, 4, 20)),
        ("1403-02", date(2024, 4, 20), date(2024, 5, 1)),
    ]


def test_days_cover_the_range_without_gaps() -> None:
    days = buckets(date(2024, 1, 1), date(2025, 1, 1), GroupBy.DAY)
    assert len(days) == 366
    assert all(a.ends_before == b.starts_on for a, b in zip(days, days[1:], strict=False))
    with pytest.raises(ValueError):
        buckets(date(2024, 1, 2), date(2024, 1, 2), GroupBy.DAY)
    assert len(buckets(date.max - timedelta(days=1), date.max, GroupBy.WEEK)) == 1


@pytest.mark.parametrize(
    ("start", "end", "valid"),
    [
        (date(2024, 1, 1), date(2025, 1, 1), True),  # 366 days
        (date(2023, 1, 1), date(2024, 1, 3), False),  # 367 days
        (date(2024, 1, 2), date(2024, 1, 2), False),
        (date(2024, 1, 3), date(2024, 1, 2), False),
    ],
)
def test_check_range(start: date, end: date, valid: bool) -> None:
    if valid:
        check_range(start, end)
    else:
        with pytest.raises(BadRequestError):
            check_range(start, end)


# --- API (integration) -----------------------------------------------------------


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


Line = tuple[ProductVariant, int, int, str]  # variant, quantity, final_line_total, title


async def _sale(
    make_order: MakeOrder,
    engine: AsyncEngine,
    paid_at: datetime,
    lines: Sequence[Line] = (),
    *,
    payment: str = "paid",
    subtotal: int = 10_000,
    product_discount_total: int = 1_000,
    tax_amount: int = 900,
    shipping_amount: int = 500,
) -> UUID:
    grand_total = subtotal - product_discount_total + tax_amount + shipping_amount
    values: dict[str, Any] = {"status": "confirmed", "payment_status": payment}
    if payment == "refund_required":
        values |= {"status": "cancelled", "cancel_reason": "expired"}
    order_id = await make_order(
        subtotal=subtotal,
        product_discount_total=product_discount_total,
        tax_amount=tax_amount,
        shipping_amount=shipping_amount,
        grand_total=grand_total,
        **values,
    )
    async with AsyncSession(engine) as session, session.begin():
        session.add(
            Payment(
                order_id=order_id,
                gateway="fake",
                idempotency_key=f"key-{uuid4()}",
                amount=grand_total,
                status=payment,
                paid_at=paid_at,
                failure_reason="late_payment" if payment == "refund_required" else None,
            )
        )
        for position, (variant, quantity, total, title) in enumerate(lines):
            session.add(
                OrderItem(
                    order_id=order_id,
                    position=position,
                    product_id=variant.product_id,
                    variant_id=variant.id,
                    product_title=title,
                    sku=variant.sku,
                    quantity=quantity,
                    unit_price=total // quantity,
                    unit_final_price=total // quantity,
                    subtotal=total,
                    product_discount=0,
                    code_discount=0,
                    discount_amount=0,
                    tax_amount=0,
                    final_line_total=total,
                )
            )
    return order_id


async def _get(
    client: AsyncClient, path: str, headers: dict[str, str], **params: Any
) -> dict[str, Any]:
    response = await client.get(f"{API}/{path}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body: dict[str, Any] = response.json()
    return body


FIGURES = (
    "order_count",
    "subtotal",
    "product_discount_total",
    "discount_code_amount",
    "tax_amount",
    "shipping_amount",
    "grand_total",
)


@pytest.mark.integration
async def test_reports_need_reports_read_and_a_valid_range(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    good = {"from": "2024-01-01", "to": "2024-02-01"}
    for path in ("sales", "products", "categories"):
        assert (await auth_client.get(f"{API}/{path}", params=good)).status_code == 401
    support = await make_account("support")
    for path in ("sales", "products", "categories"):
        response = await auth_client.get(f"{API}/{path}", params=good, headers=support.headers)
        assert response.status_code == 403, path

    admin = await make_account("admin")
    bad: list[tuple[str, dict[str, str]]] = [
        ("sales", {"from": "2023-01-01", "to": "2024-01-03"}),  # 367 days
        ("sales", {"from": "2024-01-02", "to": "2024-01-02"}),
        ("sales", {"from": "2024-01-02"}),
        ("sales", {"from": "2024-01-01", "to": "2024-01-02", "group_by": "year"}),
        ("sales", {"from": "2024-01-01", "to": "2024-01-02", "page": "1"}),
        ("sales", {"from": "yesterday", "to": "2024-01-02"}),
        ("products", {"from": "2024-01-01", "to": "2024-01-02", "limit": "0"}),
        ("products", {"from": "2024-01-01", "to": "2024-01-02", "limit": "101"}),
        ("categories", {"from": "2024-01-01", "to": "2024-01-02", "limit": "5"}),
        ("categories", {"from": "2024-03-01", "to": "2024-01-02"}),
    ]
    for path, params in bad:
        response = await auth_client.get(f"{API}/{path}", params=params, headers=admin.headers)
        assert response.status_code == 400, (path, params, response.text)
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    super_admin = await make_account("super_admin")
    year = await _get(
        auth_client, "sales", super_admin.headers, **{"from": "2024-01-01", "to": "2025-01-01"}
    )
    assert len(year["buckets"]) == 366


@pytest.mark.integration
async def test_sales_per_tehran_day_from_order_snapshots(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_order: MakeOrder,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    # Tehran midnight starting 2024-03-20 (Nowruz) is 2024-03-19 20:30 UTC.
    await _sale(make_order, db_engine, _utc(2024, 3, 19, 20, 29, 59))  # 1402-12-29
    await _sale(make_order, db_engine, _utc(2024, 3, 19, 20, 30))  # 1403-01-01
    await _sale(make_order, db_engine, _utc(2024, 3, 20, 20, 29), subtotal=20_000)
    await _sale(make_order, db_engine, _utc(2024, 3, 20, 10), payment="refund_required")
    await make_order(subtotal=5_000, grand_total=5_000)  # never paid

    body = await _get(
        auth_client, "sales", admin.headers, **{"from": "2024-03-18", "to": "2024-03-22"}
    )

    assert (body["from"], body["to"], body["group_by"]) == ("2024-03-18", "2024-03-22", "day")
    assert (body["timezone"], body["calendar"]) == ("Asia/Tehran", "jalali")
    labels = [bucket["label"] for bucket in body["buckets"]]
    assert labels == ["1402-12-28", "1402-12-29", "1403-01-01", "1403-01-02"]
    counts = [bucket["order_count"] for bucket in body["buckets"]]
    assert counts == [0, 1, 2, 0]
    nowruz = body["buckets"][2]
    assert (nowruz["starts_on"], nowruz["ends_before"]) == ("2024-03-20", "2024-03-21")
    assert nowruz["subtotal"] == 30_000
    assert nowruz["product_discount_total"] == 2_000
    assert nowruz["tax_amount"] == 1_800
    assert nowruz["shipping_amount"] == 1_000
    assert nowruz["grand_total"] == 30_000 - 2_000 + 1_800 + 1_000
    for name in FIGURES:
        assert body["totals"][name] == sum(b[name] for b in body["buckets"]), name
        assert all(isinstance(b[name], int) for b in body["buckets"])
    assert body["totals"]["order_count"] == 3


@pytest.mark.integration
async def test_sales_per_saturday_week_and_jalali_month(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_order: MakeOrder,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    # Friday 2024-03-15 23:30 Tehran, then Saturday 2024-03-16 00:30 Tehran.
    await _sale(make_order, db_engine, _utc(2024, 3, 15, 20))
    await _sale(make_order, db_engine, _utc(2024, 3, 15, 21))
    await _sale(make_order, db_engine, _utc(2024, 4, 19, 12))  # 1403-01-31
    await _sale(make_order, db_engine, _utc(2024, 4, 19, 21))  # 1403-02-01 in Tehran

    weeks = await _get(
        auth_client,
        "sales",
        admin.headers,
        **{"from": "2024-03-14", "to": "2024-03-25", "group_by": "week"},
    )
    assert [(b["starts_on"], b["order_count"]) for b in weeks["buckets"]] == [
        ("2024-03-14", 1),
        ("2024-03-16", 1),
        ("2024-03-23", 0),
    ]

    months = await _get(
        auth_client,
        "sales",
        admin.headers,
        **{"from": "2024-03-01", "to": "2024-05-01", "group_by": "month"},
    )
    assert [(b["label"], b["order_count"]) for b in months["buckets"]] == [
        ("1402-12", 2),
        ("1403-01", 1),
        ("1403-02", 1),
    ]
    assert months["totals"]["order_count"] == 4
    assert months["totals"]["grand_total"] == sum(b["grand_total"] for b in months["buckets"])


@pytest.mark.integration
async def test_sales_per_product_and_category(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    make_order: MakeOrder,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    rings, chains = await catalog.category(), await catalog.category()
    ring = await catalog.product(category=rings.id, title="Ring")
    band = await catalog.product(category=rings.id, title="Band")
    chain = await catalog.product(category=chains.id, title="Chain")
    ring_v, band_v, chain_v = (
        await catalog.variant(ring),
        await catalog.variant(band),
        await catalog.variant(chain),
    )
    when = _utc(2024, 5, 10, 8)
    await _sale(
        make_order,
        db_engine,
        when,
        [(ring_v, 2, 4_000, "Old ring"), (chain_v, 1, 9_000, "Chain")],
    )
    await _sale(make_order, db_engine, when + timedelta(hours=1), [(ring_v, 1, 2_500, "Ring")])
    await _sale(make_order, db_engine, when, [(band_v, 3, 3_000, "Band")])
    await _sale(
        make_order, db_engine, when, [(chain_v, 5, 50_000, "Chain")], payment="refund_required"
    )
    await catalog.set(Product, band.id, deleted_at=when)  # still in the report
    span = {"from": "2024-05-01", "to": "2024-06-01"}

    products = await _get(auth_client, "products", admin.headers, **span)
    rows = [(i["id"], i["title"], i["units_sold"], i["amount"]) for i in products["items"]]
    assert rows == [
        (str(chain.id), "Chain", 1, 9_000),
        (str(ring.id), "Ring", 3, 6_500),  # the most recent title snapshot
        (str(band.id), "Band", 3, 3_000),
    ]
    assert products["totals"] == {"units_sold": 7, "amount": 18_500}

    top = await _get(auth_client, "products", admin.headers, limit=1, **span)
    assert [item["id"] for item in top["items"]] == [str(chain.id)]
    assert top["totals"] == products["totals"]

    categories = await _get(auth_client, "categories", admin.headers, **span)
    assert [(i["id"], i["units_sold"], i["amount"]) for i in categories["items"]] == [
        (str(rings.id), 6, 9_500),
        (str(chains.id), 1, 9_000),
    ]
    assert categories["totals"] == products["totals"]
    assert "phone" not in str(products) and "phone" not in str(categories)
