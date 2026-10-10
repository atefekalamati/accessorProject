from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base
from app.db.models.common import UUIDPrimaryKeyMixin
from app.shared.money import (
    DEFAULT_ROUNDING_MODE,
    DEFAULT_ROUNDING_STEP,
    MAX_ROUNDING_STEP,
    MAX_TAX_RATE_BPS,
    RoundingMode,
)

CURRENCY_TOMAN: Final = "TOMAN"
ROUNDING_MODES_SQL: Final = ", ".join(f"'{mode.value}'" for mode in RoundingMode)


class PricingSetting(UUIDPrimaryKeyMixin, Base):
    """Store-wide pricing policy; exactly one row, inserted by the migration (ADR-027)."""

    __tablename__ = "pricing_settings"
    __table_args__ = (
        CheckConstraint("singleton", name="singleton"),
        CheckConstraint(f"currency = '{CURRENCY_TOMAN}'", name="currency_toman"),
        CheckConstraint(
            f"default_tax_rate_bps BETWEEN 0 AND {MAX_TAX_RATE_BPS}", name="tax_rate_range"
        ),
        CheckConstraint(f"rounding_mode IN ({ROUNDING_MODES_SQL})", name="valid_rounding_mode"),
        CheckConstraint(
            f"rounding_step BETWEEN 1 AND {MAX_ROUNDING_STEP}", name="rounding_step_range"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    singleton: Mapped[bool] = mapped_column(
        Boolean, nullable=False, unique=True, default=True, server_default="true"
    )
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default=CURRENCY_TOMAN, server_default=CURRENCY_TOMAN
    )
    tax_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    default_tax_rate_bps: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rounding_mode: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=DEFAULT_ROUNDING_MODE,
        server_default=DEFAULT_ROUNDING_MODE.value,
    )
    rounding_step: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_ROUNDING_STEP,
        server_default=str(DEFAULT_ROUNDING_STEP),
    )
    # Bumped by every settings change (PRC-05); checkout fingerprints it with each
    # variant's price_version, since tax or rounding also change the final amount.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
