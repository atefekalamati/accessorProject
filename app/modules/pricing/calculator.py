"""Pure price calculation: sale window, product and code discounts, tax, shipping (PRC-02).

Rules (ADR-001, ADR-014, ADR-027, ADR-031):
- Amounts are ``int`` Toman; ``float`` and ``bool`` are rejected.
- The sale price applies inside the half-open window ``[sale_start_at, sale_end_at)``.
- Computed components (a percentage code discount, tax) stay exact ``Fraction``s until
  each is rounded exactly once with the store's mode and step. Unit prices, fixed code
  amounts and shipping are already integers and are never rounded. ``grand_total`` is the
  sum of the components.
- Tax applies to taxable lines after the product discount and the line's share of the
  code discount; shipping is untaxed.
- Totals are split over lines with the largest-remainder method, ties going to the
  earlier line. Callers pass lines in a stable order (e.g. cart item creation order), so
  the same cart always gets the same split.

Consumers map a line to ``OrderItem`` as: ``unitPrice = unit.original``,
``discountAmount = product_discount + code_discount``, ``taxAmount = tax`` and
``finalLineTotal = total``.

No database access: callers pass the variant prices, the pricing settings and an already
validated discount code. Callers reject unpriced variants before pricing an order.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Final
from uuid import UUID

from app.shared.inventory import MAX_STOCK_QUANTITY
from app.shared.money import (
    MAX_PRICE_TOMAN,
    MAX_ROUNDING_STEP,
    MAX_TAX_RATE_BPS,
    RoundingMode,
    round_amount,
)

BPS: Final = 10_000
# Line keys are variant/cart-item ids or plain strings; the fingerprint needs a stable str.
LineKey = str | UUID
CURRENCY: Final = "TOMAN"
# Every output amount must fit the BIGINT snapshot columns.
MAX_AMOUNT: Final = 2**63 - 1


def _int(value: object, name: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int, never float or bool")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is out of range")
    return value


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be bool")
    return value


def _aware(moment: datetime | None, name: str) -> None:
    if moment is not None and moment.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class VariantPrice:
    base_price: int | None
    sale_price: int | None = None
    sale_start_at: datetime | None = None
    sale_end_at: datetime | None = None
    tax_enabled: bool = False
    price_version: int = 0


@dataclass(frozen=True, slots=True)
class UnitPrice:
    original: int
    final: int
    # original − final: the per-unit product discount.
    discount_amount: int
    # Display only, floored (PRD «جزئیات محصول»); never used to compute an amount.
    discount_percent: int
    on_sale: bool


def unit_price(price: VariantPrice, at: datetime) -> UnitPrice | None:
    """The price of one unit at ``at``; ``None`` when the variant has no price."""
    _aware(at, "at")
    _aware(price.sale_start_at, "sale_start_at")
    _aware(price.sale_end_at, "sale_end_at")
    _bool(price.tax_enabled, "tax_enabled")
    _int(price.price_version, "price_version")
    # An unpriced variant is not for sale; its sale fields are irrelevant (callers reject it).
    if price.base_price is None:
        return None
    base = _int(price.base_price, "base_price", minimum=1, maximum=MAX_PRICE_TOMAN)
    final = base
    if price.sale_price is not None:
        sale = _int(price.sale_price, "sale_price", minimum=1, maximum=base)
        start, end = price.sale_start_at, price.sale_end_at
        if start is not None and end is not None and start >= end:
            raise ValueError("sale_start_at must be before sale_end_at")
        if (start is None or start <= at) and (end is None or at < end):
            final = sale
    elif price.sale_start_at is not None or price.sale_end_at is not None:
        raise ValueError("a sale window needs sale_price")
    discount = base - final
    return UnitPrice(
        original=base,
        final=final,
        discount_amount=discount,
        discount_percent=discount * 100 // base,
        on_sale=discount > 0,
    )


@dataclass(frozen=True, slots=True)
class PricingPolicy:
    """The PricingSetting row, as plain values."""

    tax_enabled: bool = False
    tax_rate_bps: int = 0
    rounding_mode: RoundingMode = RoundingMode.NEAREST
    rounding_step: int = 1
    version: int = 1


def _check_policy(policy: PricingPolicy) -> None:
    _bool(policy.tax_enabled, "tax_enabled")
    _int(policy.tax_rate_bps, "tax_rate_bps", maximum=MAX_TAX_RATE_BPS)
    # round_amount compares modes by identity: a plain "up" string would act as NEAREST.
    if not isinstance(policy.rounding_mode, RoundingMode):
        raise TypeError("rounding_mode must be a RoundingMode")
    _int(policy.rounding_step, "rounding_step", minimum=1, maximum=MAX_ROUNDING_STEP)
    _int(policy.version, "version", minimum=1)


@dataclass(frozen=True, slots=True)
class CodeDiscount:
    """A discount code the caller has already validated (DSC); exactly one kind is set."""

    percent_bps: int | None = None
    fixed_amount: int | None = None
    max_amount: int | None = None
    # Keys of the lines the code applies to; None means every line.
    eligible_keys: frozenset[LineKey] | None = None


@dataclass(frozen=True, slots=True)
class LineInput:
    key: LineKey
    price: VariantPrice
    quantity: int


@dataclass(frozen=True, slots=True)
class LinePricing:
    key: LineKey
    quantity: int
    unit: UnitPrice
    # quantity × original unit price
    subtotal: int
    product_discount: int
    code_discount: int
    tax: int
    # subtotal − product_discount − code_discount + tax
    total: int


@dataclass(frozen=True, slots=True)
class OrderPricing:
    lines: tuple[LinePricing, ...]
    subtotal: int
    product_discount_total: int
    discount_code_amount: int
    # False when a code was given but no line was eligible: DSC/ORD answer 422 for it.
    code_applied: bool
    tax_amount: int
    shipping_amount: int
    grand_total: int
    currency: str
    calculated_at: datetime
    # Changes when any line's price (version, original, final, tax flag) or the settings
    # version changes, including a sale window starting or ending (PRICE_CHANGED).
    fingerprint: str


def allocate(total: int, weights: Sequence[int]) -> list[int]:
    """Split ``total`` proportionally to ``weights`` (largest remainder, ties by order)."""
    _int(total, "total")
    for weight in weights:
        _int(weight, "weight")
    weight_sum = sum(weights)
    if weight_sum == 0:
        if total:
            raise ValueError("cannot allocate a positive total over zero weights")
        return [0] * len(weights)
    shares = [total * weight // weight_sum for weight in weights]
    remainders = [total * weight % weight_sum for weight in weights]
    left = total - sum(shares)
    # Largest remainder first; equal remainders keep the line order (stable sort).
    for index in sorted(range(len(weights)), key=lambda i: -remainders[i])[:left]:
        shares[index] += 1
    return shares


def _code_amount(code: CodeDiscount, eligible_subtotal: int, policy: PricingPolicy) -> int:
    if (code.percent_bps is None) == (code.fixed_amount is None):
        raise ValueError("a discount code needs exactly one of percent_bps and fixed_amount")
    cap = eligible_subtotal
    if code.max_amount is not None:
        cap = min(cap, _int(code.max_amount, "max_amount"))
    if code.percent_bps is not None:
        percent = _int(code.percent_bps, "percent_bps", maximum=BPS)
        raw = Fraction(eligible_subtotal * percent, BPS)
        amount = round_amount(raw, policy.rounding_mode, policy.rounding_step)
    else:
        # A fixed amount is an integer the admin chose: it is never rounded.
        amount = _int(code.fixed_amount, "fixed_amount")
    # Applied after rounding, so rounding up never passes the cap or the eligible lines.
    return min(amount, cap)


def _fingerprint(
    lines: Sequence[LineInput], units: Sequence[UnitPrice], policy: PricingPolicy
) -> str:
    parts = sorted(
        [
            f"{type(line.key).__name__}:{line.key}",
            line.price.price_version,
            unit.original,
            unit.final,
            line.price.tax_enabled,
        ]
        for line, unit in zip(lines, units, strict=True)
    )
    canonical = json.dumps({"settings": policy.version, "lines": parts}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def price_order(
    lines: Sequence[LineInput],
    policy: PricingPolicy,
    *,
    at: datetime,
    code: CodeDiscount | None = None,
    shipping: int = 0,
) -> OrderPricing:
    """Price a cart or order; every amount and line split is computed here only.

    An empty ``lines`` prices to zeros plus ``shipping`` (an empty cart passes 0).
    """
    _check_policy(policy)
    _aware(at, "at")
    _int(shipping, "shipping", maximum=MAX_AMOUNT)
    keys = [line.key for line in lines]
    if any(not isinstance(key, str | UUID) for key in keys):
        raise TypeError("line keys must be str or UUID")
    if len(set(keys)) != len(keys):
        raise ValueError("line keys must be unique")

    units: list[UnitPrice] = []
    for line in lines:
        _int(line.quantity, "quantity", minimum=1, maximum=MAX_STOCK_QUANTITY)
        unit = unit_price(line.price, at)
        if unit is None:
            raise ValueError(f"line {line.key!s} has no price")
        units.append(unit)
    nets = [unit.final * line.quantity for unit, line in zip(units, lines, strict=True)]

    eligible = [
        net
        if code is not None and (code.eligible_keys is None or line.key in code.eligible_keys)
        else 0
        for net, line in zip(nets, lines, strict=True)
    ]
    eligible_subtotal = sum(eligible)
    code_applied = code is not None and eligible_subtotal > 0
    code_amount = _code_amount(code, eligible_subtotal, policy) if code is not None else 0
    code_shares = allocate(code_amount, eligible)

    tax_bases = [
        net - share if policy.tax_enabled and line.price.tax_enabled else 0
        for net, share, line in zip(nets, code_shares, lines, strict=True)
    ]
    raw_tax = Fraction(sum(tax_bases) * policy.tax_rate_bps, BPS)
    tax_amount = round_amount(raw_tax, policy.rounding_mode, policy.rounding_step)
    tax_shares = allocate(tax_amount, tax_bases)

    priced = tuple(
        LinePricing(
            key=line.key,
            quantity=line.quantity,
            unit=unit,
            subtotal=unit.original * line.quantity,
            product_discount=unit.discount_amount * line.quantity,
            code_discount=code_share,
            tax=tax_share,
            total=net - code_share + tax_share,
        )
        for line, unit, net, code_share, tax_share in zip(
            lines, units, nets, code_shares, tax_shares, strict=True
        )
    )
    subtotal = sum(line.subtotal for line in priced)
    product_discount_total = sum(line.product_discount for line in priced)
    grand_total = subtotal - product_discount_total - code_amount + tax_amount + shipping
    result = OrderPricing(
        lines=priced,
        subtotal=subtotal,
        product_discount_total=product_discount_total,
        discount_code_amount=code_amount,
        code_applied=code_applied,
        tax_amount=tax_amount,
        shipping_amount=shipping,
        grand_total=grand_total,
        currency=CURRENCY,
        calculated_at=at,
        fingerprint=_fingerprint(lines, units, policy),
    )
    _check(result)
    return result


def _check(result: OrderPricing) -> None:
    amounts = [
        result.subtotal,
        result.product_discount_total,
        result.discount_code_amount,
        result.tax_amount,
        result.shipping_amount,
        result.grand_total,
    ]
    for line in result.lines:
        amounts += [line.subtotal, line.product_discount, line.code_discount, line.tax, line.total]
    if min(amounts, default=0) < 0:
        raise ValueError("a priced amount is negative")
    if max(amounts, default=0) > MAX_AMOUNT:
        raise ValueError("a priced amount does not fit BIGINT")
