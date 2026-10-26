"""The customer's own orders: list and detail (ACC-01, PRD «سفارش‌ها» ✓, ADR-053).

Reads only: an unpaid order past its deadline is shown as it is stored, with ``can_pay``
and ``can_cancel`` false, until the expiry job cancels it (ADR-050).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import UnaryExpression

from app.core.errors import NotFoundError
from app.core.time import utc_now
from app.db.models import (
    InventoryReservation,
    Order,
    OrderAddress,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    Payment,
    PaymentStatus,
    ReservationStatus,
)
from app.modules.catalog.product_repository import ProductRepository
from app.modules.orders.schemas import (
    OrderDetailResponse,
    OrderHistoryResponse,
    OrderPaymentResponse,
    OrderSummaryResponse,
)
from app.modules.orders.service import order_fields
from app.shared.pagination import Page, PageParams, paginate
from app.shared.storage import FileStorage

# A customer may cancel only while no payment is under way (ADR-050).
_CANCELLABLE_PAYMENTS = frozenset({PaymentStatus.UNPAID, PaymentStatus.FAILED})


def _not_found() -> NotFoundError:
    # Someone else's order and an unknown one get the same answer (no existence leak).
    return NotFoundError(message="Order not found")


class AccountOrderService:
    def __init__(self, session: AsyncSession, storage: FileStorage) -> None:
        self._session = session
        self._storage = storage

    async def list_orders(
        self,
        user_id: UUID,
        *,
        status: OrderStatus | None,
        order_by: Sequence[UnaryExpression[Any]],
        paging: PageParams,
    ) -> Page[OrderSummaryResponse]:
        statement = select(Order).where(Order.user_id == user_id)
        if status is not None:
            statement = statement.where(Order.status == status)
        async with self._session.begin():
            rows, total = await paginate(
                self._session, statement, order_by, tie_breaker=Order.id, params=paging
            )
            orders: list[Order] = [row[0] for row in rows]
            ids = [order.id for order in orders]
            counts, firsts = await self._line_facts(ids)
            images = await ProductRepository(self._session).main_image_keys(
                list(set(firsts.values()))
            )
        items = []
        for order in orders:
            key = images.get(firsts[order.id]) if order.id in firsts else None
            items.append(
                OrderSummaryResponse(
                    id=order.id,
                    order_number=order.order_number,
                    status=order.status,
                    payment_status=order.payment_status,
                    shipment_status=order.shipment_status,
                    grand_total=order.grand_total,
                    currency=order.currency,
                    item_count=counts.get(order.id, 0),
                    image_url=None if key is None else self._storage.url(key),
                    created_at=order.created_at,
                )
            )
        return Page.build(items, total=total, params=paging)

    async def _line_facts(self, order_ids: list[UUID]) -> tuple[dict[UUID, int], dict[UUID, UUID]]:
        """Item count (sum of quantities) and the first line's product of each order."""
        if not order_ids:
            return {}, {}
        totals = await self._session.execute(
            select(OrderItem.order_id, func.sum(OrderItem.quantity))
            .where(OrderItem.order_id.in_(order_ids))
            .group_by(OrderItem.order_id)
        )
        firsts = await self._session.execute(
            select(OrderItem.order_id, OrderItem.product_id)
            .where(OrderItem.order_id.in_(order_ids))
            .ext(distinct_on(OrderItem.order_id))
            .order_by(OrderItem.order_id, OrderItem.position)
        )
        return (
            {order_id: int(total) for order_id, total in totals},
            {order_id: product_id for order_id, product_id in firsts},
        )

    async def detail(self, user_id: UUID, order_number: str) -> OrderDetailResponse:
        now = utc_now()
        async with self._session.begin():
            order = await self._session.scalar(
                select(Order).where(Order.order_number == order_number, Order.user_id == user_id)
            )
            if order is None:
                raise _not_found()
            items = list(
                await self._session.scalars(
                    select(OrderItem)
                    .where(OrderItem.order_id == order.id)
                    .order_by(OrderItem.position)
                )
            )
            address = await self._session.get(OrderAddress, order.id)
            reservation = await self._session.scalar(
                select(InventoryReservation)
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
        if address is None or reservation is None:  # ORD-04 writes both with the order
            raise RuntimeError("order is missing its address or reservation snapshot")
        live = (
            order.status == OrderStatus.PENDING_PAYMENT
            and reservation.status == ReservationStatus.ACTIVE
            and reservation.expires_at > now
        )
        fields = order_fields(order, address, items, reservation.expires_at)
        return OrderDetailResponse.model_validate(
            fields
            | {
                "cancel_reason": order.cancel_reason,
                "payments": [
                    OrderPaymentResponse(
                        id=payment.id,
                        status=payment.status,
                        amount=payment.amount,
                        created_at=payment.created_at,
                        paid_at=payment.paid_at,
                    )
                    for payment in payments
                ],
                "history": [
                    OrderHistoryResponse(
                        field=row.field,
                        old_status=row.old_status,
                        new_status=row.new_status,
                        created_at=row.created_at,
                    )
                    for row in history
                ],
                "shipment": None,
                "payment_deadline": (
                    reservation.expires_at if order.status == OrderStatus.PENDING_PAYMENT else None
                ),
                "can_pay": live,
                "can_cancel": live and order.payment_status in _CANCELLABLE_PAYMENTS,
            }
        )
