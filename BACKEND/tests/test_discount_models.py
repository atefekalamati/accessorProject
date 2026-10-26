"""DiscountCode and DiscountRedemption schema, code normalization (DSC-01, ADR-042)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import MakeAccount, new_order
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import Cart, DiscountCode, DiscountRedemption, RedemptionStatus
from app.modules.discounts.codes import normalize_code
from app.shared.money import MAX_PRICE_TOMAN

# --- normalization (no database) -----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "stored"),
    [("  summer-25 ", "SUMMER-25"), ("vip_2026", "VIP_2026"), ("ABC", "ABC"), ("x" * 32, "X" * 32)],
)
def test_codes_are_trimmed_and_upper_cased(raw: str, stored: str) -> None:
    assert normalize_code(raw) == stored


@pytest.mark.parametrize(
    "raw",
    ["", "  ", "ab", "x" * 33, "has space", "dot.ted", "ıstanbul", "straße", "۱۲۳۴", "émile"],
)
def test_malformed_or_non_ascii_codes_are_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_code(raw)


# --- schema (integration) ------------------------------------------------------------


@pytest_asyncio.fixture
async def codes(db_engine: AsyncEngine) -> AsyncIterator[list[UUID]]:
    ids: list[UUID] = []
    yield ids
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            delete(DiscountRedemption).where(DiscountRedemption.discount_code_id.in_(ids))
        )
        await session.execute(delete(DiscountCode).where(DiscountCode.id.in_(ids)))


def _code(**values: Any) -> DiscountCode:
    base: dict[str, Any] = {
        "code": f"C{uuid4().hex[:10].upper()}",
        "type": "percent",
        "value": 1000,
    }
    return DiscountCode(**(base | values))


async def _insert(engine: AsyncEngine, row: Any, ids: list[UUID] | None = None) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(row)
    if ids is not None and isinstance(row, DiscountCode):
        ids.append(row.id)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"code": "lower"}, "code_format"),
        ({"code": "AB"}, "code_format"),
        # Breaks value_range too; PostgreSQL reports the first CHECK by name.
        ({"type": "bogo"}, "(valid_type|value_range)"),
        ({"type": "percent", "value": 0}, "value_range"),
        ({"type": "percent", "value": 10_001}, "value_range"),
        ({"type": "fixed", "value": 0}, "value_range"),
        ({"type": "fixed", "value": MAX_PRICE_TOMAN + 1}, "value_range"),
        ({"type": "fixed", "value": 5_000, "max_amount": 1_000}, "max_amount_range"),
        ({"max_amount": 0}, "max_amount_range"),
        ({"min_order_amount": 0}, "min_order_amount_range"),
        ({"usage_limit_total": 0}, "usage_limit_total_range"),
        ({"usage_limit_per_user": 0}, "usage_limit_per_user_range"),
        ({"usage_limit_total": 2, "usage_limit_per_user": 3}, "per_user_within_total"),
    ],
)
async def test_code_checks(
    db_engine: AsyncEngine, codes: list[UUID], values: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=f"ck_discount_codes_{constraint}"):
        await _insert(db_engine, _code(**values), codes)


@pytest.mark.integration
async def test_window_must_be_ordered(db_engine: AsyncEngine, codes: list[UUID]) -> None:
    now = utc_now()
    with pytest.raises(IntegrityError, match="ck_discount_codes_valid_window"):
        await _insert(db_engine, _code(starts_at=now, ends_at=now), codes)
    # Open ends are fine.
    await _insert(db_engine, _code(starts_at=now), codes)
    await _insert(db_engine, _code(ends_at=now), codes)


@pytest.mark.integration
async def test_code_is_unique_among_live_codes(db_engine: AsyncEngine, codes: list[UUID]) -> None:
    first = _code(code="SUMMER")
    await _insert(db_engine, first, codes)
    with pytest.raises(IntegrityError, match="uq_discount_codes_code"):
        await _insert(db_engine, _code(code="SUMMER"), codes)

    async with AsyncSession(db_engine) as session, session.begin():
        stored = await session.get(DiscountCode, first.id)
        assert stored is not None and stored.is_active is True
        stored.soft_delete()
    # A deleted code's text can be reused.
    await _insert(db_engine, _code(code="SUMMER"), codes)


async def _redemption(discount: DiscountCode, **values: Any) -> DiscountRedemption:
    base: dict[str, Any] = {
        "discount_code_id": discount.id,
        "order_id": values.pop("order_id", None) or await new_order(),
        "phone": "+989121234567",
        "code": discount.code,
        "amount": 5_000,
    }
    return DiscountRedemption(**(base | values))


@pytest.mark.integration
@pytest.mark.usefixtures("order_factory")
@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"status": "used"}, "valid_status"),
        ({"phone": "09121234567"}, "phone_format"),
        ({"code": "lower"}, "code_format"),
        ({"amount": -1}, "amount_range"),
        ({"status": "released"}, "released_has_time"),
        ({"released_at": "now"}, "released_has_time"),
        ({"status": "confirmed"}, "confirmed_has_time"),
        ({"confirmed_at": "now"}, "confirmed_has_time"),
        (
            {"status": "released", "released_at": "past", "confirmed_at": "now"},
            "released_after_confirmed",
        ),
    ],
)
async def test_redemption_checks(
    db_engine: AsyncEngine, codes: list[UUID], values: dict[str, Any], constraint: str
) -> None:
    code = _code()
    await _insert(db_engine, code, codes)
    now = utc_now()
    moments = {"now": now, "past": now - timedelta(hours=1)}
    values = {
        key: moments.get(value, value) if isinstance(value, str) else value
        for key, value in values.items()
    }
    with pytest.raises(IntegrityError, match=f"ck_discount_redemptions_{constraint}"):
        await _insert(db_engine, await _redemption(code, **values))


@pytest.mark.integration
@pytest.mark.usefixtures("order_factory")
async def test_zero_amount_and_paid_then_released_are_valid(
    db_engine: AsyncEngine, codes: list[UUID]
) -> None:
    code = _code()
    await _insert(db_engine, code, codes)
    now = utc_now()
    await _insert(db_engine, await _redemption(code, amount=0))
    await _insert(
        db_engine,
        await _redemption(
            code, status="released", confirmed_at=now, released_at=now + timedelta(1)
        ),
    )


@pytest.mark.integration
@pytest.mark.usefixtures("order_factory")
async def test_one_live_redemption_per_order(db_engine: AsyncEngine, codes: list[UUID]) -> None:
    code = _code()
    await _insert(db_engine, code, codes)
    order_id = await new_order()
    first = await _redemption(code, order_id=order_id)
    await _insert(db_engine, first)
    with pytest.raises(IntegrityError, match="uq_discount_redemptions_live_order"):
        await _insert(db_engine, await _redemption(code, order_id=order_id))

    async with AsyncSession(db_engine) as session, session.begin():
        stored = await session.get(DiscountRedemption, first.id)
        assert stored is not None
        stored.status = RedemptionStatus.RELEASED
        stored.released_at = utc_now()
    # Once released, the order may redeem again (a new attempt after expiry).
    await _insert(db_engine, await _redemption(code, order_id=order_id))

    # A paid (confirmed) redemption blocks a second one as well.
    paid_order = await new_order()
    now = utc_now()
    await _insert(
        db_engine,
        await _redemption(code, order_id=paid_order, status="confirmed", confirmed_at=now),
    )
    with pytest.raises(IntegrityError, match="uq_discount_redemptions_live_order"):
        await _insert(db_engine, await _redemption(code, order_id=paid_order))


@pytest.mark.integration
@pytest.mark.usefixtures("order_factory")
async def test_used_code_cannot_be_hard_deleted(db_engine: AsyncEngine, codes: list[UUID]) -> None:
    code = _code()
    await _insert(db_engine, code, codes)
    await _insert(db_engine, await _redemption(code))
    with pytest.raises(IntegrityError, match="fk_discount_redemptions_discount_code_id"):
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(DiscountCode).where(DiscountCode.id == code.id))


@pytest.mark.integration
async def test_cart_keeps_a_code_reference(
    db_engine: AsyncEngine, codes: list[UUID], make_account: MakeAccount
) -> None:
    account = await make_account("customer")
    code = _code()
    await _insert(db_engine, code, codes)
    cart = Cart(user_id=account.id, discount_code_id=code.id)
    await _insert(db_engine, cart)

    async with AsyncSession(db_engine) as session:
        stored = (await session.scalars(select(Cart).where(Cart.id == cart.id))).one()
    assert stored.discount_code_id == code.id
