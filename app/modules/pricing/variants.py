"""The calculator's view of a stored variant price (PRC-02; used by catalog and cart)."""

from __future__ import annotations

from app.db.models import ProductVariant
from app.modules.pricing.calculator import VariantPrice


def variant_price(variant: ProductVariant) -> VariantPrice:
    return VariantPrice(
        base_price=variant.base_price,
        sale_price=variant.sale_price,
        sale_start_at=variant.sale_start_at,
        sale_end_at=variant.sale_end_at,
        tax_enabled=variant.tax_enabled,
        price_version=variant.price_version,
    )
