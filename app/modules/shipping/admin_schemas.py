"""Admin shipping method API shapes (ADDR-03, ADR-045).

Server-owned fields a client echoes back are dropped, never applied; any other unknown
field is 400.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

from app.shared.money import MAX_PRICE_TOMAN

SYSTEM_FIELDS: Final = frozenset({"id", "created_at", "updated_at", "deleted_at"})
EDITABLE_FIELDS: Final = (
    "title",
    "description",
    "cost",
    "free_shipping_threshold",
    "is_active",
    "display_order",
)
# Fields that may be cleared with null (no description, never free).
NULLABLE_FIELDS: Final = frozenset({"description", "free_shipping_threshold"})
MAX_DISPLAY_ORDER: Final = 1_000_000

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
# Toman; 0 means always free.
Cost = Annotated[int, Field(strict=True, ge=0, le=MAX_PRICE_TOMAN)]
Threshold = Annotated[int, Field(strict=True, ge=1, le=MAX_PRICE_TOMAN)]
DisplayOrder = Annotated[int, Field(strict=True, ge=0, le=MAX_DISPLAY_ORDER)]


def _drop_system_fields(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: value for key, value in data.items() if key not in SYSTEM_FIELDS}
    return data


class CreateShippingMethodRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    description: Description | None = None
    cost: Cost
    # Free from this total after discounts, before tax (D34); null means never free.
    free_shipping_threshold: Threshold | None = None
    is_active: StrictBool = True
    display_order: DisplayOrder = 0

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return _drop_system_fields(data)


class UpdateShippingMethodRequest(BaseModel):
    """Sent fields change; null clears only the nullable ones."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: Description | None = None
    cost: Cost | None = None
    free_shipping_threshold: Threshold | None = None
    is_active: StrictBool | None = None
    display_order: DisplayOrder | None = None

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return _drop_system_fields(data)

    @model_validator(mode="after")
    def _fields(self) -> UpdateShippingMethodRequest:
        sent = self.model_fields_set
        if not sent:
            raise ValueError("at least one field is required")
        nulls = sorted(name for name in sent - NULLABLE_FIELDS if getattr(self, name) is None)
        if nulls:
            raise ValueError(f"must not be null: {', '.join(nulls)}")
        return self


class AdminShippingMethodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    cost: int
    free_shipping_threshold: int | None
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime
