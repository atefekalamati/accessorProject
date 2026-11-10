"""Store content: static pages (CNT-04) and FAQ items (CNT-05); PRD ✓ sections, D40."""

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
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.catalog import SLUG_PATTERN
from app.db.models.common import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

MAX_PAGE_BODY_LENGTH: Final = 50_000
MAX_FAQ_ANSWER_LENGTH: Final = 5_000


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
