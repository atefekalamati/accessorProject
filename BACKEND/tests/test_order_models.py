"""Order schema: snapshots, CHECKs, order numbers and RESTRICT references (ORD-01)."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Catalog, MakeOrder
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.phone import MOBILE_E164_PATTERN
from app.core.time import utc_now
from app.db.models import (
    DiscountCode,
    DiscountRedemption,
    InventoryReservation,
    Order,
    OrderAddress,
    OrderItem,
    OrderPriceSnapshot,
    OrderStatusHistory,
    ProductVariant,
    ShippingMethod,
)
from app.db.models.orders import ORDER_NUMBER_PATTERN, format_order_number

# --- order numbers (no database) -----------------------------------------------------


@pytest.mark.parametrize(
    ("year", "number", "expected"),
    [
        (2026, 1, "ORD-2026-000001"),
        (2026, 123_456, "ORD-2026-123456"),
        (2027, 1_234_567, "ORD-2027-1234567"),  # the global sequence may pass 6 digits
    ],
)
def test_format_order_number(year: int, number: int, expected: str) -> None:
    formatted = format_order_number(year, number)
    assert formatted == expected
    assert re.fullmatch(ORDER_NUMBER_PATTERN.strip("^$"), formatted)
    # Never shaped like a mobile number, so log masking never confuses the two.
    assert not re.search(MOBILE_E164_PATTERN.strip("^$"), formatted)
    assert not re.search(r"09[0-9]{9}", formatted.replace("-", ""))


@pytest.mark.parametrize(
    ("year", "number"),
    [(999, 1), (10_000, 1), (2026, 0), (2026, -1), (True, 1), (2026, 1.0), ("2026", 1)],
)
def test_format_order_number_rejects_bad_input(year: Any, number: Any) -> None:
    with pytest.raises(ValueError):
        format_order_number(year, number)


# --- schema (integration) ------------------------------------------------------------


async def _order(engine: AsyncEngine, order_id: UUID) -> Order:
    async with AsyncSession(engine) as session:
        order = await session.get(Order, order_id)
        assert order is not None
        return order


async def _update(engine: AsyncEngine, model: Any, where: Any, **values: Any) -> None:
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(update(model).where(where).values(**values))


def _line(order_id: UUID, variant: ProductVariant, **values: Any) -> OrderItem:
    # 2 × 100 000, sale 90 000, a 10 000 code share and 9 900 tax.
    base: dict[str, Any] = {
        "order_id": order_id,
        "position": 0,
        "product_id": variant.product_id,
        "variant_id": variant.id,
        "product_title": "Silver ring",
        "sku": variant.sku,
        "variant_label": "color: Red / size: M",
        "quantity": 2,
        "unit_price": 100_000,
        "unit_final_price": 90_000,
        "subtotal": 200_000,
        "product_discount": 20_000,
        "code_discount": 10_000,
        "discount_amount": 30_000,
        "tax_amount": 9_900,
        "final_line_total": 179_900,
    }
    return OrderItem(**(base | values))


async def _insert(engine: AsyncEngine, *rows: Any) -> None:
    async with AsyncSession(engine) as session, session.begin():
        session.add_all(rows)


@pytest.mark.integration
async def test_a_full_order_survives_later_catalog_changes(
    catalog: Catalog, make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    product = await catalog.product(title="Silver ring")
    variant = await catalog.variant(product)
    order_id = await make_order(
        subtotal=200_000,
        product_discount_total=20_000,
        tax_amount=9_900,
        shipping_amount=30_000,
        grand_total=219_900,
    )
    now = utc_now()
    await _insert(
        db_engine,
        _line(order_id, variant, code_discount=0, discount_amount=20_000, final_line_total=189_900),
        OrderPriceSnapshot(
            order_id=order_id,
            pricing_version=3,
            tax_enabled=True,
            tax_rate_bps=550,
            rounding_mode="nearest",
            rounding_step=100,
            fingerprint="a" * 64,
            calculated_at=now,
            shipping_method_cost=30_000,
            shipping_free_threshold=500_000,
        ),
        OrderAddress(
            order_id=order_id,
            source_address_id=uuid4(),
            recipient_name="Sara Ahmadi",
            phone="+989121234567",
            province="Tehran",
            city="Tehran",
            postal_code="1234567890",
            address_line="Valiasr St, No. 10",
        ),
        OrderStatusHistory(order_id=order_id, field="order", new_status="pending_payment"),
    )

    # The catalog moves on: new title, new price, soft deleted variant.
    await catalog.set(type(product), product.id, title="Gold ring")
    await catalog.set(ProductVariant, variant.id, base_price=500_000, deleted_at=utc_now())

    async with AsyncSession(db_engine) as session:
        [item] = await session.scalars(select(OrderItem).where(OrderItem.order_id == order_id))
        snapshot = await session.get(OrderPriceSnapshot, order_id)
        address = await session.get(OrderAddress, order_id)
    assert (item.product_title, item.unit_price, item.final_line_total) == (
        "Silver ring",
        100_000,
        189_900,
    )
    assert item.variant_label == "color: Red / size: M"
    assert snapshot is not None and snapshot.shipping_method_cost == 30_000
    assert address is not None and address.city == "Tehran"
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status, order.shipment_status, order.grand_total) == (
        "pending_payment",
        "unpaid",
        "not_shipped",
        219_900,
    )
    # A referenced variant cannot be hard deleted.
    with pytest.raises(IntegrityError, match="fk_order_items_variant_id_product_variants"):
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(ProductVariant).where(ProductVariant.id == variant.id))


@pytest.mark.integration
@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"status": "shipped"}, "valid_status"),
        ({"payment_status": "chargeback"}, "valid_payment_status"),
        ({"shipment_status": "lost"}, "valid_shipment_status"),
        ({"status": "cancelled"}, "cancelled_has_reason"),
        ({"cancel_reason": "customer"}, "cancelled_has_reason"),
        ({"status": "cancelled", "cancel_reason": "bored"}, "valid_cancel_reason"),
        ({"grand_total": 1}, "grand_total_sum"),
        (
            {"subtotal": 10, "product_discount_total": 20, "tax_amount": 15, "grand_total": 5},
            "discounts_within_subtotal",
        ),
        ({"subtotal": 10, "grand_total": 9, "tax_amount": -1}, "amounts_non_negative"),
        ({"discount_code_amount": 5, "subtotal": 5}, "code_amount_needs_code"),
        ({"discount_code": "SUMMER"}, "code_snapshot_pair"),
        ({"currency": "IRR"}, "currency_toman"),
        ({"phone": "09121234567"}, "phone_format"),
        ({"order_number": "ORD-2026-12345"}, "order_number_format"),
        ({"order_number": "09121234567"}, "order_number_(format|year)"),
        ({"order_number": "ORD-1999-000001"}, "order_number_year"),
        ({"shipping_method_title": " Post "}, "shipping_method_title_format"),
    ],
)
async def test_order_checks(
    make_order: MakeOrder, db_engine: AsyncEngine, values: dict[str, Any], constraint: str
) -> None:
    order_id = await make_order()
    with pytest.raises(IntegrityError, match=f"ck_orders_{constraint}"):
        await _update(db_engine, Order, Order.id == order_id, **values)


@pytest.mark.integration
async def test_cancelled_with_reason_and_a_valid_total_are_accepted(
    make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    order_id = await make_order(
        subtotal=100,
        product_discount_total=10,
        tax_amount=5,
        shipping_amount=7,
        grand_total=102,
        status="cancelled",
        cancel_reason="expired",
    )
    order = await _order(db_engine, order_id)
    assert (order.status, order.cancel_reason, order.grand_total) == ("cancelled", "expired", 102)


@pytest.mark.integration
async def test_order_numbers_are_unique(make_order: MakeOrder, db_engine: AsyncEngine) -> None:
    first = await _order(db_engine, await make_order())
    second = await make_order()
    assert re.fullmatch(ORDER_NUMBER_PATTERN.strip("^$"), first.order_number)
    with pytest.raises(IntegrityError, match="uq_orders_order_number"):
        await _update(db_engine, Order, Order.id == second, order_number=first.order_number)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        (
            {
                "quantity": 0,
                "subtotal": 0,
                "product_discount": 0,
                "code_discount": 0,
                "discount_amount": 0,
                "tax_amount": 0,
                "final_line_total": 0,
            },
            "quantity_range",
        ),
        ({"subtotal": 199_999, "final_line_total": 179_899}, "subtotal_product"),
        (
            {
                "unit_final_price": 100_001,
                "product_discount": -2,
                "discount_amount": 9_998,
                "final_line_total": 199_902,
            },
            "(unit_prices_range|amounts_non_negative)",
        ),
        (
            {"product_discount": 19_000, "discount_amount": 29_000, "final_line_total": 180_900},
            "product_discount_product",
        ),
        ({"discount_amount": 30_001, "final_line_total": 179_899}, "discount_amount_sum"),
        ({"final_line_total": 1}, "final_line_total_sum"),
        (
            {
                "code_discount": 190_000,
                "discount_amount": 210_000,
                "tax_amount": 20_000,
                "final_line_total": 10_000,
            },
            "discount_within_subtotal",
        ),
        ({"tax_amount": -1, "final_line_total": 169_999}, "amounts_non_negative"),
        ({"product_title": " Ring"}, "product_title_format"),
        ({"position": -1}, "position_non_negative"),
    ],
)
async def test_order_item_checks(
    catalog: Catalog,
    make_order: MakeOrder,
    db_engine: AsyncEngine,
    values: dict[str, Any],
    constraint: str,
) -> None:
    variant = await catalog.variant(await catalog.product())
    order_id = await make_order()
    with pytest.raises(IntegrityError, match=f"ck_order_items_{constraint}"):
        await _insert(db_engine, _line(order_id, variant, **values))


@pytest.mark.integration
async def test_order_item_huge_amounts_do_not_overflow_the_checks(
    catalog: Catalog, make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product())
    order_id = await make_order()
    # 1e12 × 1e6 = 1e18 fits BIGINT; the CHECK arithmetic runs in numeric.
    big = 10**12 * 10**6
    await _insert(
        db_engine,
        _line(
            order_id,
            variant,
            quantity=10**6,
            unit_price=10**12,
            unit_final_price=10**12,
            subtotal=big,
            product_discount=0,
            code_discount=0,
            discount_amount=0,
            tax_amount=10**18,
            final_line_total=big + 10**18,
        ),
    )


@pytest.mark.integration
async def test_line_positions_and_the_variant_product_pair_are_enforced(
    catalog: Catalog, make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product())
    other = await catalog.product()
    order_id = await make_order()
    await _insert(db_engine, _line(order_id, variant))
    with pytest.raises(IntegrityError, match="uq_order_items_order_id"):
        await _insert(db_engine, _line(order_id, variant))
    with pytest.raises(IntegrityError, match="fk_order_items_variant_id_product_variants"):
        await _insert(db_engine, _line(order_id, variant, position=1, product_id=other.id))


@pytest.mark.integration
@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"fingerprint": "XYZ"}, "fingerprint_format"),
        ({"rounding_mode": "bankers"}, "valid_rounding_mode"),
        ({"rounding_step": 0}, "rounding_step_range"),
        ({"tax_rate_bps": 10_001}, "tax_rate_range"),
        ({"pricing_version": 0}, "pricing_version_positive"),
        ({"shipping_method_cost": -1}, "shipping_method_cost_range"),
        ({"shipping_free_threshold": 0}, "shipping_free_threshold_range"),
    ],
)
async def test_price_snapshot_checks(
    make_order: MakeOrder, db_engine: AsyncEngine, values: dict[str, Any], constraint: str
) -> None:
    base: dict[str, Any] = {
        "pricing_version": 1,
        "tax_enabled": False,
        "tax_rate_bps": 0,
        "rounding_mode": "nearest",
        "rounding_step": 1,
        "fingerprint": "0" * 64,
        "calculated_at": utc_now(),
        "shipping_method_cost": 0,
    }
    order_id = await make_order()
    with pytest.raises(IntegrityError, match=f"ck_order_price_snapshots_{constraint}"):
        await _insert(db_engine, OrderPriceSnapshot(order_id=order_id, **(base | values)))


@pytest.mark.integration
async def test_history_rejects_unknown_fields_and_no_op_changes(
    make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    order_id = await make_order()
    with pytest.raises(IntegrityError, match="ck_order_status_history_valid_field"):
        await _insert(db_engine, OrderStatusHistory(order_id=order_id, field="x", new_status="a"))
    with pytest.raises(IntegrityError, match="ck_order_status_history_status_changes"):
        await _insert(
            db_engine,
            OrderStatusHistory(
                order_id=order_id, field="order", old_status="paid", new_status="paid"
            ),
        )


@pytest.mark.integration
async def test_reservations_and_redemptions_must_reference_an_order(
    db_engine: AsyncEngine,
) -> None:
    with pytest.raises(IntegrityError, match="fk_inventory_reservations_order_id_orders"):
        await _insert(db_engine, InventoryReservation(order_id=uuid4(), expires_at=utc_now()))
    code_id, text = uuid4(), f"F{uuid4().hex[:10].upper()}"
    await _insert(db_engine, DiscountCode(id=code_id, code=text, type="fixed", value=1_000))
    try:
        with pytest.raises(IntegrityError, match="fk_discount_redemptions_order_id_orders"):
            await _insert(
                db_engine,
                DiscountRedemption(
                    discount_code_id=code_id,
                    order_id=uuid4(),
                    phone="+989121234567",
                    code=text,
                    amount=0,
                ),
            )
    finally:
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(DiscountCode).where(DiscountCode.id == code_id))


@pytest.mark.integration
async def test_referenced_shipping_method_cannot_be_hard_deleted(
    make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    order = await _order(db_engine, await make_order())
    with pytest.raises(IntegrityError, match="fk_orders_shipping_method_id_shipping_methods"):
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(
                delete(ShippingMethod).where(ShippingMethod.id == order.shipping_method_id)
            )
