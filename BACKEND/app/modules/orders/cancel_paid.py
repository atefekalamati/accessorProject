"""Staff cancel of a paid, unshipped order (ORD-11, PRD «مدیریت سفارش» ✓, ADR-063 R2).

The order is ``confirmed`` and ``paid`` and its shipment ``not_shipped`` or ``preparing``.
In the caller's transaction (never commits): every paid payment and the order payment
become ``refund_required`` (ADM-08 then records the full manual refund), the committed
stock goes back with one ``return`` movement per reservation line, the discount
redemption is released, and the order is cancelled with reason ``admin``.

Lock order (ADR-048 + payments): order advisory → order row (the caller holds both) →
payment rows (id order) → inventory items (``variant_id, warehouse_id`` order, as in
``reservation.py``, ADR-034) → redemption. The reservation itself is only read: its row,
its lines and its ``commit`` movements stay as they are.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError
from app.db.models import (
    CancelReason,
    DiscountRedemption,
    InventoryItem,
    InventoryReservation,
    InventoryReservationItem,
    MovementType,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    StatusField,
)
from app.db.models.inventory import ReservationItemStatus
from app.modules.discounts.redemption import RedemptionService
from app.modules.discounts.redemption import ReleaseOutcome as RedemptionOutcome
from app.modules.inventory.movements import Counters, record_movement
from app.modules.orders.cancel import ADMIN_REASON
from app.modules.orders.state import check_transition
from app.modules.orders.state_service import OrderStateService, invalid_transition, state_of
from app.modules.payments.common import move_order_payment, move_payment
from app.modules.payments.processing import ORDER_CANCELLED
from app.shared.audit import record_audit
from app.shared.inventory import MAX_STOCK_QUANTITY

logger = logging.getLogger(__name__)

ORDER_REFERENCE: Final = "order"
REFUND_REASON: Final = "order cancelled by staff"


class PaidOrderCancellation:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def cancel_locked(
        self, order: Order, *, actor_user_id: UUID, request: Request | None
    ) -> None:
        """Cancel a ``confirmed`` order whose advisory lock and row the caller holds."""
        if not self._session.in_transaction():
            raise RuntimeError("PaidOrderCancellation needs the caller's transaction")
        if order.status != OrderStatus.CONFIRMED:
            raise ValueError("only a confirmed order is cancelled here")
        why = check_transition(state_of(order), StatusField.ORDER, OrderStatus.CANCELLED)
        if why is not None:  # e.g. already_shipped: the return path applies
            raise invalid_transition(StatusField.ORDER, order.status, OrderStatus.CANCELLED, why)

        payments = list(
            await self._session.scalars(
                select(Payment)
                .where(Payment.order_id == order.id, Payment.status == PaymentStatus.PAID)
                .order_by(Payment.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        lines = list(
            await self._session.scalars(
                select(InventoryReservationItem)
                .join(
                    InventoryReservation,
                    InventoryReservation.id == InventoryReservationItem.reservation_id,
                )
                .where(
                    InventoryReservation.order_id == order.id,
                    InventoryReservationItem.status == ReservationItemStatus.COMMITTED,
                )
                .order_by(InventoryReservationItem.variant_id, InventoryReservationItem.id)
            )
        )
        items = {
            item.id: item
            for item in await self._session.scalars(
                select(InventoryItem)
                .where(InventoryItem.id.in_({line.inventory_item_id for line in lines}))
                .order_by(InventoryItem.variant_id, InventoryItem.warehouse_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        }
        back: dict[UUID, int] = {}
        for line in lines:
            back[line.inventory_item_id] = back.get(line.inventory_item_id, 0) + line.quantity
        for item_id, quantity in back.items():
            if items[item_id].total_quantity + quantity > MAX_STOCK_QUANTITY:
                raise BusinessRuleError(
                    message="Returning this order's units would exceed the stock limit",
                    details=[{"type": "stock_limit", "variant_id": str(items[item_id].variant_id)}],
                )
        redemption_before = await self._session.scalar(
            select(DiscountRedemption.status).where(DiscountRedemption.order_id == order.id)
        )

        # Nothing is written above this line: a refusal leaves the order untouched.
        for line in lines:
            item = items[line.inventory_item_id]
            before = Counters.of(item)
            item.total_quantity += line.quantity
            await record_movement(
                self._session,
                item,
                movement_type=MovementType.RETURN,
                quantity=line.quantity,
                before=before,
                actor_id=actor_user_id,
                reference=(ORDER_REFERENCE, order.id),
            )
        redemption = await RedemptionService(self._session).release(order.id)
        if redemption is RedemptionOutcome.RELEASED:
            await record_audit(
                self._session,
                actor_id=actor_user_id,
                action="discount.redemption_released",
                entity_type="order",
                entity_id=order.id,
                before={"redemption": redemption_before},
                after={"redemption": "released", "cancel_reason": CancelReason.ADMIN.value},
                request=request,
            )
        await OrderStateService(self._session).transition(
            order.id,
            StatusField.ORDER,
            OrderStatus.CANCELLED,
            actor_user_id=actor_user_id,
            reason=ADMIN_REASON,
            cancel_reason=CancelReason.ADMIN,
            request=request,
        )
        await self._session.refresh(order)
        for payment in payments:
            await move_payment(
                self._session,
                payment,
                PaymentStatus.REFUND_REQUIRED,
                reason=ORDER_CANCELLED,
                paid_amount=payment.paid_amount,
                request=request,
            )
            await record_audit(
                self._session,
                actor_id=None,
                action="payment.refund_required",
                entity_type="payment",
                entity_id=payment.id,
                before=None,
                after={
                    "order_number": order.order_number,
                    "amount": payment.amount,
                    "paid_amount": payment.paid_amount,
                    "reason": ORDER_CANCELLED,
                },
                request=request,
            )
        moved = await move_order_payment(
            self._session,
            order,
            PaymentStatus.REFUND_REQUIRED,
            actor_user_id=actor_user_id,
            reason=REFUND_REASON,
            request=request,
        )
        if not moved:  # never silently drop what is owed (rolls the cancel back)
            raise RuntimeError(f"order {order.id}: payment_status did not become refund_required")
        logger.info(
            "order.cancelled_paid",
            extra={
                "order_id": str(order.id),
                "payments": len(payments),
                "units_returned": sum(back.values()),
                "redemption": redemption.value,
            },
        )
