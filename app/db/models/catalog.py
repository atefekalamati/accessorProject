from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Public URL slug (PRD «جزئیات محصول» ✓): lowercase Latin letters, digits and '-', 3-120 chars.
# The API validates first; the CHECK is a backstop. A migration copies the literal it used.
SLUG_PATTERN = "^[a-z0-9-]{3,120}$"


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
