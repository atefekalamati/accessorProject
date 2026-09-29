from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("phone"),
        CheckConstraint("length(trim(phone)) > 0", name="phone_not_blank"),
        CheckConstraint(
            "status IN ('active', 'inactive', 'blocked')",
            name="valid_status",
        ),
        Index("ix_users_status", "status"),
    )

    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserStatus.ACTIVE, server_default="active"
    )
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
