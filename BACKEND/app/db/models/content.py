"""Store content: static pages (CNT-04, PRD «درباره برند» ✓, D40)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.catalog import SLUG_PATTERN
from app.db.models.common import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

MAX_PAGE_BODY_LENGTH: Final = 50_000


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
