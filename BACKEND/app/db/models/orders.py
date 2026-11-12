"""Orders and their snapshots (ORD-01, ADR-031, ADR-039, ADR-046).

An order never changes after it is placed (D33): every title, price, address and method
it shows is copied here, so later product, price, address, code or shipping changes never
reach it. Only the three statuses move (ORD-05), each change logged in
``order_status_history``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Sequence,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.phone import MOBILE_E164_PATTERN
from app.db.base import Base
from app.db.models.common import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.inventory import MAX_STOCK_QUANTITY
from app.shared.money import MAX_PRICE_TOMAN, MAX_ROUNDING_STEP, MAX_TAX_RATE_BPS, RoundingMode

# ``ORD-<UTC year>-<global sequence, at least 6 digits>``: never shaped like a mobile number.
ORDER_NUMBER_PATTERN: Final = r"^ORD-[0-9]{4}-[0-9]{6,}$"
# Global and never reset yearly; gaps (rolled back orders) are fine.
order_number_seq = Sequence("order_number_seq", metadata=Base.metadata)


def format_order_number(year: int, number: int) -> str:
    if isinstance(year, bool) or not isinstance(year, int) or not 1000 <= year <= 9999:
        raise ValueError("year must be a four-digit int")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("number must be a positive int")
    return f"ORD-{year:04d}-{number:06d}"


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    UNPAID = "unpaid"
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    # The gateway took money the shop must give back (late, duplicate or wrong amount, D32).
    REFUND_REQUIRED = "refund_required"
    # Given back by hand and recorded by staff (ADM-08, D35).
    REFUNDED = "refunded"


class ShipmentStatus(StrEnum):
    NOT_SHIPPED = "not_shipped"
    PREPARING = "preparing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"


class CancelReason(StrEnum):
    CUSTOMER = "customer"
    # The reservation expired before payment (D34).
    EXPIRED = "expired"
    ADMIN = "admin"


class StatusField(StrEnum):
    ORDER = "order"
    PAYMENT = "payment"
    SHIPMENT = "shipment"


def _sql_list(values: type[StrEnum]) -> str:
    return ", ".join(f"'{value.value}'" for value in values)


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The header of one order with its priced totals (ADR-031 mapping).

    The header totals equal the sums of the lines; a CHECK cannot span rows, so ORD-04
    asserts it when it builds the order.
    """

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(f"order_number ~ '{ORDER_NUMBER_PATTERN}'", name="order_number_format"),
        # ORD-04 sets created_at from the same ``now`` as the number's year (never the
        # flush-time default, which could cross the year boundary). Guarded so a malformed
        # number fails order_number_format instead of the int cast.
        CheckConstraint(
            f"order_number !~ '{ORDER_NUMBER_PATTERN}'"
            " OR substring(order_number from 5 for 4)::int"
            " = extract(year from created_at AT TIME ZONE 'UTC')::int",
            name="order_number_year",
        ),
        CheckConstraint(f"phone ~ '{MOBILE_E164_PATTERN}'", name="phone_format"),
        CheckConstraint(f"status IN ({_sql_list(OrderStatus)})", name="valid_status"),
        CheckConstraint(
            f"payment_status IN ({_sql_list(PaymentStatus)})", name="valid_payment_status"
        ),
        CheckConstraint(
            f"shipment_status IN ({_sql_list(ShipmentStatus)})", name="valid_shipment_status"
        ),
        CheckConstraint(
            f"cancel_reason IS NULL OR cancel_reason IN ({_sql_list(CancelReason)})",
            name="valid_cancel_reason",
        ),
        CheckConstraint(
            "(status = 'cancelled') = (cancel_reason IS NOT NULL)", name="cancelled_has_reason"
        ),
        CheckConstraint(
            "subtotal >= 0 AND product_discount_total >= 0 AND discount_code_amount >= 0"
            " AND tax_amount >= 0 AND shipping_amount >= 0 AND grand_total >= 0",
            name="amounts_non_negative",
        ),
        # numeric: an intermediate sum may pass BIGINT even when the result fits.
        CheckConstraint(
            "grand_total::numeric = subtotal::numeric - product_discount_total"
            " - discount_code_amount + tax_amount + shipping_amount",
            name="grand_total_sum",
        ),
        CheckConstraint(
            "subtotal::numeric - product_discount_total - discount_code_amount >= 0",
            name="discounts_within_subtotal",
        ),
        CheckConstraint("currency = 'TOMAN'", name="currency_toman"),
        CheckConstraint(
            "(discount_code_id IS NULL) = (discount_code IS NULL)", name="code_snapshot_pair"
        ),
        CheckConstraint(
            "discount_code_id IS NOT NULL OR discount_code_amount = 0",
            name="code_amount_needs_code",
        ),
        CheckConstraint(
            "shipping_method_title = btrim(shipping_method_title) AND shipping_method_title <> ''",
            name="shipping_method_title_format",
        ),
        UniqueConstraint("order_number"),
        Index("ix_orders_user_id_created_at", "user_id", "created_at"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_payment_status", "payment_status"),
    )

    order_number: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # The verified mobile the order was placed with (redemption limits count it, D31).
    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=OrderStatus.PENDING_PAYMENT,
        server_default=OrderStatus.PENDING_PAYMENT.value,
    )
    payment_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PaymentStatus.UNPAID,
        server_default=PaymentStatus.UNPAID.value,
    )
    shipment_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ShipmentStatus.NOT_SHIPPED,
        server_default=ShipmentStatus.NOT_SHIPPED.value,
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    subtotal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_discount_total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_code_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shipping_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    grand_total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default="TOMAN", server_default="TOMAN"
    )
    discount_code_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("discount_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    discount_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shipping_method_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("shipping_methods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    shipping_method_title: Mapped[str] = mapped_column(String(100), nullable=False)


class OrderItem(UUIDPrimaryKeyMixin, Base):
    """One priced line, copied at purchase (ADR-031: ``unit_price`` is the original price,
    ``discount_amount`` = product + code discount)."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint(f"quantity BETWEEN 1 AND {MAX_STOCK_QUANTITY}", name="quantity_range"),
        CheckConstraint(
            f"unit_price BETWEEN 0 AND {MAX_PRICE_TOMAN}"
            " AND unit_final_price BETWEEN 0 AND unit_price",
            name="unit_prices_range",
        ),
        CheckConstraint(
            "product_discount >= 0 AND code_discount >= 0 AND tax_amount >= 0"
            " AND final_line_total >= 0",
            name="amounts_non_negative",
        ),
        CheckConstraint(
            "subtotal::numeric = unit_price::numeric * quantity", name="subtotal_product"
        ),
        CheckConstraint(
            "product_discount::numeric = (unit_price::numeric - unit_final_price) * quantity",
            name="product_discount_product",
        ),
        CheckConstraint(
            "discount_amount::numeric = product_discount::numeric + code_discount",
            name="discount_amount_sum",
        ),
        CheckConstraint(
            "subtotal::numeric - discount_amount >= 0", name="discount_within_subtotal"
        ),
        CheckConstraint(
            "final_line_total::numeric = subtotal::numeric - discount_amount + tax_amount",
            name="final_line_total_sum",
        ),
        CheckConstraint(
            "product_title = btrim(product_title) AND product_title <> ''",
            name="product_title_format",
        ),
        # The variant must belong to the stored product; referenced ones are only soft deleted.
        ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_order_items_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("order_id", "position"),
        Index("ix_order_items_variant_id", "variant_id"),
        Index("ix_order_items_product_id", "product_id"),
    )

    order_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # The stable line order the pricing ran in (ADR-031: by line id).
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    product_title: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    # The variant's options at purchase, e.g. "color: Red / size: M"; empty if none.
    variant_label: Mapped[str] = mapped_column(String(300), nullable=False, server_default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_final_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subtotal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_discount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    code_discount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    final_line_total: Mapped[int] = mapped_column(BigInteger, nullable=False)


class OrderPriceSnapshot(Base):
    """The pricing policy and quote an order was priced with (one per order)."""

    __tablename__ = "order_price_snapshots"
    __table_args__ = (
        CheckConstraint("pricing_version >= 1", name="pricing_version_positive"),
        CheckConstraint(f"tax_rate_bps BETWEEN 0 AND {MAX_TAX_RATE_BPS}", name="tax_rate_range"),
        CheckConstraint(
            f"rounding_mode IN ({_sql_list(RoundingMode)})", name="valid_rounding_mode"
        ),
        CheckConstraint(
            f"rounding_step BETWEEN 1 AND {MAX_ROUNDING_STEP}", name="rounding_step_range"
        ),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint_format"),
        CheckConstraint(
            f"shipping_method_cost BETWEEN 0 AND {MAX_PRICE_TOMAN}",
            name="shipping_method_cost_range",
        ),
        CheckConstraint(
            "shipping_free_threshold IS NULL"
            f" OR shipping_free_threshold BETWEEN 1 AND {MAX_PRICE_TOMAN}",
            name="shipping_free_threshold_range",
        ),
    )

    order_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    pricing_version: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tax_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    rounding_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    rounding_step: Mapped[int] = mapped_column(Integer, nullable=False)
    # The checkout quote fingerprint (ORD-03): prices, code and amount, method and cost (D34).
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The method's cost and free threshold at purchase; shipping_amount is 0 or the cost.
    shipping_method_cost: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shipping_free_threshold: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class OrderAddress(Base):
    """A copy of the delivery address (no FK: addresses are hard deleted, ADR-045)."""

    __tablename__ = "order_addresses"
    __table_args__ = (
        CheckConstraint(f"phone ~ '{MOBILE_E164_PATTERN}'", name="phone_format"),
        CheckConstraint("postal_code ~ '^[0-9]{10}$'", name="postal_code_format"),
        CheckConstraint("length(btrim(recipient_name)) > 0", name="recipient_name_not_blank"),
    )

    order_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_address_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    province: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    address_line: Mapped[str] = mapped_column(String(500), nullable=False)
    plaque: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)


class OrderStatusHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One status change of one of the three fields (ORD-05); a null actor is the system."""

    __tablename__ = "order_status_history"
    __table_args__ = (
        CheckConstraint(f"field IN ({_sql_list(StatusField)})", name="valid_field"),
        CheckConstraint("old_status IS NULL OR old_status <> new_status", name="status_changes"),
        Index("ix_order_status_history_order_id_created_at", "order_id", "created_at"),
    )

    order_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(String(10), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


# Carrier tracking codes are short; printable text, trimmed by the API.
MAX_TRACKING_CODE_LENGTH: Final = 64


class Shipment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The delivery of one order (ADM-02, ADR-053): created when it starts preparing.

    ``orders.shipment_status`` stays the source of the status; this row adds the carrier
    tracking code and when the parcel was shipped and delivered.
    """

    __tablename__ = "shipments"
    __table_args__ = (
        CheckConstraint(
            "tracking_code IS NULL"
            " OR (tracking_code = btrim(tracking_code) AND tracking_code <> '')",
            name="tracking_code_not_blank",
        ),
        CheckConstraint("shipped_at IS NULL OR tracking_code IS NOT NULL", name="shipped_has_code"),
        CheckConstraint(
            "delivered_at IS NULL OR (shipped_at IS NOT NULL AND delivered_at >= shipped_at)",
            name="delivered_after_shipped",
        ),
    )

    order_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    tracking_code: Mapped[str | None] = mapped_column(
        String(MAX_TRACKING_CODE_LENGTH), nullable=True
    )
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
