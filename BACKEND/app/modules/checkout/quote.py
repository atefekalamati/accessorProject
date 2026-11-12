"""The checkout quote fingerprint (ORD-03, D34, ADR-047).

Pure. ``POST /orders`` (ORD-04) recomputes the quote and compares fingerprints: any change
to what the order would cost gives a new one, so the shopper confirms it. Display-only
snapshot fields (product title, SKU, address text) are not covered: the order copies them
as they are when it is placed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.modules.discounts.rules import CodeRules
from app.modules.pricing.calculator import OrderPricing
from app.modules.shipping.calculator import ShippingRates


@dataclass(frozen=True, slots=True)
class QuotedCode:
    id: UUID
    rules: CodeRules


@dataclass(frozen=True, slots=True)
class QuotedShipping:
    method_id: UUID
    rates: ShippingRates


def quote_fingerprint(
    pricing: OrderPricing,
    code: QuotedCode | None,
    shipping: QuotedShipping,
    quantities: Sequence[tuple[str, int]],
) -> str:
    """SHA-256 over the calculator fingerprint (prices, tax flags, settings version) plus
    what it leaves out: each line's quantity, the total, the code and its rules, and the
    shipping method with its cost, threshold and amount.

    The method's cost and threshold are covered even when shipping is free, because the
    order snapshots them (ADR-046).
    """
    canonical = json.dumps(
        {
            "pricing": pricing.fingerprint,
            "quantities": sorted([str(key), quantity] for key, quantity in quantities),
            "grand_total": pricing.grand_total,
            "code": None
            if code is None
            else {
                "id": str(code.id),
                "type": code.rules.type.value,
                "value": code.rules.value,
                "max_amount": code.rules.max_amount,
                "amount": pricing.discount_code_amount,
            },
            "shipping": {
                "method_id": str(shipping.method_id),
                "cost": shipping.rates.cost,
                "free_shipping_threshold": shipping.rates.free_shipping_threshold,
                "amount": pricing.shipping_amount,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
