"""Create categories: tree, unique slug among non-deleted rows, soft delete.

Revision ID: 20261010_0006
Revises: 20261009_0005
Create Date: 2026-10-10 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261010_0006"
down_revision: str | None = "20261009_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literal copy of app.db.models.catalog.SLUG_PATTERN at the time of this revision.
_SLUG_FORMAT = "slug ~ '^[a-z0-9-]{3,120}$'"


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon_key", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("seo_title", sa.String(length=200), nullable=True),
        sa.Column("seo_description", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(trim(title)) > 0", name=op.f("ck_categories_title_not_blank")),
        sa.CheckConstraint(_SLUG_FORMAT, name=op.f("ck_categories_slug_format")),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_categories_display_order_non_negative")
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_categories_parent_not_self")
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name=op.f("fk_categories_parent_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_index("ix_categories_created_at", "categories", ["created_at"])
    op.create_index("ix_categories_deleted_at", "categories", ["deleted_at"])
    op.create_index(
        "ix_categories_parent_id_display_order", "categories", ["parent_id", "display_order"]
    )
    op.create_index(
        "uq_categories_slug",
        "categories",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_categories_slug", table_name="categories")
    op.drop_index("ix_categories_parent_id_display_order", table_name="categories")
    op.drop_index("ix_categories_deleted_at", table_name="categories")
    op.drop_index("ix_categories_created_at", table_name="categories")
    op.drop_table("categories")
