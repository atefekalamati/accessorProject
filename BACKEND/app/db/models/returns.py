"""Return requests (ORD-08..ORD-10, PRD «مرجوعی» ✓, ADR-063).

A customer asks to return lines of a delivered order; staff approve or reject, receive
and inspect the goods (stock goes back only for ``sellable`` items) and record a manual
refund. Requests are never deleted. Each status change is logged in
``return_status_history``.
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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.payments import MAX_REFUND_REFERENCE_LENGTH, REFUND_REFERENCE_PATTERN
from app.shared.inventory import MAX_STOCK_QUANTITY

MAX_RETURN_NOTE_LENGTH: Final = 1000
MAX_RETURN_ADMIN_NOTE_LENGTH: Final = 2000


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    RECEIVED = "received"
    INSPECTED = "inspected"
    REFUND_REQUIRED = "refund_required"
    REFUNDED = "refunded"
    CLOSED = "closed"


class ReturnReason(StrEnum):
    DEFECTIVE = "defective"
    WRONG_ITEM = "wrong_item"
    NOT_AS_DESCRIBED = "not_as_described"
    CHANGED_MIND = "changed_mind"
    OTHER = "other"


class ItemCondition(StrEnum):
    SELLABLE = "sellable"
    DAMAGED = "damaged"


def _sql_list(values: type[StrEnum] | tuple[StrEnum, ...]) -> str:
    return ", ".join(f"'{value.value}'" for value in values)


# A request still claims its quantity unless it was rejected or cancelled.
RELEASED_STATUSES: Final = (ReturnStatus.REJECTED, ReturnStatus.CANCELLED)
_DECIDED: Final = tuple(
    s for s in ReturnStatus if s not in (ReturnStatus.REQUESTED, ReturnStatus.CANCELLED)
)
_RECEIVED: Final = (
    ReturnStatus.RECEIVED,
    ReturnStatus.INSPECTED,
    ReturnStatus.REFUND_REQUIRED,
    ReturnStatus.REFUNDED,
    ReturnStatus.CLOSED,
)
_INSPECTED: Final = _RECEIVED[1:]


def _text_check(column: str, maximum: int) -> str:
    return (
        f"{column} IS NULL OR ({column} = btrim({column})"
        f" AND char_length({column}) BETWEEN 1 AND {maximum})"
    )


class ReturnRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One customer request to return lines of one delivered order."""

    __tablename__ = "return_requests"
    __table_args__ = (
        CheckConstraint(f"status IN ({_sql_list(ReturnStatus)})", name="valid_status"),
        CheckConstraint(f"reason IN ({_sql_list(ReturnReason)})", name="valid_reason"),
        CheckConstraint(_text_check("note", MAX_RETURN_NOTE_LENGTH), name="note_length"),
        CheckConstraint(
            _text_check("reject_reason", MAX_RETURN_NOTE_LENGTH), name="reject_reason_length"
        ),
        CheckConstraint(
            _text_check("admin_note", MAX_RETURN_ADMIN_NOTE_LENGTH), name="admin_note_length"
        ),
        CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL", name="rejected_has_reason"
        ),
        CheckConstraint(
            f"(status IN ({_sql_list(_DECIDED)})) = (decided_at IS NOT NULL)",
            name="decided_when_decided",
        ),
        CheckConstraint(
            f"received_at IS NULL OR status IN ({_sql_list(_RECEIVED)})",
            name="received_only_after_receipt",
        ),
        CheckConstraint(
            f"(status IN ({_sql_list(_INSPECTED)})) = (inspected_at IS NOT NULL)",
            name="inspected_when_inspected",
        ),
        CheckConstraint("refund_amount IS NULL OR refund_amount >= 0", name="refund_amount_range"),
        # The manual refund record (ORD-10): all of it exactly when refunded (as payments).
        CheckConstraint(
            "(status = 'refunded') = (refund_reference IS NOT NULL)"
            " AND (refund_reference IS NULL) = (refunded_at IS NULL)"
            " AND (refund_reference IS NULL) = (refunded_by IS NULL)"
            " AND (refund_reference IS NULL OR refund_amount > 0)",
            name="refund_record_complete",
        ),
        CheckConstraint(
            "refund_reference IS NULL OR (refund_reference = btrim(refund_reference)"
            f" AND refund_reference ~ '{REFUND_REFERENCE_PATTERN}')",
            name="refund_reference_format",
        ),
        Index("ix_return_requests_user_id_created_at", "user_id", "created_at"),
        Index("ix_return_requests_order_id", "order_id"),
        Index("ix_return_requests_status_created_at", "status", "created_at"),
    )

    order_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    # Copied from the locked order; an account deletion anonymizes the user, never deletes it.
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReturnStatus.REQUESTED, server_default="requested"
    )
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Shown to the customer when rejected; ``admin_note`` never is.
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refund_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    refund_reference: Mapped[str | None] = mapped_column(
        String(MAX_REFUND_REFERENCE_LENGTH), nullable=True, unique=True
    )
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class ReturnItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One order line of a request; the inspection fields are set together (ORD-09).

    ``condition``, ``accepted_quantity`` and ``refundable`` are all set at inspection: a line
    with nothing accepted still records its condition (usually ``damaged``).
    """

    __tablename__ = "return_items"
    __table_args__ = (
        CheckConstraint(f"quantity BETWEEN 1 AND {MAX_STOCK_QUANTITY}", name="quantity_range"),
        CheckConstraint(
            "accepted_quantity IS NULL OR accepted_quantity BETWEEN 0 AND quantity",
            name="accepted_quantity_range",
        ),
        CheckConstraint(
            f"condition IS NULL OR condition IN ({_sql_list(ItemCondition)})",
            name="valid_condition",
        ),
        CheckConstraint(
            "(condition IS NULL) = (accepted_quantity IS NULL)"
            " AND (condition IS NULL) = (refundable IS NULL)",
            name="inspection_complete",
        ),
        CheckConstraint("refund_amount IS NULL OR refund_amount >= 0", name="refund_amount_range"),
        CheckConstraint(
            "refundable IS TRUE OR COALESCE(refund_amount, 0) = 0", name="refund_only_if_refundable"
        ),
        CheckConstraint(
            "inventory_movement_id IS NULL OR condition = 'sellable'",
            name="restock_only_sellable",
        ),
        CheckConstraint(
            _text_check("inspection_note", MAX_RETURN_ADMIN_NOTE_LENGTH),
            name="inspection_note_length",
        ),
        UniqueConstraint("return_request_id", "order_item_id"),
        Index("ix_return_items_order_item_id", "order_item_id"),
    )

    return_request_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("return_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_item_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("order_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(10), nullable=True)
    refundable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    refund_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    inspection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The stock movement that put the sellable units back (ORD-09): at most once.
    inventory_movement_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("inventory_movements.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )


class ReturnStatusHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One status change of a request; a null actor is the system."""

    __tablename__ = "return_status_history"
    __table_args__ = (
        CheckConstraint(
            f"old_status IS NULL OR old_status IN ({_sql_list(ReturnStatus)})",
            name="valid_old_status",
        ),
        CheckConstraint(f"new_status IN ({_sql_list(ReturnStatus)})", name="valid_new_status"),
        CheckConstraint("old_status IS NULL OR old_status <> new_status", name="status_changes"),
        Index(
            "ix_return_status_history_return_request_id_created_at",
            "return_request_id",
            "created_at",
        ),
    )

    return_request_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("return_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
