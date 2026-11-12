from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base
from app.db.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin
from app.shared.money import (
    DEFAULT_ROUNDING_MODE,
    DEFAULT_ROUNDING_STEP,
    MAX_PRICE_TOMAN,
    MAX_ROUNDING_STEP,
    MAX_TAX_RATE_BPS,
    RoundingMode,
)

CURRENCY_TOMAN: Final = "TOMAN"
ROUNDING_MODES_SQL: Final = ", ".join(f"'{mode.value}'" for mode in RoundingMode)
MAX_PRICE_REASON_LENGTH: Final = 500


def _price_range(column: str, *, nullable: bool) -> str:
    check = f"{column} BETWEEN 1 AND {MAX_PRICE_TOMAN}"
    return f"{column} IS NULL OR {check}" if nullable else check


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


class PriceHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One price change of a variant, both sides (PRC-03, PRD «قیمت و مالیات» ✓, ADR-035).

    Append-only. ``old_*`` are NULL for the first price (set when the variant is created).
    """

    __tablename__ = "price_history"
    __table_args__ = (
        CheckConstraint(_price_range("old_base_price", nullable=True), name="old_base_range"),
        CheckConstraint(_price_range("new_base_price", nullable=False), name="new_base_range"),
        CheckConstraint(_price_range("old_sale_price", nullable=True), name="old_sale_range"),
        CheckConstraint(_price_range("new_sale_price", nullable=True), name="new_sale_range"),
        CheckConstraint(
            "new_sale_price IS NULL OR new_sale_price <= new_base_price",
            name="new_sale_not_above_base",
        ),
        CheckConstraint(
            "new_sale_start_at IS NULL OR new_sale_end_at IS NULL"
            " OR new_sale_start_at < new_sale_end_at",
            name="new_sale_window_order",
        ),
        CheckConstraint(
            f"reason IS NULL OR length(trim(reason)) BETWEEN 1 AND {MAX_PRICE_REASON_LENGTH}",
            name="reason_length",
        ),
        # The variant must belong to the stored product.
        ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_price_history_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        Index("ix_price_history_product_id_seq", "product_id", "seq"),
        Index("ix_price_history_variant_id_seq", "variant_id", "seq"),
    )

    # Insertion order: listing order that does not depend on clock resolution.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)

    product_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    variant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    old_base_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    new_base_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    old_sale_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    new_sale_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    old_sale_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_sale_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    old_sale_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_sale_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(MAX_PRICE_REASON_LENGTH), nullable=True)
    changed_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
