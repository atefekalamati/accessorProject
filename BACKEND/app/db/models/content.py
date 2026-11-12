"""Store content: pages, FAQ, contact messages, home sections (CNT-01..06); PRD ✓."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final
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
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.phone import MOBILE_E164_PATTERN
from app.db.base import Base
from app.db.models.catalog import SLUG_PATTERN
from app.db.models.common import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

MAX_PAGE_BODY_LENGTH: Final = 50_000
MAX_FAQ_ANSWER_LENGTH: Final = 5_000
MAX_CONTACT_TEXT_LENGTH: Final = 2_000
MAX_SECTION_TEXT_LENGTH: Final = 2_000
MAX_SECTION_PRODUCTS: Final = 20


class PageStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class StaticPage(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A Markdown page (``about``, ``terms``...); its slug never changes after creation."""

    __tablename__ = "static_pages"
    __table_args__ = (
        CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="slug_format"),
        CheckConstraint("title = btrim(title) AND title <> ''", name="title_format"),
        CheckConstraint("status IN ('draft', 'published')", name="valid_status"),
        CheckConstraint(
            f"char_length(body) BETWEEN 1 AND {MAX_PAGE_BODY_LENGTH}", name="body_length"
        ),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL", name="published_has_time"
        ),
        Index(
            "uq_static_pages_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PageStatus.DRAFT, server_default="draft"
    )
    # The first publication; kept when the page goes back to draft.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class FaqItem(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A question under a short group title; the answer is Markdown without raw HTML."""

    __tablename__ = "faq_items"
    __table_args__ = (
        CheckConstraint(
            "group_title = btrim(group_title) AND group_title <> ''", name="group_format"
        ),
        CheckConstraint("question = btrim(question) AND question <> ''", name="question_format"),
        CheckConstraint(
            f"char_length(answer) BETWEEN 1 AND {MAX_FAQ_ANSWER_LENGTH}", name="answer_length"
        ),
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
        Index("ix_faq_items_public_order", "display_order", "id"),
    )

    group_title: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ContactStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class ContactMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A message from the contact form; it holds personal data and is never logged."""

    __tablename__ = "contact_messages"
    __table_args__ = (
        CheckConstraint(f"phone ~ '{MOBILE_E164_PATTERN}'", name="phone_format"),
        CheckConstraint(
            f"char_length(message) BETWEEN 1 AND {MAX_CONTACT_TEXT_LENGTH}", name="message_length"
        ),
        CheckConstraint(
            f"internal_note IS NULL OR char_length(internal_note)"
            f" BETWEEN 1 AND {MAX_CONTACT_TEXT_LENGTH}",
            name="note_length",
        ),
        CheckConstraint("status IN ('new', 'in_progress', 'closed')", name="valid_status"),
        Index("ix_contact_messages_ip_created_at", "ip", "created_at"),
        Index("ix_contact_messages_phone_created_at", "phone", "created_at"),
        Index("ix_contact_messages_status_created_at", "status", "created_at"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ContactStatus.NEW, server_default="new"
    )
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    handled_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SectionType(StrEnum):
    HERO = "hero"
    CATEGORY_GRID = "category_grid"
    PRODUCT_CAROUSEL = "product_carousel"
    BENEFITS = "benefits"
    EDITORIAL = "editorial"


class ProductSource(StrEnum):
    MANUAL = "manual"
    NEWEST = "newest"
    BEST_SELLING = "best_selling"
    DISCOUNT = "discount"
    CATEGORY = "category"


class TargetType(StrEnum):
    """Internal destinations only (D41)."""

    PRODUCT = "product"
    CATEGORY = "category"
    PAGE = "page"
    NONE = "none"


def _sql_values(values: type[StrEnum]) -> str:
    return ", ".join(f"'{item.value}'" for item in values)


class HomeSection(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A block of the home page (CNT-01, PRD «صفحه اصلی» ✓, D36, D41).

    ``target_id`` points at a product, category or static page by ``target_type``; it has
    no foreign key, so the public read checks that the target is still public.
    """

    __tablename__ = "home_sections"
    __table_args__ = (
        CheckConstraint(f"type IN ({_sql_values(SectionType)})", name="valid_type"),
        CheckConstraint("title = btrim(title) AND title <> ''", name="title_format"),
        CheckConstraint(f"target_type IN ({_sql_values(TargetType)})", name="valid_target_type"),
        CheckConstraint("(target_type = 'none') = (target_id IS NULL)", name="target_complete"),
        CheckConstraint(
            f"product_source IS NULL OR product_source IN ({_sql_values(ProductSource)})",
            name="valid_product_source",
        ),
        CheckConstraint(
            "(type = 'product_carousel') = (product_source IS NOT NULL)", name="carousel_source"
        ),
        CheckConstraint(
            "(product_source IS NOT DISTINCT FROM 'category') = (source_category_id IS NOT NULL)",
            name="source_category_complete",
        ),
        CheckConstraint(
            f"product_limit BETWEEN 1 AND {MAX_SECTION_PRODUCTS}", name="product_limit_range"
        ),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at", name="valid_window"
        ),
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
        Index(
            "uq_home_sections_display_order",
            "display_order",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    layout_variant: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Shown within [starts_at, ends_at); an empty end is open.
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TargetType.NONE, server_default="none"
    )
    target_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    # Product carousels only; manual items come first, the source fills the rest.
    product_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_category_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    product_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=12, server_default="12"
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class HomeSectionItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One entry of a section: a product, a category, or text with an icon or image."""

    __tablename__ = "home_section_items"
    __table_args__ = (
        CheckConstraint("num_nonnulls(product_id, category_id) <= 1", name="one_reference"),
        CheckConstraint(
            f"body IS NULL OR char_length(body) BETWEEN 1 AND {MAX_SECTION_TEXT_LENGTH}",
            name="body_length",
        ),
        CheckConstraint("display_order >= 0", name="display_order_non_negative"),
        Index("ix_home_section_items_section_id_display_order", "section_id", "display_order"),
    )

    section_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("home_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )
    category_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    title_override: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_media_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("media.id", ondelete="RESTRICT"), nullable=True
    )
    icon_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
