"""What counts as a sale (CAT-17, ADR-047): one definition for sorting and reports."""

from __future__ import annotations

from sqlalchemy import ColumnElement, Subquery, func, select

from app.db.models import Order, OrderItem, PaymentStatus


def successful_order() -> ColumnElement[bool]:
    """Paid orders only: cancelled, unpaid and refund_required ones never count."""
    return Order.payment_status == PaymentStatus.PAID


def units_sold_by_product() -> Subquery:
    """``(product_id, units)`` over the lines of successful orders, one row per product."""
    return (
        select(
            OrderItem.product_id.label("product_id"), func.sum(OrderItem.quantity).label("units")
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(successful_order())
        .group_by(OrderItem.product_id)
        .subquery("units_sold")
    )
