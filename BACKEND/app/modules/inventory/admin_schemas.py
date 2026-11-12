"""Admin inventory API shapes (INV-08, ADR-038)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.db.models.inventory import MAX_MOVEMENT_REASON_LENGTH
from app.modules.inventory.service import AdjustmentType
from app.modules.inventory.stock import StockStatus
from app.shared.inventory import MAX_STOCK_QUANTITY

# Server-owned fields a client may echo back from the list row: dropped, never applied
# (CLAUDE.md §8; same rule as ADR-030). Stock changes only through an adjustment.
SYSTEM_FIELDS: Final = frozenset(
    {
        "id",
        "variant_id",
        "product_id",
        "product_title",
        "sku",
        "warehouse_id",
        "total",
        "reserved",
        "free",
        "total_quantity",
        "reserved_quantity",
        "stock",
        "stock_status",
        "created_at",
        "updated_at",
    }
)

Quantity = Annotated[int, Field(strict=True, ge=0, le=MAX_STOCK_QUANTITY)]
Reason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MOVEMENT_REASON_LENGTH),
]


class UpdateInventoryRequest(BaseModel):
    """A stock adjustment, a new low-stock threshold, or both, with one reason.

    ``expected_total`` guards against a repeated submit: the change applies only while the
    stored total still equals it (409 otherwise).
    """

    model_config = ConfigDict(extra="forbid")

    adjustment_type: AdjustmentType | None = None
    quantity: Quantity | None = None
    low_stock_threshold: Quantity | None = None
    expected_total: Quantity | None = None
    reason: Reason

    @model_validator(mode="before")
    @classmethod
    def _drop_system_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if key not in SYSTEM_FIELDS}
        return data

    @model_validator(mode="after")
    def _check_body(self) -> UpdateInventoryRequest:
        if (self.adjustment_type is None) != (self.quantity is None):
            raise ValueError("adjustment_type and quantity are sent together")
        if self.adjustment_type is None and self.low_stock_threshold is None:
            raise ValueError("an adjustment or low_stock_threshold is required")
        if (
            self.adjustment_type is not None
            and self.adjustment_type is not AdjustmentType.CORRECTION
            and self.quantity == 0
        ):
            raise ValueError("quantity must be at least 1 for increase and decrease")
        return self


class InventoryRow(BaseModel):
    """One variant's stock across active warehouses; ``reserved`` excludes expired holds."""

    variant_id: UUID
    product_id: UUID
    product_title: str
    sku: str
    total: int
    reserved: int
    free: int
    low_stock_threshold: int
    stock_status: StockStatus
    # None while the variant has no InventoryItem.
    updated_at: datetime | None


class ReservationItemRow(BaseModel):
    variant_id: UUID
    sku: str
    quantity: int
    status: str


class ReservationRow(BaseModel):
    id: UUID
    order_id: UUID | None
    user_id: UUID | None
    # ``expired`` also for an active reservation past expires_at the job has not swept.
    status: str
    expires_at: datetime
    created_at: datetime
    committed_at: datetime | None
    released_at: datetime | None
    items: list[ReservationItemRow]


class MovementRow(BaseModel):
    id: UUID
    inventory_item_id: UUID
    movement_type: str
    quantity: int
    total_before: int
    total_after: int
    reserved_before: int
    reserved_after: int
    reference_type: str | None
    reference_id: UUID | None
    reason: str | None
    created_by: UUID | None
    created_at: datetime
