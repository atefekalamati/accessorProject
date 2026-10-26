"""Admin order and payment lists and order detail (ADM-01, PRD «مدیریت سفارش» ✓)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import UnaryExpression

from app.core.errors import NotFoundError
from app.core.redaction import mask_phone
from app.core.time import utc_now
from app.db.models import (
    InventoryReservation,
    Order,
    OrderAddress,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    Payment,
    Shipment,
    ShipmentStatus,
    StatusField,
)
from app.modules.auth.service import CurrentUser
from app.modules.orders.admin_schemas import (
    AdminHistoryResponse,
    AdminOrderDetailResponse,
    AdminOrderSummaryResponse,
    AdminPaymentResponse,
    UpdateShipmentRequest,
)
from app.modules.orders.cancel import lock_order, order_advisory_lock
from app.modules.orders.service import order_fields
from app.modules.orders.shipments import shipment_of
from app.modules.orders.state_service import OrderStateService
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams, escape_like, paginate
from app.shared.search import TimeRange


@dataclass(frozen=True, slots=True)
class OrderFilters:
    status: str | None = None
    payment_status: str | None = None
    shipment_status: str | None = None
    # An order number prefix (``ORD-…``) or digits inside the mobile; one of the two.
    number_prefix: str | None = None
    mobile_digits: str | None = None
    created: TimeRange = TimeRange()


@dataclass(frozen=True, slots=True)
class PaymentFilters:
    status: str | None = None
    failure_reason: str | None = None
    created: TimeRange = TimeRange()


def _in_range(column: Any, created: TimeRange) -> list[ColumnElement[bool]]:
    criteria: list[ColumnElement[bool]] = []
    if created.start is not None:
        criteria.append(column >= created.start)
    if created.end is not None:
        criteria.append(column < created.end)
    return criteria


def _payment(payment: Payment, order_number: str) -> AdminPaymentResponse:
    return AdminPaymentResponse(
        id=payment.id,
        order_id=payment.order_id,
        order_number=order_number,
        gateway=payment.gateway,
        gateway_reference=payment.gateway_reference,
        amount=payment.amount,
        paid_amount=payment.paid_amount,
        status=payment.status,
        failure_reason=payment.failure_reason,
        created_at=payment.created_at,
        paid_at=payment.paid_at,
        verified_at=payment.verified_at,
    )


# The only step into each status (ADR-047); the transition above already checked it.
_PREVIOUS: dict[ShipmentStatus, ShipmentStatus] = {
    ShipmentStatus.PREPARING: ShipmentStatus.NOT_SHIPPED,
    ShipmentStatus.SHIPPED: ShipmentStatus.PREPARING,
    ShipmentStatus.DELIVERED: ShipmentStatus.SHIPPED,
}


def _shipment_snapshot(shipment: Shipment, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "tracking_code": shipment.tracking_code,
        "shipped_at": shipment.shipped_at,
        "delivered_at": shipment.delivered_at,
    }


class AdminOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_orders(
        self,
        filters: OrderFilters,
        order_by: Sequence[UnaryExpression[Any]],
        paging: PageParams,
    ) -> Page[AdminOrderSummaryResponse]:
        item_count = (
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .where(OrderItem.order_id == Order.id)
            .scalar_subquery()
        )
        criteria = _in_range(Order.created_at, filters.created)
        for column, value in (
            (Order.status, filters.status),
            (Order.payment_status, filters.payment_status),
            (Order.shipment_status, filters.shipment_status),
        ):
            if value is not None:
                criteria.append(column == value)
        if filters.number_prefix is not None:
            criteria.append(
                Order.order_number.like(f"{escape_like(filters.number_prefix)}%", escape="\\")
            )
        if filters.mobile_digits is not None:
            criteria.append(
                Order.phone.like(f"%{escape_like(filters.mobile_digits)}%", escape="\\")
            )
        statement = select(Order, item_count).where(*criteria)
        async with self._session.begin():
            rows, total = await paginate(
                self._session, statement, order_by, tie_breaker=Order.id, params=paging
            )
        items = [
            AdminOrderSummaryResponse(
                id=order.id,
                order_number=order.order_number,
                user_id=order.user_id,
                phone=mask_phone(order.phone),
                status=order.status,
                payment_status=order.payment_status,
                shipment_status=order.shipment_status,
                grand_total=order.grand_total,
                currency=order.currency,
                item_count=int(count),
                created_at=order.created_at,
            )
            for order, count in rows
        ]
        return Page.build(items, total=total, params=paging)

    async def detail(self, order_id: UUID) -> AdminOrderDetailResponse:
        async with self._session.begin():
            order = await self._session.get(Order, order_id)
            if order is None:
                raise NotFoundError(message="Order not found")
            items = list(
                await self._session.scalars(
                    select(OrderItem)
                    .where(OrderItem.order_id == order.id)
                    .order_by(OrderItem.position)
                )
            )
            address = await self._session.get(OrderAddress, order.id)
            expires_at = await self._session.scalar(
                select(InventoryReservation.expires_at)
                .where(InventoryReservation.order_id == order.id)
                .order_by(InventoryReservation.created_at.desc(), InventoryReservation.id.desc())
                .limit(1)
            )
            payments = list(
                await self._session.scalars(
                    select(Payment)
                    .where(Payment.order_id == order.id)
                    .order_by(Payment.created_at, Payment.id)
                )
            )
            history = list(
                await self._session.scalars(
                    select(OrderStatusHistory)
                    .where(OrderStatusHistory.order_id == order.id)
                    .order_by(OrderStatusHistory.created_at, OrderStatusHistory.id)
                )
            )
            shipment = await shipment_of(self._session, order.id)
        if address is None or expires_at is None:  # ORD-04 writes both with the order
            raise RuntimeError("order is missing its address or reservation snapshot")
        return AdminOrderDetailResponse.model_validate(
            order_fields(order, address, items, expires_at)
            | {
                "user_id": order.user_id,
                "phone": order.phone,
                "cancel_reason": order.cancel_reason,
                "updated_at": order.updated_at,
                "payments": [_payment(payment, order.order_number) for payment in payments],
                "history": [
                    AdminHistoryResponse(
                        field=row.field,
                        old_status=row.old_status,
                        new_status=row.new_status,
                        actor_user_id=row.actor_user_id,
                        reason=row.reason,
                        created_at=row.created_at,
                    )
                    for row in history
                ],
                "shipment": shipment,
            }
        )

    async def update_shipment(
        self,
        actor: CurrentUser,
        order_id: UUID,
        payload: UpdateShipmentRequest,
        request: Request | None,
    ) -> AdminOrderDetailResponse:
        """Move the shipment one step (ADR-047); ``delivered`` also completes the order.

        Lock order (ADR-048): the order's advisory lock, then its row. Cart, stock and
        codes are not touched. An invalid or repeated move is 422 and changes nothing.
        """
        new_status = ShipmentStatus(payload.status)
        async with self._session.begin():
            if await self._session.scalar(select(Order.id).where(Order.id == order_id)) is None:
                raise NotFoundError(message="Order not found")
            await self._session.execute(order_advisory_lock(order_id))
            if await lock_order(self._session, order_id) is None:
                raise NotFoundError(message="Order not found")
            states = OrderStateService(self._session)
            await states.transition(
                order_id,
                StatusField.SHIPMENT,
                new_status,
                actor_user_id=actor.id,
                request=request,
            )
            shipment = await self._session.scalar(
                select(Shipment).where(Shipment.order_id == order_id).with_for_update()
            )
            if shipment is None:
                # Preparing creates the row; a later step without one is a bug, not input.
                if new_status is not ShipmentStatus.PREPARING:
                    raise RuntimeError(f"order {order_id} has no shipment row")
                shipment = Shipment(order_id=order_id)
                self._session.add(shipment)
                previous = ShipmentStatus.NOT_SHIPPED
            else:
                previous = _PREVIOUS[new_status]
            before = _shipment_snapshot(shipment, previous)
            # Taken after the locks, like every order write (ADR-048).
            now = utc_now()
            if new_status is ShipmentStatus.SHIPPED:
                shipment.tracking_code = payload.tracking_code
                shipment.shipped_at = now
            elif new_status is ShipmentStatus.DELIVERED:
                # Never before shipped_at, even with clock skew between instances.
                shipment.delivered_at = max(now, shipment.shipped_at or now)
                await states.transition(
                    order_id,
                    StatusField.ORDER,
                    OrderStatus.COMPLETED,
                    actor_user_id=actor.id,
                    reason="delivered",
                    request=request,
                )
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="shipment.updated",
                entity_type="order",
                entity_id=order_id,
                before=before,
                after=_shipment_snapshot(shipment, new_status),
                request=request,
            )
        return await self.detail(order_id)

    async def list_payments(
        self,
        filters: PaymentFilters,
        order_by: Sequence[UnaryExpression[Any]],
        paging: PageParams,
    ) -> Page[AdminPaymentResponse]:
        criteria = _in_range(Payment.created_at, filters.created)
        if filters.status is not None:
            criteria.append(Payment.status == filters.status)
        if filters.failure_reason is not None:
            criteria.append(Payment.failure_reason == filters.failure_reason)
        statement = (
            select(Payment, Order.order_number)
            .join(Order, Order.id == Payment.order_id)
            .where(*criteria)
        )
        async with self._session.begin():
            rows, total = await paginate(
                self._session, statement, order_by, tie_breaker=Payment.id, params=paging
            )
        items = [_payment(payment, number) for payment, number in rows]
        return Page.build(items, total=total, params=paging)
