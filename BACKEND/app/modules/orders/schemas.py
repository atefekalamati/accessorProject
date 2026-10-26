"""Order API shapes (ORD-04)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

Fingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class CreateOrderRequest(BaseModel):
    """Ids and the expected quote fingerprint only: every amount comes from the server."""

    model_config = ConfigDict(extra="forbid")

    address_id: UUID
    shipping_method_id: UUID
    # From POST /checkout/validate; a different current quote is 409 PRICE_CHANGED.
    fingerprint: Fingerprint


class OrderLineResponse(BaseModel):
    position: int
    product_id: UUID
    variant_id: UUID
    product_title: str
    sku: str
    variant_label: str
    quantity: int
    unit_price: int
    unit_final_price: int
    subtotal: int
    discount_amount: int
    tax_amount: int
    final_line_total: int


class OrderAddressResponse(BaseModel):
    recipient_name: str
    phone: str
    province: str
    city: str
    postal_code: str
    address_line: str
    plaque: str | None
    unit: str | None


class OrderShippingResponse(BaseModel):
    method_id: UUID
    title: str
    amount: int


class OrderDiscountResponse(BaseModel):
    code: str
    amount: int


class OrderResponse(BaseModel):
    id: UUID
    order_number: str
    status: str
    payment_status: str
    shipment_status: str
    subtotal: int
    product_discount_total: int
    discount_code_amount: int
    tax_amount: int
    shipping_amount: int
    grand_total: int
    currency: str
    items: list[OrderLineResponse]
    address: OrderAddressResponse
    shipping: OrderShippingResponse
    discount: OrderDiscountResponse | None
    # Pay before this moment; afterwards the order is cancelled (D34). A replayed response
    # keeps the original value: read GET /orders/{number} for the current state.
    reservation_expires_at: datetime
    created_at: datetime


class OrderStatusResponse(BaseModel):
    """The order's current statuses after a cancel (ORD-06); the full view is ACC-01."""

    id: UUID
    order_number: str
    status: str
    payment_status: str
    shipment_status: str
    cancel_reason: str | None
    updated_at: datetime


# --- the customer's own orders (ACC-01, PRD «سفارش‌ها» ✓) --------------------------------


class OrderSummaryResponse(BaseModel):
    id: UUID
    order_number: str
    status: str
    payment_status: str
    shipment_status: str
    grand_total: int
    currency: str
    item_count: int
    # The first line's product image as it is now (lines snapshot no image).
    image_url: str | None
    created_at: datetime


class OrderPaymentResponse(BaseModel):
    """One payment attempt; no gateway reference or raw gateway data."""

    id: UUID
    status: str
    amount: int
    created_at: datetime
    paid_at: datetime | None


class OrderHistoryResponse(BaseModel):
    """One status change; the actor is not shown to the customer."""

    field: str
    old_status: str | None
    new_status: str
    created_at: datetime


class OrderShipmentResponse(BaseModel):
    tracking_code: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None


class OrderDetailResponse(OrderResponse):
    """The placed order plus its payments, history and what the customer can do now.

    ``reservation_expires_at`` is the reservation's current end. A GET never writes, so an
    unpaid order past its deadline stays ``pending_payment`` (with ``can_pay`` and
    ``can_cancel`` false) until the expiry job cancels it (ADR-050).
    """

    cancel_reason: str | None
    payments: list[OrderPaymentResponse]
    history: list[OrderHistoryResponse]
    # Set once the order ships (ADM-02).
    shipment: OrderShipmentResponse | None
    payment_deadline: datetime | None
    can_pay: bool
    can_cancel: bool
