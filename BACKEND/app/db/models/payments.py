"""Payments of orders, their gateway events, and the fake gateway's sessions (PAY-01).

PRD «پرداخت» ✓, ADR-001, ADR-009, ADR-049, ADR-051. Amounts are integer toman; rial
exists only inside a gateway adapter. A payment row never holds card data: its
``raw_event`` and the events keep only an adapter's allowlisted, redacted fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.idempotency import MAX_IDEMPOTENCY_KEY_LENGTH
from app.db.models.orders import PaymentStatus

MAX_GATEWAY_NAME_LENGTH: Final = 32
MAX_GATEWAY_REFERENCE_LENGTH: Final = 128
MAX_FAILURE_REASON_LENGTH: Final = 64
MAX_REDIRECT_URL_LENGTH: Final = 2048
GATEWAY_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]*$"
# Printable ASCII without spaces: refs come from the gateway (or a forged callback).
GATEWAY_REFERENCE_PATTERN: Final = r"^[!-~]+$"
# A payment row is never ``unpaid``: that is the order's status before any attempt.
PAYMENT_ROW_STATUSES: Final = tuple(s for s in PaymentStatus if s is not PaymentStatus.UNPAID)
_ROW_STATUSES_SQL: Final = ", ".join(f"'{status.value}'" for status in PAYMENT_ROW_STATUSES)


class PaymentEventKind:
    CALLBACK: Final = "callback"
    VERIFY: Final = "verify"


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One attempt to pay an order; an order may have several (retry after a failure).

    ``failure_reason`` is set exactly when failed or refund_required, so a late
    ``failed → paid`` clears it in the same update; the earlier reason stays in the
    payment's events and audit rows.

    ``gateway_reference`` is NULL until the gateway answers the request. At most one
    ``pending`` payment per order, and (gateway, reference) is unique: a callback finds
    exactly one payment.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(f"status IN ({_ROW_STATUSES_SQL})", name="valid_status"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(f"gateway ~ '{GATEWAY_NAME_PATTERN}'", name="gateway_format"),
        CheckConstraint(
            f"gateway_reference IS NULL OR gateway_reference ~ '{GATEWAY_REFERENCE_PATTERN}'",
            name="gateway_reference_format",
        ),
        CheckConstraint("status <> 'paid' OR paid_at IS NOT NULL", name="paid_has_paid_at"),
        # A refund_required payment took money too (late, duplicate or wrong amount).
        CheckConstraint(
            "paid_at IS NULL OR status IN ('paid', 'refund_required')", name="paid_at_when_paid"
        ),
        CheckConstraint(
            "(status IN ('failed', 'refund_required')) = (failure_reason IS NOT NULL)",
            name="closed_has_reason",
        ),
        # Money was taken (late, duplicate or wrong amount): the refund needs its record.
        CheckConstraint(
            "status <> 'refund_required' OR paid_at IS NOT NULL", name="refund_was_paid"
        ),
        CheckConstraint("paid_amount IS NULL OR paid_amount >= 0", name="paid_amount_range"),
        CheckConstraint(
            "(redirect_url IS NULL) = (gateway_reference IS NULL)", name="redirect_with_reference"
        ),
        CheckConstraint(
            "(gateway_expires_at IS NULL) = (gateway_reference IS NULL)",
            name="expires_with_reference",
        ),
        Index(
            "uq_payments_gateway_reference",
            "gateway",
            "gateway_reference",
            unique=True,
            postgresql_where=text("gateway_reference IS NOT NULL"),
        ),
        Index(
            "uq_payments_one_pending_per_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_payments_order_id", "order_id"),
        Index(
            "ix_payments_pending_created_at",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    order_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    gateway: Mapped[str] = mapped_column(String(MAX_GATEWAY_NAME_LENGTH), nullable=False)
    gateway_reference: Mapped[str | None] = mapped_column(
        String(MAX_GATEWAY_REFERENCE_LENGTH), nullable=True
    )
    redirect_url: Mapped[str | None] = mapped_column(String(MAX_REDIRECT_URL_LENGTH))
    # When the gateway's session for this payment stops accepting the customer (ADR-051).
    gateway_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The init request's key, for support and to tell a retried init apart.
    idempotency_key: Mapped[str] = mapped_column(String(MAX_IDEMPOTENCY_KEY_LENGTH), nullable=False)
    # Expected toman: the order's grand_total when the payment started.
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Toman the gateway confirmed it took; NULL if not paid or not a whole toman (the rial
    # stays in ``raw_event``). With amount_mismatch it is the figure to refund.
    paid_amount: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PaymentStatus.PENDING.value
    )
    failure_reason: Mapped[str | None] = mapped_column(String(MAX_FAILURE_REASON_LENGTH))
    # The last verify result, allowlisted and redacted by the adapter.
    raw_event: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A redacted record of every callback and verify, kept for disputes (ADR-051).

    Callback rows also feed the per-IP rate limit (rows inside its window count).
    Reconciliation's verifies are ``verify`` rows too.
    """

    __tablename__ = "payment_events"
    __table_args__ = (
        CheckConstraint("kind IN ('callback', 'verify')", name="valid_kind"),
        CheckConstraint(f"gateway ~ '{GATEWAY_NAME_PATTERN}'", name="gateway_format"),
        Index("ix_payment_events_ip_created_at", "ip", "created_at"),
        Index("ix_payment_events_payment_id", "payment_id"),
        # Unknown-reference callbacks have no payment: support finds them by reference.
        Index("ix_payment_events_gateway_reference", "gateway", "gateway_reference"),
    )

    payment_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL")
    )
    gateway: Mapped[str] = mapped_column(String(MAX_GATEWAY_NAME_LENGTH), nullable=False)
    gateway_reference: Mapped[str | None] = mapped_column(String(MAX_GATEWAY_REFERENCE_LENGTH))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class FakeGatewaySession(CreatedAtMixin, Base):
    """The fake gateway's side of a payment (dev, test and staging only; ADR-051).

    In the database so a restart, several workers or replicas never lose a session.
    The production gateway never reads or writes it.
    """

    __tablename__ = "fake_gateway_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'paid', 'failed')", name="valid_status"),
        CheckConstraint("amount_rial > 0", name="amount_positive"),
        CheckConstraint(
            "(status = 'paid') = (paid_amount_rial IS NOT NULL)", name="paid_has_amount"
        ),
    )

    reference: Mapped[str] = mapped_column(String(MAX_GATEWAY_REFERENCE_LENGTH), primary_key=True)
    payment_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    amount_rial: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    paid_amount_rial: Mapped[int | None] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
