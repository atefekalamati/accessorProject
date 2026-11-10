"""Create the static pages table (CNT-04, D40).

Revision ID: 20261110_0028
Revises: 20261026_0027
Create Date: 2026-11-10 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261110_0028"
down_revision: str | None = "20261026_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "static_pages",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
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
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 50000", name=op.f("ck_static_pages_body_length")
        ),
        sa.CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name=op.f("ck_static_pages_published_has_time"),
        ),
        sa.CheckConstraint("slug ~ '^[a-z0-9-]{3,120}$'", name=op.f("ck_static_pages_slug_format")),
        sa.CheckConstraint(
            "title = btrim(title) AND title <> ''", name=op.f("ck_static_pages_title_format")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published')", name=op.f("ck_static_pages_valid_status")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_static_pages_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_static_pages_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_static_pages")),
    )
    op.create_index(
        op.f("ix_static_pages_created_at"), "static_pages", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_static_pages_deleted_at"), "static_pages", ["deleted_at"], unique=False
    )
    op.create_index(
        "uq_static_pages_slug",
        "static_pages",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_static_pages_slug",
        table_name="static_pages",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_static_pages_deleted_at"), table_name="static_pages")
    op.drop_index(op.f("ix_static_pages_created_at"), table_name="static_pages")
    op.drop_table("static_pages")
