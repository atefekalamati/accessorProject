"""Discount codes and their redemptions (DSC-01, ADR-039, ADR-042)."""

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
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.phone import MOBILE_E164_PATTERN
from app.db.base import Base
from app.db.models.common import (
    CreatedAtMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.shared.money import MAX_PRICE_TOMAN

MAX_CODE_LENGTH: Final = 32
CODE_PATTERN_SQL: Final = f"^[A-Z0-9_-]{{3,{MAX_CODE_LENGTH}}}$"
# Percent codes are stored in basis points, like the calculator (10 000 = 100%).
MAX_PERCENT_BPS: Final = 10_000


class DiscountType(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


class RedemptionStatus(StrEnum):
    # Created by POST /orders; counts toward the limits (D31).
    PENDING = "pending"
    # The order was paid.
    CONFIRMED = "confirmed"
    # The order was cancelled or its reservation expired; counts no more.
    RELEASED = "released"


LIVE_REDEMPTION_SQL: Final = "status IN ('pending', 'confirmed')"
_TYPES_SQL: Final = ", ".join(f"'{t.value}'" for t in DiscountType)
_STATUSES_SQL: Final = ", ".join(f"'{s.value}'" for s in RedemptionStatus)


class DiscountCode(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A code shoppers type; ``code`` is stored normalized (trimmed, ASCII upper case)."""

    __tablename__ = "discount_codes"
    __table_args__ = (
        CheckConstraint(f"code ~ '{CODE_PATTERN_SQL}'", name="code_format"),
        CheckConstraint(f"type IN ({_TYPES_SQL})", name="valid_type"),
        CheckConstraint(
            f"(type = 'percent' AND value BETWEEN 1 AND {MAX_PERCENT_BPS})"
            f" OR (type = 'fixed' AND value BETWEEN 1 AND {MAX_PRICE_TOMAN})",
            name="value_range",
        ),
        # A cap only limits a percentage; a fixed amount is its own cap.
        CheckConstraint(
            "max_amount IS NULL OR (type = 'percent'"
            f" AND max_amount BETWEEN 1 AND {MAX_PRICE_TOMAN})",
            name="max_amount_range",
        ),
        CheckConstraint(
            f"min_order_amount IS NULL OR min_order_amount BETWEEN 1 AND {MAX_PRICE_TOMAN}",
            name="min_order_amount_range",
        ),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at", name="valid_window"
        ),
        CheckConstraint(
            "usage_limit_total IS NULL OR usage_limit_total >= 1", name="usage_limit_total_range"
        ),
        CheckConstraint(
            "usage_limit_per_user IS NULL OR usage_limit_per_user >= 1",
            name="usage_limit_per_user_range",
        ),
        CheckConstraint(
            "usage_limit_per_user IS NULL OR usage_limit_total IS NULL"
            " OR usage_limit_per_user <= usage_limit_total",
            name="per_user_within_total",
        ),
        Index(
            "uq_discount_codes_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(MAX_CODE_LENGTH), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    # Basis points for a percentage, Toman for a fixed amount.
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    min_order_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Valid in [starts_at, ends_at); a missing end is open.
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_limit_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Counted per normalized mobile number, not per account (ADR-017).
    usage_limit_per_user: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class DiscountRedemption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One use of a code by one order (D31): pending at POST /orders, confirmed when paid,
    released on cancel or reservation expiry. Only live rows count toward the limits."""

    __tablename__ = "discount_redemptions"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUSES_SQL})", name="valid_status"),
        CheckConstraint(f"phone ~ '{MOBILE_E164_PATTERN}'", name="phone_format"),
        CheckConstraint(f"code ~ '{CODE_PATTERN_SQL}'", name="code_format"),
        # Zero is valid: a small percentage can round to nothing (ADR-031).
        CheckConstraint(f"amount BETWEEN 0 AND {MAX_PRICE_TOMAN}", name="amount_range"),
        CheckConstraint(
            "(status = 'released') = (released_at IS NOT NULL)", name="released_has_time"
        ),
        # A released redemption keeps confirmed_at if it was paid first (refunds, D32).
        CheckConstraint(
            "(status <> 'confirmed' OR confirmed_at IS NOT NULL)"
            " AND (status <> 'pending' OR confirmed_at IS NULL)",
            name="confirmed_has_time",
        ),
        CheckConstraint(
            "released_at IS NULL OR confirmed_at IS NULL OR released_at >= confirmed_at",
            name="released_after_confirmed",
        ),
        Index(
            "uq_discount_redemptions_live_order",
            "order_id",
            unique=True,
            postgresql_where=text(LIVE_REDEMPTION_SQL),
        ),
        # Serves both counts: total (leading column) and per mobile number.
        Index(
            "ix_discount_redemptions_live_code_phone",
            "discount_code_id",
            "phone",
            postgresql_where=text(LIVE_REDEMPTION_SQL),
        ),
        Index("ix_discount_redemptions_order_id", "order_id"),
    )

    discount_code_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("discount_codes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The per-user limit key: the normalized mobile number (ADR-017).
    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    # Snapshot of the code as typed for this order; later edits of the code never touch it.
    code: Mapped[str] = mapped_column(String(MAX_CODE_LENGTH), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=RedemptionStatus.PENDING, server_default="pending"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiscountAttempt(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One failed POST /cart/discount, counted by the rate limit (DSC-03, D34, ADR-043).

    Successful attempts are not stored and never reset the count. Rows older than the
    window are deleted when a new failure is recorded.
    """

    __tablename__ = "discount_attempts"
    __table_args__ = (
        CheckConstraint("cart_id IS NOT NULL OR user_id IS NOT NULL", name="has_owner"),
        Index("ix_discount_attempts_cart_id_created_at", "cart_id", "created_at"),
        Index("ix_discount_attempts_user_id_created_at", "user_id", "created_at"),
        Index("ix_discount_attempts_ip_created_at", "ip", "created_at"),
    )

    # The guest's cart, or the signed-in user (whose budget follows the account).
    cart_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
