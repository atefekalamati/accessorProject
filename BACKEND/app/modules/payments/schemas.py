"""Payment API shapes (PAY-02, PAY-03)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InitPaymentRequest(BaseModel):
    """Only the order: the amount always comes from the order's stored grand_total."""

    model_config = ConfigDict(extra="forbid")

    order_id: UUID


class PaymentInitResponse(BaseModel):
    payment_id: UUID
    order_id: UUID
    order_number: str
    # Toman; the order's grand_total.
    amount: int
    currency: str
    redirect_url: str
    # The gateway stops accepting the customer here; a later init starts a new payment.
    gateway_expires_at: datetime
    reservation_expires_at: datetime


class FakeCompleteRequest(BaseModel):
    """The customer's action on the fake gateway's page (development only)."""

    model_config = ConfigDict(extra="forbid")

    result: Literal["paid", "failed"]
    # Defaults to the requested amount; another value simulates a wrong amount.
    amount_rial: int | None = Field(default=None, ge=0)


class FakeSessionResponse(BaseModel):
    reference: str
    status: str


class CallbackResponse(BaseModel):
    """The acknowledgement; always 200 once processed (ADR-051).

    The endpoint is public and the reference sits in the browser history, so only the
    outcome is returned. The order itself is read with a token (ADR-061, SEC-08).
    """

    outcome: Literal["success", "failed", "pending"]
