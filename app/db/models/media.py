from __future__ import annotations

from typing import Final
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import CreatedAtMixin, UUIDPrimaryKeyMixin
from app.shared.media import MAX_DIMENSION, MAX_STORED_BYTES, ImageType

IMAGE_TYPES_SQL: Final = ", ".join(f"'{item.value}'" for item in ImageType)


class Media(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A stored, re-encoded image (ADR-028). Its file lives in FileStorage under storage_key."""

    __tablename__ = "media"
    __table_args__ = (
        CheckConstraint(f"content_type IN ({IMAGE_TYPES_SQL})", name="valid_content_type"),
        CheckConstraint(f"size_bytes BETWEEN 1 AND {MAX_STORED_BYTES}", name="size_range"),
        CheckConstraint(f"width BETWEEN 1 AND {MAX_DIMENSION}", name="width_range"),
        CheckConstraint(f"height BETWEEN 1 AND {MAX_DIMENSION}", name="height_range"),
    )

    # Server-generated (uuid4 hex + extension); never derived from the uploaded filename.
    storage_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ProductMedia(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An image of a product, optionally tied to one of its variants (PRD «محصولات»)."""

    __tablename__ = "product_media"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
        # The variant must belong to the same product (PRD: otherwise 422 in CAT-11).
        ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_product_media_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        Index("ix_product_media_product_id_display_order", "product_id", "display_order"),
        # Exactly one main image per product.
        Index(
            "uq_product_media_main",
            "product_id",
            unique=True,
            postgresql_where=text("is_main"),
        ),
    )

    product_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    variant_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    # One usage per stored file: deleting the product image deletes the media and its file.
    media_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("media.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    alt_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_main: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
