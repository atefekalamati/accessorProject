from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.money import MAX_PRICE_TOMAN

# Public URL slug (PRD «جزئیات محصول» ✓): lowercase Latin letters, digits and '-', 3-120 chars.
# The API validates first; the CHECK is a backstop. A migration copies the literal it used.
SLUG_PATTERN = "^[a-z0-9-]{3,120}$"
# SKU (PRD «محصولات» ✓): stored normalized (trimmed, upper case); Latin letters, digits and '-'.
SKU_PATTERN = "^[A-Z0-9-]{1,64}$"


class VariantOptionKey(StrEnum):
    COLOR = "color"
    SIZE = "size"
    MODEL = "model"


class CategoryFilterType(StrEnum):
    CHECKBOX = "checkbox"
    RANGE = "range"
    COLOR = "color"
    SELECT = "select"


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
    """Purchasable unit. Stock lives only in InventoryItem (ADR-005); prices are Toman (ADR-027).

    Referenced by carts and orders, so it is only ever soft deleted.
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint(f"sku ~ '{SKU_PATTERN}'", name="sku_format"),
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
        # Prices are integer Toman (ADR-001, ADR-027); NULL base_price means "no price yet".
        CheckConstraint(
            f"base_price IS NULL OR base_price BETWEEN 1 AND {MAX_PRICE_TOMAN}",
            name="base_price_range",
        ),
        CheckConstraint(
            "sale_price IS NULL OR "
            "(base_price IS NOT NULL AND sale_price >= 1 AND sale_price <= base_price)",
            name="sale_price_range",
        ),
        CheckConstraint(
            "sale_start_at IS NULL OR sale_end_at IS NULL OR sale_start_at < sale_end_at",
            name="sale_window_order",
        ),
        CheckConstraint(
            "sale_price IS NOT NULL OR (sale_start_at IS NULL AND sale_end_at IS NULL)",
            name="sale_window_needs_sale_price",
        ),
        CheckConstraint("price_version >= 0", name="price_version_non_negative"),
        # Backstop for the PRD rule "a variant without a valid price cannot be active".
        CheckConstraint("NOT is_active OR base_price IS NOT NULL", name="active_needs_base_price"),
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
    base_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sale_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # The sale price applies only inside this window; an empty end is open (PRD).
    sale_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sale_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tax_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Bumped by every price change; checkout compares it to detect PRICE_CHANGED (ADR-027).
    price_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class ProductAttribute(UUIDPrimaryKeyMixin, Base):
    """Free-text spec pair shown on the product page; the admin replaces the whole set."""

    __tablename__ = "product_attributes"
    __table_args__ = (
        UniqueConstraint("product_id", "attribute_key"),
        CheckConstraint("length(trim(attribute_key)) > 0", name="attribute_key_not_blank"),
        CheckConstraint("length(trim(attribute_value)) > 0", name="attribute_value_not_blank"),
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
        Index("ix_product_attributes_attribute_key", "attribute_key"),
    )

    product_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attribute_key: Mapped[str] = mapped_column(String(50), nullable=False)
    attribute_value: Mapped[str] = mapped_column(String(200), nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class VariantOption(UUIDPrimaryKeyMixin, Base):
    """One value per key (color/size/model) per variant (PRD «محصولات» ✓)."""

    __tablename__ = "variant_options"
    __table_args__ = (
        UniqueConstraint("variant_id", "option_key"),
        CheckConstraint("option_key IN ('color', 'size', 'model')", name="valid_option_key"),
        CheckConstraint("length(trim(value)) > 0", name="value_not_blank"),
        Index("ix_variant_options_option_key_value", "option_key", "value"),
    )

    variant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    option_key: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(50), nullable=False)


class CategoryFilter(UUIDPrimaryKeyMixin, Base):
    """A filterable key shown on a category page; the admin replaces the whole set (CAT-09).

    ``attribute_key`` is a variant option key (color/size/model), a product attribute key,
    or ``price`` (range only).
    """

    __tablename__ = "category_filters"
    __table_args__ = (
        UniqueConstraint("category_id", "attribute_key"),
        CheckConstraint("length(trim(attribute_key)) > 0", name="attribute_key_not_blank"),
        CheckConstraint("length(trim(label)) > 0", name="label_not_blank"),
        CheckConstraint(
            "filter_type IN ('checkbox', 'range', 'color', 'select')", name="valid_filter_type"
        ),
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
    )

    category_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attribute_key: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    filter_type: Mapped[str] = mapped_column(String(20), nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
