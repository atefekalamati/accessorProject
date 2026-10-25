"""Shipping methods (ADDR-02, ADR-045)."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.money import MAX_PRICE_TOMAN


class ShippingMethod(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A way to ship an order: a flat cost, free from an optional threshold (D33, D34).

    Only soft deleted: orders keep a snapshot of the method and its cost (ORD-01), and the
    future Shipment FK is RESTRICT.
    """

    __tablename__ = "shipping_methods"
    # Lengths are enforced by the column types (VARCHAR 100/500); the CHECK adds trimming.
    __table_args__ = (
        CheckConstraint("title = btrim(title) AND title <> ''", name="title_format"),
        # 0 means always free.
        CheckConstraint(f"cost BETWEEN 0 AND {MAX_PRICE_TOMAN}", name="cost_range"),
        CheckConstraint(
            "free_shipping_threshold IS NULL"
            f" OR free_shipping_threshold BETWEEN 1 AND {MAX_PRICE_TOMAN}",
            name="free_shipping_threshold_range",
        ),
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
    )

    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cost: Mapped[int] = mapped_column(BigInteger, nullable=False)
    free_shipping_threshold: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
