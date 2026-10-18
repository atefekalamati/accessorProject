"""Shipping cost behind an interface (ADDR-02, D33, D34, ADR-045).

Pure: no database. v1 has one implementation, a flat cost per method that becomes free
when the basis reaches the method's threshold. Regional pricing (D33, later) only needs a
new calculator; ``ShippingContext`` already carries the address fields it will use.

How ORD-03/ORD-04 price an order with shipping (exact, no circularity: the code discount
and tax never read the shipping amount):
1. price the lines with the code and ``shipping=0``;
2. ``basis = shipping_basis(that pricing)``;
3. ``amount = calculator.quote(rates, ShippingContext(basis=basis, ...))``;
4. price again (or add) with ``shipping=amount``: lines, tax and code are unchanged and
   ``grand_total`` grows by exactly ``amount``. Shipping is never rounded or taxed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.db.models import ShippingMethod
from app.modules.pricing.calculator import OrderPricing
from app.shared.money import MAX_PRICE_TOMAN


def _int(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int, never float or bool")
    if not minimum <= value <= MAX_PRICE_TOMAN:
        raise ValueError(f"{name} is out of range")
    return value


@dataclass(frozen=True, slots=True)
class ShippingRates:
    cost: int
    free_shipping_threshold: int | None = None

    def __post_init__(self) -> None:
        _int(self.cost, "cost", minimum=0)
        if self.free_shipping_threshold is not None:
            _int(self.free_shipping_threshold, "free_shipping_threshold", minimum=1)


@dataclass(frozen=True, slots=True)
class ShippingContext:
    # The total the free-shipping threshold is compared with (see shipping_basis).
    basis: int
    # For regional pricing later (D33); unused by the flat calculator.
    province: str | None = None
    city: str | None = None

    def __post_init__(self) -> None:
        _int(self.basis, "basis", minimum=0)


class ShippingCalculator(Protocol):
    def quote(self, rates: ShippingRates, context: ShippingContext) -> int: ...


class FlatRateCalculator:
    """The method's cost, or 0 once the basis reaches the threshold (>=, «برسد»)."""

    def quote(self, rates: ShippingRates, context: ShippingContext) -> int:
        threshold = rates.free_shipping_threshold
        if threshold is not None and context.basis >= threshold:
            return 0
        return rates.cost


def rates_of(method: ShippingMethod) -> ShippingRates:
    return ShippingRates(cost=method.cost, free_shipping_threshold=method.free_shipping_threshold)


def shipping_basis(pricing: OrderPricing) -> int:
    """The free-shipping basis (D34): the priced lines after every discount (product and an
    applied code), before tax and without shipping. Not the code's minimum-order basis,
    which is before the code (ADR-043)."""
    return pricing.subtotal - pricing.product_discount_total - pricing.discount_code_amount


def get_shipping_calculator() -> ShippingCalculator:
    return FlatRateCalculator()
