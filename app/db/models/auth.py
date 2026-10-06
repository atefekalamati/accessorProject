from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.phone import MOBILE_E164_PATTERN
from app.db.base import Base
from app.db.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin


class OtpCode(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One issued OTP; only its HMAC is stored (app.modules.auth.otp.hash_otp_code)."""

    __tablename__ = "otp_codes"
    __table_args__ = (
        CheckConstraint(f"mobile ~ '{MOBILE_E164_PATTERN}'", name="mobile_format"),
        # A hex HMAC-SHA256 digest; rejects any attempt to store a plaintext code.
        CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'", name="code_hash_format"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        Index("ix_otp_codes_mobile_created_at", "mobile", "created_at"),
    )

    mobile: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)


class UserSession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One refresh token; rotation revokes it and issues a successor in the same family."""

    __tablename__ = "sessions"
    __table_args__ = (
        # A hex SHA-256 digest; rejects any attempt to store a raw refresh token.
        CheckConstraint("refresh_token_hash ~ '^[0-9a-f]{64}$'", name="refresh_token_hash_format"),
        UniqueConstraint("refresh_token_hash"),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_family_id", "family_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Shared by every rotation of one login; reuse of a revoked token revokes the family.
    family_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
