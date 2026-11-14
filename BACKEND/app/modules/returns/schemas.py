"""Return request API shapes for the customer (ORD-08, PRD «مرجوعی» ✓).

Amounts, statuses and inspection results are never accepted from the client; the
responses show no actor, internal note, refund reference or inspection detail.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.db.models import ReturnReason
from app.db.models.returns import MAX_RETURN_NOTE_LENGTH
from app.shared.inventory import MAX_STOCK_QUANTITY

MAX_RETURN_LINES: Final = 50
# Multi-line plain text: no control characters except tab, newline and carriage return.
_MULTILINE: Final = r"^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+$"

ReturnNote = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_RETURN_NOTE_LENGTH, pattern=_MULTILINE
    ),
]
Quantity = Annotated[int, Field(strict=True, ge=1, le=MAX_STOCK_QUANTITY)]


class ReturnLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_item_id: UUID
    quantity: Quantity


class CreateReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReturnLineRequest] = Field(min_length=1, max_length=MAX_RETURN_LINES)
    reason: ReturnReason
    note: ReturnNote | None = None

    @model_validator(mode="after")
    def _unique_lines(self) -> CreateReturnRequest:
        ids = [line.order_item_id for line in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("each order item may appear only once")
        return self

    def canonical(self) -> dict[str, object]:
        """The body for the Idempotency-Key hash: line order does not matter."""
        body = self.model_dump(mode="json")
        body["items"] = sorted(body["items"], key=lambda line: line["order_item_id"])
        return body


class ReturnItemResponse(BaseModel):
    order_item_id: UUID
    product_title: str
    variant_label: str
    quantity: int
    # Set after inspection (ORD-09).
    accepted_quantity: int | None
    refund_amount: int | None


class ReturnHistoryResponse(BaseModel):
    status: str
    created_at: datetime


class ReturnResponse(BaseModel):
    id: UUID
    order_number: str
    status: str
    reason: str
    note: str | None
    # Only for a rejected request: the staff's reason, written for the customer.
    reject_reason: str | None
    items: list[ReturnItemResponse]
    refund_amount: int | None
    refunded_at: datetime | None
    history: list[ReturnHistoryResponse]
    created_at: datetime
    updated_at: datetime


class ReturnSummaryResponse(BaseModel):
    id: UUID
    order_number: str
    status: str
    reason: str
    item_count: int
    refund_amount: int | None
    created_at: datetime


class ReturnableItemResponse(BaseModel):
    order_item_id: UUID
    position: int
    returnable_quantity: int
