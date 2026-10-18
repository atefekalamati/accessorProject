"""POST /orders: place an order from the user's cart (ORD-04, ADR-048).

One transaction, locks in the global order (ADR-048): idempotency key → cart row →
discount code row → order advisory → (order row) → variants / inventory → redemption.
The code is locked before the order row is inserted: the ``orders.discount_code_id`` FK
takes KEY SHARE on the code row, which a later FOR UPDATE would deadlock against. A new
order's row is inserted (and flushed) before ``reserve`` takes the order advisory lock;
that is safe only because the row is invisible to others until commit. Paths on an
existing order (PAY-03, cancel, expiry) take the advisory lock, then the order row.

At most one live pending order per user (``pending_payment`` with an unexpired
reservation): the cart lock serializes a user's order requests, so the check cannot race.
The cart is not emptied (D34). Only a successful order is stored for replay (ADR-046).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError, ConflictError, ErrorCode, UnauthorizedError
from app.core.phone import MOBILE_E164_PATTERN
from app.core.time import utc_now
from app.db.models import (
    InventoryReservation,
    Order,
    OrderAddress,
    OrderItem,
    OrderPriceSnapshot,
    OrderStatus,
    OrderStatusHistory,
    PaymentStatus,
    ReservationStatus,
    ShipmentStatus,
    StatusField,
    User,
)
from app.db.models.orders import format_order_number, order_number_seq
from app.modules.cart.repository import CartRepository
from app.modules.checkout.service import CheckoutService, Quote, render
from app.modules.discounts.redemption import RedemptionService
from app.modules.inventory.reservation import ReservationService, ReserveLine
from app.modules.orders.schemas import CreateOrderRequest, OrderResponse
from app.shared.audit import record_audit
from app.shared.idempotency import (
    NO_STORE,
    IdempotencyService,
    StoredResponse,
    request_hash,
)

SCOPE: Final = "orders.create"
MAX_VARIANT_LABEL: Final = 300


@dataclass(frozen=True, slots=True)
class PlacedOrder:
    status_code: int
    body: dict[str, Any]
    replayed: bool


def _cart_empty() -> BusinessRuleError:
    return BusinessRuleError(
        message="The cart is empty", details=[{"field": "cart", "type": "cart_empty"}]
    )


def variant_label(options: dict[str, str]) -> str:
    """``color: Red / size: M`` in key order; empty without options."""
    label = " / ".join(f"{key}: {value}" for key, value in sorted(options.items()))
    return label[:MAX_VARIANT_LABEL]


class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def place(
        self,
        user_id: UUID,
        key: str,
        payload: CreateOrderRequest,
        request: Request | None = None,
        now: datetime | None = None,
    ) -> PlacedOrder:
        hash_ = request_hash(body=payload.model_dump(mode="json"))
        async with self._session.begin():
            idempotency = IdempotencyService(self._session)
            stored = await idempotency.begin(
                user_id=user_id, scope=SCOPE, key=key, request_hash=hash_
            )
            if stored is not None:
                return _replay(stored)
            phone = await self._verified_phone(user_id)
            cart = await CartRepository(self._session).find_user_cart(user_id, lock=True)
            if cart is None:
                raise _cart_empty()
            locked_code = None
            if cart.discount_code_id is not None:
                locked_code = await RedemptionService(self._session).lock_code(
                    cart.discount_code_id
                )
            # After the locks, so a wait never shortens the reservation (as in INV-05).
            now = now or utc_now()
            await self._refuse_live_pending(user_id, now)
            quote = await CheckoutService(self._session).build_quote(
                user_id,
                payload.address_id,
                payload.shipping_method_id,
                now=now,
                locked_code=locked_code,
                check_stock=False,
            )
            if quote.fingerprint != payload.fingerprint:
                raise ConflictError(
                    code=ErrorCode.PRICE_CHANGED,
                    message="The order total changed since the quote; review it and retry",
                    details=[
                        {"type": "price_changed", "quote": render(quote).model_dump(mode="json")}
                    ],
                    headers=dict(NO_STORE),
                )
            order = await self._insert_order(user_id, phone, quote, now)
            reservation = await ReservationService(self._session).reserve(
                order_id=order.id,
                lines=[ReserveLine(row.variant.id, row.item.quantity) for row in quote.rows],
                user_id=user_id,
                cart_id=cart.id,
                now=now,
            )
            if quote.code is not None and quote.priced_rules is not None:
                pricing = quote.pricing
                await RedemptionService(self._session).redeem(
                    code_id=quote.code.id,
                    priced_rules=quote.priced_rules,
                    order_id=order.id,
                    user_id=user_id,
                    phone=phone,
                    amount=pricing.discount_code_amount,
                    subtotal=pricing.subtotal - pricing.product_discount_total,
                    now=now,
                )
            items = self._insert_snapshot(order, quote)
            _assert_totals(order, items)
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=user_id,
                action="order.created",
                entity_type="order",
                entity_id=order.id,
                before=None,
                after={
                    "order_number": order.order_number,
                    "grand_total": order.grand_total,
                    "lines": len(items),
                },
                request=request,
            )
            body = _response(order, quote, items, reservation.expires_at).model_dump(mode="json")
            await idempotency.complete(
                user_id=user_id,
                scope=SCOPE,
                key=key,
                request_hash=hash_,
                status_code=201,
                body=body,
            )
        return PlacedOrder(status_code=201, body=body, replayed=False)

    async def _verified_phone(self, user_id: UUID) -> str:
        """Sign-in is by OTP only, so the account's mobile is verified; never trust less."""
        phone = await self._session.scalar(select(User.phone).where(User.id == user_id))
        if phone is None or not re.fullmatch(MOBILE_E164_PATTERN, phone):
            raise UnauthorizedError(
                code=ErrorCode.MOBILE_NOT_VERIFIED, message="A verified mobile is required"
            )
        return phone

    async def _refuse_live_pending(self, user_id: UUID, now: datetime) -> None:
        """409 ORDER_PENDING while the user has an unpaid order with live stock held."""
        live = await self._session.scalar(
            select(Order.order_number)
            .join(InventoryReservation, InventoryReservation.order_id == Order.id)
            .where(
                Order.user_id == user_id,
                Order.status == OrderStatus.PENDING_PAYMENT,
                InventoryReservation.status == ReservationStatus.ACTIVE,
                InventoryReservation.expires_at > now,
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        if live is not None:
            raise ConflictError(
                code=ErrorCode.ORDER_PENDING,
                message="You already have an order waiting for payment",
                details=[{"type": "order_pending", "order_number": live}],
            )

    async def _insert_order(self, user_id: UUID, phone: str, quote: Quote, now: datetime) -> Order:
        number = int(await self._session.scalar(order_number_seq.next_value()) or 0)
        pricing = quote.pricing
        order = Order(
            id=uuid4(),
            order_number=format_order_number(now.year, number),
            user_id=user_id,
            phone=phone,
            status=OrderStatus.PENDING_PAYMENT,
            payment_status=PaymentStatus.UNPAID,
            shipment_status=ShipmentStatus.NOT_SHIPPED,
            subtotal=pricing.subtotal,
            product_discount_total=pricing.product_discount_total,
            discount_code_amount=pricing.discount_code_amount,
            tax_amount=pricing.tax_amount,
            shipping_amount=pricing.shipping_amount,
            grand_total=pricing.grand_total,
            currency=pricing.currency,
            discount_code_id=None if quote.code is None else quote.code.id,
            discount_code=None if quote.code is None else quote.code.code,
            shipping_method_id=quote.method.id,
            shipping_method_title=quote.method.title,
            created_at=now,
            updated_at=now,
        )
        self._session.add(order)
        # Reservations and redemptions reference the order.
        await self._session.flush()
        return order

    def _insert_snapshot(self, order: Order, quote: Quote) -> list[OrderItem]:
        rows = {row.item.id: row for row in quote.rows}
        items: list[OrderItem] = []
        for position, line in enumerate(quote.pricing.lines):
            row = rows[UUID(str(line.key))]
            items.append(
                OrderItem(
                    order_id=order.id,
                    position=position,
                    product_id=row.product.id,
                    variant_id=row.variant.id,
                    product_title=row.product.title,
                    sku=row.variant.sku,
                    variant_label=variant_label(quote.options[row.variant.id]),
                    quantity=line.quantity,
                    unit_price=line.unit.original,
                    unit_final_price=line.unit.final,
                    subtotal=line.subtotal,
                    product_discount=line.product_discount,
                    code_discount=line.code_discount,
                    discount_amount=line.product_discount + line.code_discount,
                    tax_amount=line.tax,
                    final_line_total=line.total,
                )
            )
        policy, address = quote.policy, quote.address
        self._session.add_all(items)
        self._session.add_all(
            [
                OrderPriceSnapshot(
                    order_id=order.id,
                    pricing_version=policy.version,
                    tax_enabled=policy.tax_enabled,
                    tax_rate_bps=policy.tax_rate_bps,
                    rounding_mode=policy.rounding_mode,
                    rounding_step=policy.rounding_step,
                    fingerprint=quote.fingerprint,
                    calculated_at=quote.calculated_at,
                    shipping_method_cost=quote.rates.cost,
                    shipping_free_threshold=quote.rates.free_shipping_threshold,
                ),
                OrderAddress(
                    order_id=order.id,
                    source_address_id=address.id,
                    recipient_name=address.recipient_name,
                    phone=address.phone,
                    province=address.province,
                    city=address.city,
                    postal_code=address.postal_code,
                    address_line=address.address_line,
                    plaque=address.plaque,
                    unit=address.unit,
                ),
                *(
                    OrderStatusHistory(order_id=order.id, field=field, new_status=status)
                    for field, status in (
                        (StatusField.ORDER, order.status),
                        (StatusField.PAYMENT, order.payment_status),
                        (StatusField.SHIPMENT, order.shipment_status),
                    )
                ),
            ]
        )
        return items


def _assert_totals(order: Order, items: list[OrderItem]) -> None:
    """The header equals the sum of its lines; a CHECK cannot span rows (ADR-046)."""
    sums = (
        sum(item.subtotal for item in items),
        sum(item.product_discount for item in items),
        sum(item.code_discount for item in items),
        sum(item.tax_amount for item in items),
    )
    header = (
        order.subtotal,
        order.product_discount_total,
        order.discount_code_amount,
        order.tax_amount,
    )
    if sums != header:
        raise RuntimeError("order header totals differ from the sum of its lines")


def _replay(stored: StoredResponse) -> PlacedOrder:
    body = stored.body if isinstance(stored.body, dict) else {}
    return PlacedOrder(status_code=stored.status_code, body=body, replayed=True)


def _response(
    order: Order, quote: Quote, items: list[OrderItem], expires_at: datetime
) -> OrderResponse:
    address = quote.address
    return OrderResponse.model_validate(
        {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "payment_status": order.payment_status,
            "shipment_status": order.shipment_status,
            "subtotal": order.subtotal,
            "product_discount_total": order.product_discount_total,
            "discount_code_amount": order.discount_code_amount,
            "tax_amount": order.tax_amount,
            "shipping_amount": order.shipping_amount,
            "grand_total": order.grand_total,
            "currency": order.currency,
            "items": [
                {
                    "position": item.position,
                    "product_id": item.product_id,
                    "variant_id": item.variant_id,
                    "product_title": item.product_title,
                    "sku": item.sku,
                    "variant_label": item.variant_label,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "unit_final_price": item.unit_final_price,
                    "subtotal": item.subtotal,
                    "discount_amount": item.discount_amount,
                    "tax_amount": item.tax_amount,
                    "final_line_total": item.final_line_total,
                }
                for item in items
            ],
            "address": {
                "recipient_name": address.recipient_name,
                "phone": address.phone,
                "province": address.province,
                "city": address.city,
                "postal_code": address.postal_code,
                "address_line": address.address_line,
                "plaque": address.plaque,
                "unit": address.unit,
            },
            "shipping": {
                "method_id": order.shipping_method_id,
                "title": order.shipping_method_title,
                "amount": order.shipping_amount,
            },
            "discount": None
            if order.discount_code is None
            else {"code": order.discount_code, "amount": order.discount_code_amount},
            "reservation_expires_at": expires_at,
            "created_at": order.created_at,
        }
    )
