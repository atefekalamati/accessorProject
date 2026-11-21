"""Staff return request API shapes (ORD-09, PRD «مرجوعی» ✓)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

from app.db.models import ItemCondition
from app.db.models.returns import MAX_RETURN_ADMIN_NOTE_LENGTH, MAX_RETURN_NOTE_LENGTH
from app.modules.returns.schemas import MAX_RETURN_LINES
from app.shared.inventory import MAX_STOCK_QUANTITY

_MULTILINE: Final = r"^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+$"

AdminNote = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_RETURN_ADMIN_NOTE_LENGTH,
        pattern=_MULTILINE,
    ),
]
RejectReason = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_RETURN_NOTE_LENGTH, pattern=_MULTILINE
    ),
]
AcceptedQuantity = Annotated[int, Field(strict=True, ge=0, le=MAX_STOCK_QUANTITY)]


class ReturnNoteRequest(BaseModel):
    """Approve or receive: an optional internal note."""

    model_config = ConfigDict(extra="forbid")

    admin_note: AdminNote | None = None


class RejectReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Shown to the customer.
    reject_reason: RejectReason
    admin_note: AdminNote | None = None


class InspectLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_item_id: UUID
    condition: ItemCondition
    accepted_quantity: AcceptedQuantity
    # ``sellable`` lines are always refundable; ``damaged`` lines say so explicitly.
    refundable: StrictBool | None = None
    note: AdminNote | None = None

    @model_validator(mode="after")
    def _refundable(self) -> InspectLineRequest:
        if self.condition is ItemCondition.SELLABLE:
            if self.refundable is False:
                raise ValueError("a sellable line is always refundable")
            self.refundable = True
        elif self.refundable is None:
            raise ValueError("say whether a damaged line is refundable")
        return self


class InspectReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[InspectLineRequest] = Field(min_length=1, max_length=MAX_RETURN_LINES)
    admin_note: AdminNote | None = None

    @model_validator(mode="after")
    def _unique_lines(self) -> InspectReturnRequest:
        ids = [line.order_item_id for line in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("each order item may appear only once")
        return self


class AdminReturnItemResponse(BaseModel):
    order_item_id: UUID
    product_id: UUID
    variant_id: UUID
    product_title: str
    sku: str
    variant_label: str
    quantity: int
    accepted_quantity: int | None
    condition: str | None
    refundable: bool | None
    refund_amount: int | None
    inspection_note: str | None
    inventory_movement_id: UUID | None


class AdminReturnHistoryResponse(BaseModel):
    old_status: str | None
    new_status: str
    actor_user_id: UUID | None
    created_at: datetime


class AdminReturnResponse(BaseModel):
    id: UUID
    order_id: UUID
    order_number: str
    user_id: UUID
    status: str
    reason: str
    note: str | None
    reject_reason: str | None
    admin_note: str | None
    decided_by: UUID | None
    decided_at: datetime | None
    received_at: datetime | None
    inspected_at: datetime | None
    refund_amount: int | None
    refund_reference: str | None
    refunded_at: datetime | None
    refunded_by: UUID | None
    items: list[AdminReturnItemResponse]
    history: list[AdminReturnHistoryResponse]
    created_at: datetime
    updated_at: datetime


class AdminReturnSummaryResponse(BaseModel):
    id: UUID
    order_number: str
    status: str
    reason: str
    item_count: int
    refund_amount: int | None
    created_at: datetime
    updated_at: datetime
