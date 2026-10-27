"""Report queries: aggregates computed in SQL, a fixed number of statements per request.

A sale is an order with ``payment_status = paid`` (ADR-047, ``orders.sales``); it is dated
by the successful payment's ``paid_at`` (D39, ADR-055).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Subquery, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    InventoryReservation,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Product,
    ProductVariant,
    ReservationStatus,
    Role,
    ShipmentStatus,
    User,
    UserRole,
)
from app.db.models.common import not_deleted
from app.modules.auth.service import CUSTOMER_ROLE
from app.modules.inventory.admin_repository import stock_columns
from app.modules.inventory.stock import StockStatus
from app.modules.orders.sales import successful_order
from app.modules.reports.periods import DAYS_BEFORE_TODAY, DashboardPeriod, day_start


def paid_at_by_order(since: ColumnElement[datetime]) -> Subquery:
    """``(order_id, paid_at)``: the first successful payment, one row per order.

    An order may have several ``paid`` rows; the earliest dates it. ``since`` goes in HAVING,
    not WHERE, so a later duplicate payment never re-dates an older order.
    """
    first_paid = func.min(Payment.paid_at)
    return (
        select(Payment.order_id.label("order_id"), first_paid.label("paid_at"))
        .where(Payment.status == PaymentStatus.PAID)
        .group_by(Payment.order_id)
        .having(first_paid >= since)
        .subquery("paid")
    )


@dataclass(frozen=True, slots=True)
class PeriodFigures:
    starts_at: datetime
    sales_count: int
    sales_amount: int
    new_customers: int


@dataclass(frozen=True, slots=True)
class DashboardFigures:
    periods: dict[DashboardPeriod, PeriodFigures]
    pending_payment_orders: int
    refund_required_payments: int
    orders_to_ship: int
    low_stock_variants: int
    out_of_stock_variants: int


def _count(criteria: ColumnElement[bool]) -> ColumnElement[int]:
    return func.count().filter(criteria)


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def dashboard(self, now: datetime) -> DashboardFigures:
        starts = {period: day_start(now, days) for period, days in DAYS_BEFORE_TODAY.items()}
        earliest = starts[DashboardPeriod.LAST_30_DAYS]
        paid = paid_at_by_order(earliest)

        sales_columns: list[Any] = []
        for period, start in starts.items():
            in_period = paid.c.paid_at >= start
            sales_columns += [
                start.label(f"{period}_start"),
                _count(in_period).label(f"{period}_count"),
                func.coalesce(func.sum(Order.grand_total).filter(in_period), 0).label(
                    f"{period}_amount"
                ),
            ]
        sales = (
            await self._session.execute(
                select(*sales_columns)
                .select_from(Order)
                .join(paid, paid.c.order_id == Order.id)
                .where(successful_order(), paid.c.paid_at >= earliest, paid.c.paid_at <= now)
            )
        ).one()

        # Users soft-deleted since are left out, so a past period's figure can only drop.
        is_customer = exists().where(
            UserRole.user_id == User.id, UserRole.role_id == Role.id, Role.name == CUSTOMER_ROLE
        )
        customers = (
            await self._session.execute(
                select(
                    *(
                        _count(User.created_at >= start).label(str(period))
                        for period, start in starts.items()
                    )
                ).where(
                    not_deleted(User),
                    is_customer,
                    User.created_at >= earliest,
                    User.created_at <= now,
                )
            )
        ).one()

        live_reservation = exists().where(
            InventoryReservation.order_id == Order.id,
            InventoryReservation.status == ReservationStatus.ACTIVE,
            InventoryReservation.expires_at > now,
        )
        orders = (
            await self._session.execute(
                select(
                    _count(
                        and_(Order.status == OrderStatus.PENDING_PAYMENT, live_reservation)
                    ).label("pending"),
                    _count(
                        and_(
                            Order.status == OrderStatus.CONFIRMED,
                            Order.shipment_status.in_(
                                (ShipmentStatus.NOT_SHIPPED, ShipmentStatus.PREPARING)
                            ),
                        )
                    ).label("to_ship"),
                    select(func.count())
                    .select_from(Payment)
                    .where(Payment.status == PaymentStatus.REFUND_REQUIRED)
                    .scalar_subquery()
                    .label("refund_required"),
                ).where(Order.status.in_((OrderStatus.PENDING_PAYMENT, OrderStatus.CONFIRMED)))
            )
        ).one()

        # Active variants only (unlike the inventory list): an inactive one is not on sale.
        items, stock = stock_columns(now)
        stock_counts = (
            await self._session.execute(
                select(
                    _count(stock.status == StockStatus.LOW_STOCK.value).label("low"),
                    _count(stock.status == StockStatus.OUT_OF_STOCK.value).label("out"),
                )
                .select_from(ProductVariant)
                .join(Product, Product.id == ProductVariant.product_id)
                .outerjoin(items, items.c.variant_id == ProductVariant.id)
                .where(ProductVariant.is_active, not_deleted(ProductVariant), not_deleted(Product))
            )
        ).one()

        mapping = sales._mapping
        return DashboardFigures(
            periods={
                period: PeriodFigures(
                    starts_at=mapping[f"{period}_start"],
                    sales_count=int(mapping[f"{period}_count"]),
                    sales_amount=int(mapping[f"{period}_amount"]),
                    new_customers=int(customers._mapping[str(period)]),
                )
                for period in starts
            },
            pending_payment_orders=int(orders.pending),
            refund_required_payments=int(orders.refund_required),
            orders_to_ship=int(orders.to_ship),
            low_stock_variants=int(stock_counts.low),
            out_of_stock_variants=int(stock_counts.out),
        )
