"""Cart API shapes (CART-02, ADR-040)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.inventory import MAX_STOCK_QUANTITY

# Server-owned or computed fields a client may echo back: dropped, never applied
# (CLAUDE.md §8: amounts come from the backend only).
SYSTEM_FIELDS: Final = frozenset(
    {
        "id",
        "cart_id",
        "product_id",
        "price",
        "unit_price",
        "final_price",
        "discount_amount",
        "tax_amount",
        "total",
        "line_total",
        "created_at",
        "updated_at",
    }
)

Quantity = Annotated[int, Field(strict=True, ge=1, le=MAX_STOCK_QUANTITY)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_system_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if key not in SYSTEM_FIELDS}
        return data


class AddCartItemRequest(_Body):
    variant_id: UUID
    quantity: Quantity


class UpdateCartItemRequest(_Body):
    quantity: Quantity


class CartItemResponse(BaseModel):
    id: UUID
    variant_id: UUID
    product_id: UUID
    quantity: int


class LinePrice(BaseModel):
    original: int
    final: int


class CartLineResponse(BaseModel):
    id: UUID
    variant_id: UUID
    product_id: UUID
    product_title: str
    product_slug: str
    sku: str
    options: dict[str, str]
    quantity: int
    # False when the variant is no longer public or for sale: the line is not priced.
    available: bool
    # ok, insufficient (more than is free) or out_of_stock; never a stock number (ADR-029).
    stock_status: str | None
    unit_price: LinePrice | None = None
    subtotal: int | None = None
    product_discount: int | None = None
    code_discount: int | None = None
    tax: int | None = None
    total: int | None = None
    # The final unit price differs from what the shopper last saw (ADR-041); UX only.
    price_changed: bool
    previous_unit_price: int | None


class CartResponse(BaseModel):
    items: list[CartLineResponse]
    subtotal: int
    product_discount_total: int
    discount_code_amount: int
    tax_amount: int
    # Chosen at checkout (POST /checkout/validate); always 0 here.
    shipping_amount: int
    grand_total: int
    currency: str
    calculated_at: datetime
    # Any line changed price, became unavailable or is short of stock.
    has_changes: bool
