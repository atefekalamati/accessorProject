"""Pure discount code rules (DSC-02, ADR-043)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import ErrorCode
from app.db.models import DiscountType
from app.modules.cart.view import price_with_code
from app.modules.discounts.rules import (
    CodeRules,
    Rejection,
    Usage,
    check_code,
    discount_error,
    to_code_discount,
)
from app.modules.pricing.calculator import LineInput, PricingPolicy, VariantPrice, price_order

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
TICK = timedelta(microseconds=1)
RULES = CodeRules(
    type=DiscountType.PERCENT,
    value=1_000,
    max_amount=None,
    min_order_amount=None,
    starts_at=None,
    ends_at=None,
    usage_limit_total=None,
    usage_limit_per_user=None,
    is_active=True,
    deleted=False,
)
FREE = Usage(total_live=0, user_live=0)


def _check(
    rules: CodeRules | None, subtotal: int = 100_000, usage: Usage = FREE
) -> Rejection | None:
    return check_code(rules, at=NOW, subtotal=subtotal, usage=usage)


@pytest.mark.parametrize(
    ("changes", "usage", "subtotal", "expected"),
    [
        ({}, FREE, 100_000, None),
        ({"deleted": True}, FREE, 100_000, Rejection.INVALID),
        ({"is_active": False}, FREE, 100_000, Rejection.INVALID),
        ({"starts_at": NOW}, FREE, 100_000, None),  # valid from exactly starts_at
        # Not started yet looks like an unknown code (no upcoming promo leaks).
        ({"starts_at": NOW + TICK}, FREE, 100_000, Rejection.INVALID),
        ({"ends_at": NOW}, FREE, 100_000, Rejection.EXPIRED),  # half-open: ends_at is out
        ({"ends_at": NOW + TICK}, FREE, 100_000, None),
        ({"usage_limit_total": None}, Usage(10**6, 10**6), 100_000, None),  # unlimited
        ({"usage_limit_total": 3}, Usage(2, 0), 100_000, None),  # limit - 1
        ({"usage_limit_total": 3}, Usage(3, 0), 100_000, Rejection.EXHAUSTED),
        ({"usage_limit_per_user": 1}, Usage(5, 0), 100_000, None),
        ({"usage_limit_per_user": 1}, Usage(5, 1), 100_000, Rejection.USER_EXHAUSTED),
        # A guest has no verified mobile: the per-user limit waits for POST /orders.
        ({"usage_limit_per_user": 1}, Usage(5, None), 100_000, None),
        ({"min_order_amount": 100_000}, FREE, 100_000, None),
        ({"min_order_amount": 100_001}, FREE, 100_000, Rejection.BELOW_MINIMUM),
    ],
)
def test_rules(
    changes: dict[str, object], usage: Usage, subtotal: int, expected: Rejection | None
) -> None:
    assert _check(replace(RULES, **changes), subtotal, usage) is expected  # type: ignore[arg-type]


def test_unknown_code_is_invalid() -> None:
    assert _check(None) is Rejection.INVALID


def test_first_failing_rule_wins() -> None:
    broken = replace(
        RULES,
        starts_at=NOW + TICK,
        ends_at=NOW + timedelta(days=1),
        usage_limit_total=1,
        usage_limit_per_user=1,
        min_order_amount=10**9,
    )
    order = [
        (replace(broken, is_active=False), Rejection.INVALID),
        (broken, Rejection.INVALID),  # not started
        (replace(broken, starts_at=None, ends_at=NOW), Rejection.EXPIRED),
        (replace(broken, starts_at=None), Rejection.EXHAUSTED),
        (replace(broken, starts_at=None, usage_limit_total=None), Rejection.USER_EXHAUSTED),
        (
            replace(broken, starts_at=None, usage_limit_total=None, usage_limit_per_user=None),
            Rejection.BELOW_MINIMUM,
        ),
    ]
    for rules, expected in order:
        assert _check(rules, usage=Usage(1, 1)) is expected


def test_conversion_to_the_calculator() -> None:
    percent = to_code_discount(replace(RULES, value=2_500, max_amount=40_000))
    fixed = to_code_discount(replace(RULES, type=DiscountType.FIXED, value=15_000))

    assert (percent.percent_bps, percent.max_amount, percent.fixed_amount) == (2_500, 40_000, None)
    assert (fixed.percent_bps, fixed.fixed_amount, fixed.max_amount) == (None, 15_000, None)
    assert percent.eligible_keys is None and fixed.eligible_keys is None  # whole cart (D33)


def test_amounts_come_only_from_the_calculator() -> None:
    lines = [LineInput(key="a", price=VariantPrice(base_price=100_000), quantity=3)]
    capped = price_order(
        lines,
        PricingPolicy(),
        at=NOW,
        code=to_code_discount(replace(RULES, value=5_000, max_amount=40_000)),
    )
    oversized = price_order(
        lines,
        PricingPolicy(),
        at=NOW,
        code=to_code_discount(replace(RULES, type=DiscountType.FIXED, value=10**9)),
    )

    assert (capped.discount_code_amount, capped.grand_total) == (40_000, 260_000)
    # A fixed amount above the cart is capped at the eligible subtotal; never negative.
    assert (oversized.discount_code_amount, oversized.grand_total) == (300_000, 0)


def test_error_shape_has_no_numbers() -> None:
    error = discount_error(Rejection.EXHAUSTED)

    assert (error.status_code, error.code) == (422, ErrorCode.DISCOUNT_NOT_APPLICABLE)
    assert error.details == [{"field": "code", "type": "exhausted"}]
    assert not any(character.isdigit() for character in error.message)


def test_naive_instant_is_rejected() -> None:
    with pytest.raises(ValueError):
        check_code(RULES, at=NOW.replace(tzinfo=None), subtotal=1, usage=FREE)


def test_minimum_uses_the_price_after_product_discounts() -> None:
    """ADR-043: the basis is the total after product discounts, as price_with_code uses."""
    lines = [
        LineInput(key="sale", price=VariantPrice(base_price=100_000, sale_price=80_000), quantity=1)
    ]

    pricing, rejection = price_with_code(
        lines, PricingPolicy(), NOW, replace(RULES, min_order_amount=90_000), FREE
    )
    passing, ok = price_with_code(
        lines, PricingPolicy(), NOW, replace(RULES, min_order_amount=80_000), FREE
    )

    assert rejection is Rejection.BELOW_MINIMUM and pricing.discount_code_amount == 0
    assert ok is None and passing.discount_code_amount == 8_000
