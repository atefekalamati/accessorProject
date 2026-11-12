"""Stored responses for the Idempotency-Key header (ORD-02, D34, ADR-046)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin

MAX_IDEMPOTENCY_KEY_LENGTH: Final = 255
MAX_IDEMPOTENCY_SCOPE_LENGTH: Final = 64


class IdempotencyKey(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The first successful response to one (user, scope, key) for 24 hours.

    Only successes are stored, so a request that failed (price changed, out of stock) can
    be retried with the same key. Removed with the user (the body is the user's own data).
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        CheckConstraint("key ~ '^[!-~]+$'", name="key_format"),
        CheckConstraint("scope ~ '^[a-z][a-z0-9_.]*$'", name="scope_format"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="request_hash_format"),
        CheckConstraint("response_status BETWEEN 200 AND 299", name="response_status_success"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        UniqueConstraint("user_id", "scope", "key"),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(String(MAX_IDEMPOTENCY_SCOPE_LENGTH), nullable=False)
    key: Mapped[str] = mapped_column(String(MAX_IDEMPOTENCY_KEY_LENGTH), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    response_body: Mapped[Any] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
