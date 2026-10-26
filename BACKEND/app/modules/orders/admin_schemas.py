"""Admin order and payment API shapes (ADM-01, PRD «مدیریت سفارش» ✓)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.db.models.orders import MAX_TRACKING_CODE_LENGTH
from app.modules.orders.schemas import OrderResponse, OrderShipmentResponse


class AdminOrderSummaryResponse(BaseModel):
    id: UUID
    order_number: str
    user_id: UUID
    # Masked in lists (D38); the detail shows it in full.
    phone: str
    status: str
    payment_status: str
    shipment_status: str
    grand_total: int
    currency: str
    item_count: int
    created_at: datetime


class AdminPaymentResponse(BaseModel):
    """A payment for the panel: no raw gateway event (it stays in the database)."""

    id: UUID
    order_id: UUID
    order_number: str
    gateway: str
    gateway_reference: str | None
    amount: int
    paid_amount: int | None
    status: str
    failure_reason: str | None
    created_at: datetime
    paid_at: datetime | None
    verified_at: datetime | None


class AdminHistoryResponse(BaseModel):
    field: str
    old_status: str | None
    new_status: str
    # Null for the system (expiry job, gateway callback).
    actor_user_id: UUID | None
    reason: str | None
    created_at: datetime


class AdminOrderDetailResponse(OrderResponse):
    user_id: UUID
    phone: str
    cancel_reason: str | None
    updated_at: datetime
    payments: list[AdminPaymentResponse]
    history: list[AdminHistoryResponse]
    shipment: OrderShipmentResponse | None


TrackingCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_TRACKING_CODE_LENGTH,
        # Printable only: no control characters (a NUL would fail in PostgreSQL).
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]


class UpdateShipmentRequest(BaseModel):
    """The next shipment status; ``shipped`` needs the carrier tracking code (ADM-02)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["preparing", "shipped", "delivered"]
    tracking_code: TrackingCode | None = None

    @model_validator(mode="after")
    def check_tracking_code(self) -> Self:
        if (self.status == "shipped") != (self.tracking_code is not None):
            raise ValueError("tracking_code is required for, and only for, shipped")
        return self
