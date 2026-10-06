from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import INET
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
