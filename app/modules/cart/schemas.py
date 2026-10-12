"""Cart API shapes (CART-02, ADR-040)."""

from __future__ import annotations

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
