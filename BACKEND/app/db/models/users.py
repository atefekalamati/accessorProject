from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.phone import MOBILE_E164_PATTERN
from app.db.base import Base
from app.db.models.common import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"phone ~ '{MOBILE_E164_PATTERN}'", name="phone_format"),
        CheckConstraint(
            "first_name IS NULL OR length(trim(first_name)) > 0",
            name="first_name_not_blank",
        ),
        CheckConstraint(
            "last_name IS NULL OR length(trim(last_name)) > 0",
            name="last_name_not_blank",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'blocked')",
            name="valid_status",
        ),
        Index("ix_users_status", "status"),
        # One active account per mobile; a soft-deleted account frees its number (ADR-015).
        Index(
            "uq_users_phone",
            "phone",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    # Stored only in normalized E.164 form (app.core.phone.normalize_phone); exposed as
    # `mobile` in the API.
    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserStatus.ACTIVE, server_default="active"
    )
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    mobile_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
