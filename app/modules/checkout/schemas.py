"""Checkout API shapes (ORD-03)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.cart.schemas import LinePrice


class CheckoutRequest(BaseModel):
    """Only ids: every amount comes from the server (CLAUDE.md §8)."""

    model_config = ConfigDict(extra="forbid")

    address_id: UUID
    shipping_method_id: UUID


class QuoteLine(BaseModel):
    id: UUID
    variant_id: UUID
    product_id: UUID
    product_title: str
    sku: str
    options: dict[str, str]
    quantity: int
    unit_price: LinePrice
    subtotal: int
    product_discount: int
    code_discount: int
    tax: int
    total: int


class QuoteDiscount(BaseModel):
    code: str
    amount: int


class QuoteShipping(BaseModel):
    method_id: UUID
    title: str
    # The method's cost; amount is 0 once the free-shipping threshold is reached.
    cost: int
    free_shipping_threshold: int | None
    amount: int


class CheckoutQuoteResponse(BaseModel):
    items: list[QuoteLine]
    subtotal: int
    product_discount_total: int
    discount_code_amount: int
    tax_amount: int
    shipping_amount: int
    grand_total: int
    currency: str
    calculated_at: datetime
    discount: QuoteDiscount | None
    shipping: QuoteShipping
    address_id: UUID
    # Send back unchanged to POST /orders; any change since this quote is 409 PRICE_CHANGED.
    fingerprint: str
