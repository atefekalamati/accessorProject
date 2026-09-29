from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base
from app.db.models.common import UUIDPrimaryKeyMixin


class AppSetting(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        UniqueConstraint("key"),
        CheckConstraint("length(trim(key)) > 0", name="key_not_blank"),
    )

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
        index=True,
    )
