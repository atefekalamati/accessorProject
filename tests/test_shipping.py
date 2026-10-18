"""Shipping methods: calculator, basis, schema and the public list (ADDR-02, ADR-045)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.errors import AppError
from app.core.time import utc_now
from app.db.models import DiscountType, ShippingMethod
from app.modules.cart.view import price_with_code
from app.modules.discounts.rules import CodeRules, Usage
from app.modules.pricing.calculator import (
    CodeDiscount,
    LineInput,
    PricingPolicy,
    VariantPrice,
    price_order,
)
from app.modules.shipping.calculator import (
    FlatRateCalculator,
    ShippingContext,
    ShippingRates,
    shipping_basis,
)
from app.modules.shipping.repository import ShippingRepository
from app.shared.money import MAX_PRICE_TOMAN, RoundingMode

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
FLAT = FlatRateCalculator()


def _quote(cost: int, threshold: int | None, basis: int) -> int:
    return FLAT.quote(ShippingRates(cost, threshold), ShippingContext(basis=basis))


# --- calculator (no database) --------------------------------------------------------


@pytest.mark.parametrize(
    ("cost", "threshold", "basis", "expected"),
    [
        (30_000, None, 10**9, 30_000),  # no threshold: never free
        (30_000, 500_000, 499_999, 30_000),
        (30_000, 500_000, 500_000, 0),  # reaching the threshold is free
        (30_000, 500_000, 500_001, 0),
        (0, None, 0, 0),  # cost 0 is always free
        (0, 500_000, 1, 0),
    ],
)
def test_flat_rate(cost: int, threshold: int | None, basis: int, expected: int) -> None:
    assert _quote(cost, threshold, basis) == expected


@pytest.mark.parametrize(
    ("rates", "error"),
    [
        ({"cost": -1}, ValueError),
        ({"cost": 1.5}, TypeError),
        ({"cost": True}, TypeError),
        ({"cost": MAX_PRICE_TOMAN + 1}, ValueError),
        ({"cost": 1, "free_shipping_threshold": 0}, ValueError),
        ({"cost": 1, "free_shipping_threshold": MAX_PRICE_TOMAN + 1}, ValueError),
        ({"cost": 1, "free_shipping_threshold": 1.5}, TypeError),
    ],
)
def test_rates_are_validated(rates: dict[str, Any], error: type[Exception]) -> None:
    with pytest.raises(error):
        ShippingRates(**rates)


@pytest.mark.parametrize(
    ("basis", "error"),
    [(-1, ValueError), (1.0, TypeError), (True, TypeError), (MAX_PRICE_TOMAN + 1, ValueError)],
)
def test_context_is_validated(basis: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        ShippingContext(basis=basis)


def _lines() -> list[LineInput]:
    return [
        LineInput(
            key="a",
            price=VariantPrice(base_price=200_000, sale_price=150_000, tax_enabled=True),
            quantity=2,
        ),
        LineInput(key="b", price=VariantPrice(base_price=100_000), quantity=1),
    ]


def test_basis_is_after_every_discount_before_tax() -> None:
    policy = PricingPolicy(tax_enabled=True, tax_rate_bps=900)
    pricing = price_order(_lines(), policy, at=NOW, code=CodeDiscount(fixed_amount=40_000))

    # 400 000 original + 100 000, minus 100 000 sale, minus 40 000 code; tax is not in it.
    assert shipping_basis(pricing) == 360_000
    assert pricing.tax_amount > 0


def test_a_code_can_push_the_basis_below_the_threshold() -> None:
    without = price_order(_lines(), PricingPolicy(), at=NOW)
    with_code = price_order(
        _lines(), PricingPolicy(), at=NOW, code=CodeDiscount(fixed_amount=50_000)
    )

    assert _quote(30_000, 400_000, shipping_basis(without)) == 0
    assert _quote(30_000, 400_000, shipping_basis(with_code)) == 30_000


def test_a_code_that_does_not_apply_leaves_the_basis_alone() -> None:
    rules = CodeRules(
        type=DiscountType.FIXED,
        value=50_000,
        max_amount=None,
        min_order_amount=10**9,  # never reached: the code is rejected
        starts_at=None,
        ends_at=None,
        usage_limit_total=None,
        usage_limit_per_user=None,
        is_active=True,
        deleted=False,
    )
    pricing, rejection = price_with_code(_lines(), PricingPolicy(), NOW, rules, Usage(0, 0))

    assert rejection is not None and pricing.discount_code_amount == 0
    assert shipping_basis(pricing) == 400_000


def test_shipping_is_never_rounded_or_taxed_and_changes_nothing_else() -> None:
    policy = PricingPolicy(
        tax_enabled=True, tax_rate_bps=900, rounding_mode=RoundingMode.UP, rounding_step=1_000
    )
    code = CodeDiscount(percent_bps=1_000)
    base = price_order(_lines(), policy, at=NOW, code=code)
    shipped = price_order(_lines(), policy, at=NOW, code=code, shipping=12_345)

    assert shipped.shipping_amount == 12_345
    assert shipped.lines == base.lines
    assert (shipped.tax_amount, shipped.discount_code_amount) == (
        base.tax_amount,
        base.discount_code_amount,
    )
    assert shipped.grand_total == base.grand_total + 12_345


# --- schema and the public list (integration) ----------------------------------------


@pytest_asyncio.fixture
async def methods(
    db_engine: AsyncEngine,
) -> AsyncIterator[Callable[..., Awaitable[ShippingMethod]]]:
    ids: list[UUID] = []

    async def make(**values: Any) -> ShippingMethod:
        base: dict[str, Any] = {"title": f"Post {uuid4().hex[:6]}", "cost": 30_000}
        method = ShippingMethod(**(base | values))
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(method)
        ids.append(method.id)
        return method

    yield make
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(ShippingMethod).where(ShippingMethod.id.in_(ids)))


@pytest.mark.integration
@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"title": " padded "}, "title_format"),
        ({"title": ""}, "title_format"),
        ({"cost": -1}, "cost_range"),
        ({"free_shipping_threshold": 0}, "free_shipping_threshold_range"),
        ({"display_order": -1}, "display_order_non_negative"),
    ],
)
async def test_method_checks(methods: Any, values: dict[str, Any], constraint: str) -> None:
    with pytest.raises(DBAPIError, match=f"ck_shipping_methods_{constraint}"):
        await methods(**values)


@pytest.mark.integration
async def test_public_list_shows_selectable_methods_in_order(
    auth_client: AsyncClient, methods: Any, db_engine: AsyncEngine
) -> None:
    client = auth_client
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(ShippingMethod))
    empty = await client.get("/api/v1/shipping-methods")
    assert (empty.status_code, empty.json()) == (200, [])

    late = await methods(title="Courier", display_order=2)
    tie_b = await methods(title="Post B", display_order=1, free_shipping_threshold=500_000)
    tie_a = await methods(title="Post A", display_order=1, description="3-5 days")
    await methods(title="Hidden", is_active=False)
    await methods(title="Gone", deleted_at=utc_now())

    response = await client.get("/api/v1/shipping-methods")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(tie_a.id), str(tie_b.id), str(late.id)]
    assert set(body[0]) == {"id", "title", "description", "cost", "free_shipping_threshold"}
    assert body[1]["free_shipping_threshold"] == 500_000
    bad = await client.get("/api/v1/shipping-methods", params={"city": "Tehran"})
    assert bad.status_code == 400


@pytest.mark.integration
async def test_checkout_lookup_gives_one_answer_for_any_unusable_id(
    methods: Any, db_engine: AsyncEngine
) -> None:
    usable = await methods()
    inactive = await methods(is_active=False)
    deleted = await methods(deleted_at=utc_now())

    async with AsyncSession(db_engine) as session, session.begin():
        repository = ShippingRepository(session)
        assert (await repository.get_selectable(usable.id)).id == usable.id
        for method_id in (inactive.id, deleted.id, uuid4()):
            with pytest.raises(AppError) as caught:
                await repository.get_selectable(method_id)
            assert caught.value.status_code == 422
            assert caught.value.details[0]["type"] == "shipping_method_unavailable"
