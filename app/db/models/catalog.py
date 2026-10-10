from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Public URL slug (PRD «جزئیات محصول» ✓): lowercase Latin letters, digits and '-', 3-120 chars.
# The API validates first; the CHECK is a backstop. A migration copies the literal it used.
SLUG_PATTERN = "^[a-z0-9-]{3,120}$"
# SKU (PRD «محصولات» ✓): stored normalized (trimmed, upper case); Latin letters, digits and '-'.
SKU_PATTERN = "^[A-Z0-9-]{1,64}$"


class Category(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="slug_format"),
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
        # Deeper cycles (A → B → A) are rejected by the admin service (CAT-10).
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="parent_not_self"),
        Index("ix_categories_parent_id_display_order", "parent_id", "display_order"),
        # A soft-deleted category frees its slug (ADR-015).
        Index(
            "uq_categories_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    parent_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Public reads show only active, non-deleted categories (CAT-06).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ProductStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Product(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Referenced by variants, carts and orders, so it is only ever soft deleted (PRD «محصولات»)."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="slug_format"),
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="valid_status",
        ),
        # Set on the first publish and never cleared (sort key for «newest»).
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="published_has_published_at",
        ),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_status_published_at", "status", "published_at"),
        # A soft-deleted product frees its slug (ADR-015).
        Index(
            "uq_products_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    category_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProductStatus.DRAFT, server_default="draft"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ProductVariant(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Purchasable unit. Stock lives only in InventoryItem (ADR-005); price fields come in PRC-01.

    Referenced by carts and orders, so it is only ever soft deleted.
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint(f"sku ~ '{SKU_PATTERN}'", name="sku_format"),
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
        Index("ix_product_variants_product_id_display_order", "product_id", "display_order"),
        # A soft-deleted variant frees its SKU (ADR-015).
        Index(
            "uq_product_variants_sku",
            "sku",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    product_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Inactive by default: a variant without a valid price must not be active (PRD «محصولات»).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_purchasable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
