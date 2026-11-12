from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import Any

import pytest

from app.modules.pricing.calculator import (
    CodeDiscount,
    LineInput,
    OrderPricing,
    PricingPolicy,
    UnitPrice,
    VariantPrice,
    allocate,
    price_order,
    unit_price,
)
from app.shared.money import MAX_PRICE_TOMAN, RoundingMode, round_amount

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
TICK = timedelta(microseconds=1)
NO_TAX = PricingPolicy()
TAX_10 = PricingPolicy(tax_enabled=True, tax_rate_bps=1000)


def _line(key: str, base: int, quantity: int = 1, **price: Any) -> LineInput:
    return LineInput(key=key, price=VariantPrice(base_price=base, **price), quantity=quantity)


# --- unit price ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "on_sale"),
    [
        (None, None, True),
        (NOW, None, True),  # starts exactly now
        (NOW + TICK, None, False),  # not started yet
        (None, NOW, False),  # ended exactly now (half-open window)
        (None, NOW + TICK, True),
        (NOW - HOUR, NOW + HOUR, True),
        (NOW - 2 * HOUR, NOW - HOUR, False),
    ],
)
def test_sale_window_is_half_open(
    start: datetime | None, end: datetime | None, on_sale: bool
) -> None:
    price = VariantPrice(150_000, 120_000, start, end)

    unit = unit_price(price, NOW)

    assert unit is not None
    assert unit.final == (120_000 if on_sale else 150_000)
    assert unit.on_sale is on_sale


def test_unit_price_discount_fields() -> None:
    assert unit_price(VariantPrice(30_000, 20_000), NOW) == UnitPrice(
        original=30_000, final=20_000, discount_amount=10_000, discount_percent=33, on_sale=True
    )
    assert unit_price(VariantPrice(1000), NOW) == UnitPrice(1000, 1000, 0, 0, False)


def test_unpriced_variant_has_no_unit_price() -> None:
    assert unit_price(VariantPrice(None), NOW) is None


@pytest.mark.parametrize(
    ("price", "error"),
    [
        (VariantPrice(1000.0), TypeError),  # type: ignore[arg-type]
        (VariantPrice(True), TypeError),
        (VariantPrice(0), ValueError),
        (VariantPrice(1000, 1001), ValueError),
        (VariantPrice(1000, 900, datetime(2026, 1, 1)), ValueError),  # naive time
    ],
)
def test_unit_price_rejects_invalid_prices(price: VariantPrice, error: type[Exception]) -> None:
    with pytest.raises(error):
        unit_price(price, NOW)


def test_unit_price_needs_an_aware_instant() -> None:
    with pytest.raises(ValueError):
        unit_price(VariantPrice(1000), datetime(2026, 1, 1))


# --- allocation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "weights", "shares"),
    [
        (10, [1, 1, 1], [4, 3, 3]),  # ties go to the earlier line
        (2, [1, 1, 1], [1, 1, 0]),
        (100, [50, 30, 20], [50, 30, 20]),
        (7, [0, 5, 0], [0, 7, 0]),
        (0, [0, 0], [0, 0]),
        (5, [], []),
    ],
)
def test_allocate(total: int, weights: list[int], shares: list[int]) -> None:
    if not weights:
        with pytest.raises(ValueError):
            allocate(total, weights)
        return
    assert allocate(total, weights) == shares


def test_allocate_rejects_positive_total_over_zero_weights() -> None:
    with pytest.raises(ValueError):
        allocate(1, [0, 0])


# --- orders --------------------------------------------------------------------------


def test_order_without_discounts_or_tax() -> None:
    result = price_order([_line("a", 1000, 2), _line("b", 500)], NO_TAX, at=NOW, shipping=300)

    assert (result.subtotal, result.product_discount_total) == (2500, 0)
    assert (result.discount_code_amount, result.tax_amount) == (0, 0)
    assert (result.shipping_amount, result.grand_total) == (300, 2800)
    assert [line.total for line in result.lines] == [2000, 500]


def test_product_discount_and_percent_code() -> None:
    lines = [_line("a", 10_000, 2, sale_price=8_000), _line("b", 5_000)]

    result = price_order(lines, NO_TAX, at=NOW, code=CodeDiscount(percent_bps=1000))

    assert result.subtotal == 25_000
    assert result.product_discount_total == 4_000
    assert result.discount_code_amount == 2_100  # 10% of 21,000
    assert [line.code_discount for line in result.lines] == [1_600, 500]
    assert result.grand_total == 18_900


def test_code_respects_cap_and_eligible_lines() -> None:
    lines = [_line("a", 10_000), _line("b", 5_000)]
    capped = CodeDiscount(percent_bps=5000, max_amount=1_000)
    only_b = CodeDiscount(fixed_amount=9_999, eligible_keys=frozenset({"b"}))

    capped_result = price_order(lines, NO_TAX, at=NOW, code=capped)
    only_b_result = price_order(lines, NO_TAX, at=NOW, code=only_b)

    assert capped_result.discount_code_amount == 1_000
    # A fixed code never discounts more than the eligible lines are worth.
    assert only_b_result.discount_code_amount == 5_000
    assert [line.code_discount for line in only_b_result.lines] == [0, 5_000]
    assert only_b_result.grand_total == 10_000


def test_code_rounding_up_never_exceeds_the_eligible_subtotal() -> None:
    policy = PricingPolicy(rounding_mode=RoundingMode.UP, rounding_step=1000)

    result = price_order([_line("a", 1_500)], policy, at=NOW, code=CodeDiscount(percent_bps=9_999))

    assert result.discount_code_amount == 1_500
    assert result.grand_total == 0


def test_tax_after_discounts_on_taxable_lines_only() -> None:
    lines = [
        _line("taxed", 10_000, tax_enabled=True),
        _line("exempt", 10_000, tax_enabled=False),
    ]

    result = price_order(
        lines, TAX_10, at=NOW, code=CodeDiscount(fixed_amount=2_000), shipping=5_000
    )

    # Code split 1,000 / 1,000; tax = 10% of (10,000 − 1,000); shipping untaxed.
    assert [line.code_discount for line in result.lines] == [1_000, 1_000]
    assert [line.tax for line in result.lines] == [900, 0]
    assert result.tax_amount == 900
    assert result.grand_total == 20_000 - 2_000 + 900 + 5_000


def test_tax_is_off_unless_the_store_enables_it() -> None:
    lines = [_line("a", 10_000, tax_enabled=True)]

    assert price_order(lines, NO_TAX, at=NOW).tax_amount == 0
    assert price_order(lines, PricingPolicy(tax_enabled=True), at=NOW).tax_amount == 0


@pytest.mark.parametrize(
    ("mode", "step", "tax"),
    [
        (RoundingMode.NEAREST, 1, 1235),  # 1234.5 rounds half up
        (RoundingMode.DOWN, 1, 1234),
        (RoundingMode.UP, 1, 1235),
        (RoundingMode.NEAREST, 1000, 1000),
        (RoundingMode.UP, 1000, 2000),
        (RoundingMode.DOWN, 1000, 1000),
    ],
)
def test_tax_is_rounded_once(mode: RoundingMode, step: int, tax: int) -> None:
    policy = PricingPolicy(
        tax_enabled=True, tax_rate_bps=1000, rounding_mode=mode, rounding_step=step
    )
    lines = [_line("a", 4_115, tax_enabled=True), _line("b", 8_230, tax_enabled=True)]

    result = price_order(lines, policy, at=NOW)

    assert result.tax_amount == tax
    assert sum(line.tax for line in result.lines) == tax


def test_large_amounts_stay_exact() -> None:
    result = price_order([_line("a", MAX_PRICE_TOMAN, 1000)], TAX_10, at=NOW)

    assert result.grand_total == MAX_PRICE_TOMAN * 1000


def test_fingerprint_tracks_price_and_settings_versions() -> None:
    lines = [_line("a", 1000, price_version=1), _line("b", 1000, price_version=4)]
    reordered = list(reversed(lines))
    bumped = [_line("a", 1000, price_version=2), lines[1]]

    base = price_order(lines, NO_TAX, at=NOW).fingerprint

    assert price_order(reordered, NO_TAX, at=NOW).fingerprint == base
    assert price_order(bumped, NO_TAX, at=NOW).fingerprint != base
    assert price_order(lines, PricingPolicy(version=2), at=NOW).fingerprint != base


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"lines": [_line("a", 1000, 0)]}, ValueError),
        ({"lines": [_line("a", 1000, 1.5)]}, TypeError),  # type: ignore[arg-type]
        ({"lines": [_line("a", 1000), _line("a", 500)]}, ValueError),
        ({"lines": [LineInput("a", VariantPrice(None), 1)]}, ValueError),
        ({"shipping": -1}, ValueError),
        ({"shipping": 10.0}, TypeError),
        ({"code": CodeDiscount()}, ValueError),
        ({"code": CodeDiscount(percent_bps=10, fixed_amount=10)}, ValueError),
        ({"code": CodeDiscount(percent_bps=10_001)}, ValueError),
        ({"code": CodeDiscount(fixed_amount=True)}, TypeError),
        ({"policy": PricingPolicy(tax_rate_bps=10_001)}, ValueError),
    ],
)
def test_price_order_rejects_invalid_input(kwargs: dict[str, Any], error: type[Exception]) -> None:
    arguments: dict[str, Any] = {"lines": [_line("a", 1000)], "policy": NO_TAX, **kwargs}

    with pytest.raises(error):
        price_order(arguments.pop("lines"), arguments.pop("policy"), at=NOW, **arguments)


# --- invariants over random carts (ADR-031) ------------------------------------------


def _random_cart(rng: random.Random) -> dict[str, Any]:
    lines = []
    for index in range(rng.randint(1, 6)):
        base = rng.choice([1, 999, rng.randint(1, 10_000_000), rng.randint(1, MAX_PRICE_TOMAN)])
        sale = rng.choice([None, rng.randint(1, base)])
        start = rng.choice([None, NOW - HOUR, NOW + HOUR, NOW])
        end = rng.choice([None, NOW + HOUR, NOW, NOW - TICK])
        if sale is None or (start is not None and end is not None and start >= end):
            start = end = None
        price = VariantPrice(base, sale, start, end, rng.random() < 0.5, rng.randint(0, 9))
        lines.append(LineInput(f"line-{index}", price, rng.randint(1, 50)))
    keys = [line.key for line in lines]
    code: CodeDiscount | None = None
    kind = rng.choice(["none", "percent", "fixed"])
    if kind != "none":
        eligible = rng.choice([None, frozenset(rng.sample(keys, rng.randint(0, len(keys))))])
        scale = max(line.price.base_price or 0 for line in lines) * 2
        cap = rng.choice([None, rng.randint(0, scale)])
        if kind == "percent":
            code = CodeDiscount(
                percent_bps=rng.randint(0, 10_000), max_amount=cap, eligible_keys=eligible
            )
        else:
            code = CodeDiscount(
                fixed_amount=rng.randint(0, scale), max_amount=cap, eligible_keys=eligible
            )
    policy = PricingPolicy(
        tax_enabled=rng.random() < 0.7,
        tax_rate_bps=rng.randint(0, 10_000),
        rounding_mode=rng.choice(list(RoundingMode)),
        rounding_step=rng.choice([1, 10, 100, 1000, 10_000]),
        version=rng.randint(1, 5),
    )
    return {
        "lines": lines,
        "policy": policy,
        "code": code,
        "shipping": rng.choice([0, rng.randint(0, 500_000)]),
    }


def _check_invariants(result: OrderPricing, cart: dict[str, Any]) -> None:
    lines = result.lines
    assert sum(line.subtotal for line in lines) == result.subtotal
    assert sum(line.product_discount for line in lines) == result.product_discount_total
    assert sum(line.code_discount for line in lines) == result.discount_code_amount
    assert sum(line.tax for line in lines) == result.tax_amount
    assert sum(line.total for line in lines) + result.shipping_amount == result.grand_total
    assert result.grand_total == (
        result.subtotal
        - result.product_discount_total
        - result.discount_code_amount
        + result.tax_amount
        + result.shipping_amount
    )
    for line in lines:
        net = line.subtotal - line.product_discount
        assert 0 <= line.code_discount <= net
        assert line.tax >= 0 and line.total >= 0
        assert line.total == net - line.code_discount + line.tax
    code: CodeDiscount | None = cart["code"]
    eligible = sum(
        line.subtotal - line.product_discount
        for line in lines
        if code is not None and (code.eligible_keys is None or line.key in code.eligible_keys)
    )
    assert 0 <= result.discount_code_amount <= eligible
    assert result.shipping_amount == cart["shipping"]
    assert result.grand_total >= 0

    # Shares only go to the lines they belong to.
    policy: PricingPolicy = cart["policy"]
    inputs = {line.key: line for line in cart["lines"]}
    for line in lines:
        if code is None or (code.eligible_keys is not None and line.key not in code.eligible_keys):
            assert line.code_discount == 0
        if not (policy.tax_enabled and inputs[line.key].price.tax_enabled):
            assert line.tax == 0

    # Independent oracle: each component rounded exactly once (ADR-031).
    mode, step = policy.rounding_mode, policy.rounding_step
    if code is None:
        expected_code = 0
    else:
        cap = eligible if code.max_amount is None else min(eligible, code.max_amount)
        if code.percent_bps is not None:
            raw = round_amount(Fraction(eligible * code.percent_bps, 10_000), mode, step)
        else:
            raw = code.fixed_amount or 0
        expected_code = min(raw, cap)
    assert result.discount_code_amount == expected_code
    taxable = [
        line.subtotal - line.product_discount - line.code_discount
        for line in lines
        if policy.tax_enabled and inputs[line.key].price.tax_enabled
    ]
    expected_tax = round_amount(Fraction(sum(taxable) * policy.tax_rate_bps, 10_000), mode, step)
    assert result.tax_amount == expected_tax

    # Largest remainder: every share is within one unit of its exact proportion.
    code_weights = [
        line.subtotal - line.product_discount
        if code is not None and (code.eligible_keys is None or line.key in code.eligible_keys)
        else 0
        for line in lines
    ]
    _check_split(result.discount_code_amount, code_weights, [line.code_discount for line in lines])


def _check_split(total: int, weights: list[int], shares: list[int]) -> None:
    weight_sum = sum(weights)
    assert sum(shares) == total
    for weight, share in zip(weights, shares, strict=True):
        if weight_sum == 0 or weight == 0:
            assert share == 0
        else:
            assert abs(share * weight_sum - total * weight) < weight_sum


def test_invariants_over_seeded_random_carts() -> None:
    rng = random.Random(20261011)
    for _ in range(1500):
        cart = _random_cart(rng)

        result = price_order(
            cart["lines"], cart["policy"], at=NOW, code=cart["code"], shipping=cart["shipping"]
        )
        again = price_order(
            cart["lines"], cart["policy"], at=NOW, code=cart["code"], shipping=cart["shipping"]
        )

        _check_invariants(result, cart)
        assert again == result
        assert len(result.fingerprint) == 64
        shuffled = list(cart["lines"])
        rng.shuffle(shuffled)
        reordered = price_order(
            shuffled, cart["policy"], at=NOW, code=cart["code"], shipping=cart["shipping"]
        )
        assert reordered.fingerprint == result.fingerprint
        assert (reordered.discount_code_amount, reordered.tax_amount) == (
            result.discount_code_amount,
            result.tax_amount,
        )
        assert reordered.grand_total == result.grand_total


def test_allocate_properties_over_seeded_random_inputs() -> None:
    rng = random.Random(7)
    for _ in range(2000):
        weights = [rng.choice([0, rng.randint(1, 10), rng.randint(1, 10**12)]) for _ in range(5)]
        if not sum(weights):
            continue
        total = rng.randint(0, sum(weights))

        shares = allocate(total, weights)

        _check_split(total, weights, shares)
        assert all(share <= weight for share, weight in zip(shares, weights, strict=True))


@pytest.mark.parametrize(
    ("total", "weights", "error"),
    [(-1, [1], ValueError), (1, [-1, 2], ValueError), (1, [True], TypeError)],
)
def test_allocate_rejects_invalid_input(
    total: int, weights: list[int], error: type[Exception]
) -> None:
    with pytest.raises(error):
        allocate(total, weights)


@pytest.mark.parametrize(
    "changed",
    [
        _line("a", 2000, price_version=1),
        _line("a", 1000, price_version=1, tax_enabled=True),
        _line("a", 1000, price_version=1, sale_price=900),
    ],
)
def test_fingerprint_tracks_prices_even_without_a_version_bump(changed: LineInput) -> None:
    base = price_order([_line("a", 1000, price_version=1)], NO_TAX, at=NOW).fingerprint

    assert price_order([changed], NO_TAX, at=NOW).fingerprint != base


def test_line_keys_must_be_str_or_uuid() -> None:
    with pytest.raises(TypeError):
        price_order([LineInput(1, VariantPrice(1000), 1)], NO_TAX, at=NOW)  # type: ignore[arg-type]


# --- review additions ----------------------------------------------------------------


def test_fingerprint_changes_when_a_sale_window_ends() -> None:
    lines = [_line("a", 1000, sale_price=800, sale_end_at=NOW)]

    during = price_order(lines, NO_TAX, at=NOW - TICK)
    after = price_order(lines, NO_TAX, at=NOW)

    assert (during.grand_total, after.grand_total) == (800, 1000)
    assert during.fingerprint != after.fingerprint


def test_fixed_code_is_not_rounded_but_percent_code_is() -> None:
    policy = PricingPolicy(rounding_mode=RoundingMode.NEAREST, rounding_step=1000)
    lines = [_line("a", 100_000)]

    fixed = price_order(lines, policy, at=NOW, code=CodeDiscount(fixed_amount=15_500))
    percent = price_order(lines, policy, at=NOW, code=CodeDiscount(percent_bps=1_550))

    assert fixed.discount_code_amount == 15_500
    assert percent.discount_code_amount == 16_000  # 15,500 rounded half up to 1000


def test_rounding_up_never_passes_the_code_cap() -> None:
    policy = PricingPolicy(rounding_mode=RoundingMode.UP, rounding_step=1000)
    code = CodeDiscount(percent_bps=5000, max_amount=15_500)

    result = price_order([_line("a", 100_000)], policy, at=NOW, code=code)

    assert result.discount_code_amount == 15_500


@pytest.mark.parametrize(
    ("code", "amount", "applied"),
    [
        (CodeDiscount(percent_bps=0), 0, True),
        (CodeDiscount(percent_bps=10_000), 3_000, True),
        (CodeDiscount(fixed_amount=3_000), 3_000, True),
        (CodeDiscount(percent_bps=5000, eligible_keys=frozenset({"b"})), 1_000, True),
        (CodeDiscount(percent_bps=5000, eligible_keys=frozenset()), 0, False),
        (None, 0, False),
    ],
)
def test_code_amounts_and_applied_flag(
    code: CodeDiscount | None, amount: int, applied: bool
) -> None:
    result = price_order([_line("a", 1_000), _line("b", 2_000)], NO_TAX, at=NOW, code=code)

    assert result.discount_code_amount == amount
    assert result.code_applied is applied


def test_tax_rounding_up_with_a_large_step_is_the_configured_policy() -> None:
    # ADR-031: rounding happens once per component, so a tiny base can get a whole step.
    policy = PricingPolicy(
        tax_enabled=True,
        tax_rate_bps=1000,
        rounding_mode=RoundingMode.UP,
        rounding_step=1000,
    )

    result = price_order([_line("a", 100, tax_enabled=True)], policy, at=NOW)

    assert result.tax_amount == 1000


def test_all_exempt_lines_pay_no_tax() -> None:
    lines = [_line("a", 1000), _line("b", 2000)]

    assert price_order(lines, TAX_10, at=NOW).tax_amount == 0


def test_sale_equal_to_base_is_not_on_sale() -> None:
    unit = unit_price(VariantPrice(1000, 1000), NOW)

    assert unit is not None
    assert (unit.final, unit.on_sale, unit.discount_percent) == (1000, False, 0)


def test_empty_order_prices_to_shipping_only() -> None:
    result = price_order([], NO_TAX, at=NOW)

    assert (result.grand_total, result.lines, result.currency) == (0, (), "TOMAN")
    assert result.calculated_at == NOW


def test_amounts_beyond_bigint_are_rejected() -> None:
    lines = [_line(f"l{i}", MAX_PRICE_TOMAN, 1_000_000) for i in range(10)]

    with pytest.raises(ValueError, match="BIGINT"):
        price_order(lines, NO_TAX, at=NOW)


@pytest.mark.parametrize(
    ("policy", "error"),
    [
        (PricingPolicy(rounding_mode="up"), TypeError),  # type: ignore[arg-type]
        (PricingPolicy(rounding_step=0), ValueError),
        (PricingPolicy(rounding_step=1_000_001), ValueError),
        (PricingPolicy(tax_enabled=1), TypeError),  # type: ignore[arg-type]
        (PricingPolicy(version=0), ValueError),
        (PricingPolicy(tax_rate_bps=-1), ValueError),
    ],
)
def test_policy_is_type_checked(policy: PricingPolicy, error: type[Exception]) -> None:
    with pytest.raises(error):
        price_order([_line("a", 1000)], policy, at=NOW)


@pytest.mark.parametrize(
    ("price", "quantity"),
    [
        (VariantPrice(MAX_PRICE_TOMAN + 1), 1),
        (VariantPrice(1000, 900, NOW, NOW), 1),  # empty window
        (VariantPrice(1000, None, NOW), 1),  # window without a sale price
        (VariantPrice(1000, price_version=-1), 1),
        (VariantPrice(1000), 1_000_001),
    ],
)
def test_line_guards(price: VariantPrice, quantity: int) -> None:
    with pytest.raises(ValueError):
        price_order([LineInput("a", price, quantity)], NO_TAX, at=NOW)


def test_naive_instant_is_rejected_for_orders() -> None:
    with pytest.raises(ValueError):
        price_order([_line("a", 1000)], NO_TAX, at=datetime(2026, 1, 1))
