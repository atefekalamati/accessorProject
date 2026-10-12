"""Shopping carts of users and guests (CART-01, ADR-039, ADR-040)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.inventory import MAX_STOCK_QUANTITY

# A cart holds at most this many lines (one per variant; ADR-039).
MAX_CART_LINES: Final = 50


class CartStatus(StrEnum):
    ACTIVE = "active"
    # A guest cart whose lines moved into the user's cart at login.
    MERGED = "merged"
    # A guest cart past expires_at.
    EXPIRED = "expired"


CART_STATUSES_SQL: Final = ", ".join(f"'{s.value}'" for s in CartStatus)


class Cart(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's cart (``user_id``) or a guest's cart (``token_hash``), never both.

    The guest token lives only in the ``cart_token`` cookie; the row keeps its SHA-256
    (D30). A user has at most one active cart.
    """

    __tablename__ = "carts"
    __table_args__ = (
        CheckConstraint(f"status IN ({CART_STATUSES_SQL})", name="valid_status"),
        CheckConstraint("(user_id IS NULL) <> (token_hash IS NULL)", name="one_owner"),
        # A hex SHA-256 digest; rejects any attempt to store a raw cart token.
        CheckConstraint(
            "token_hash IS NULL OR token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_format"
        ),
        # Guest carts expire; user carts do not.
        CheckConstraint("(token_hash IS NULL) = (expires_at IS NULL)", name="guest_expires"),
        UniqueConstraint("token_hash"),
        Index(
            "uq_carts_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active' AND user_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=CartStatus.ACTIVE, server_default="active"
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CartItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One variant in a cart; adding to a cart reserves nothing (ADR-007)."""

    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint(f"quantity BETWEEN 1 AND {MAX_STOCK_QUANTITY}", name="quantity_range"),
        # The variant must belong to the stored product.
        ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_cart_items_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("cart_id", "variant_id"),
        Index("ix_cart_items_variant_id", "variant_id"),
    )

    cart_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
