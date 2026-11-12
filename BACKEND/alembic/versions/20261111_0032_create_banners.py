"""Create the banners table (CNT-03, ADR-028, D41).

Revision ID: 20261111_0032
Revises: 20261111_0031
Create Date: 2026-11-11 00:01:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261111_0032"
down_revision: str | None = "20261111_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "banners",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=300), nullable=True),
        sa.Column("image_media_id", sa.UUID(), nullable=False),
        sa.Column("mobile_image_media_id", sa.UUID(), nullable=True),
        sa.Column("target_type", sa.String(length=16), server_default="none", nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
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
            "(target_type = 'none') = (target_id IS NULL)", name=op.f("ck_banners_target_complete")
        ),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_banners_display_order_non_negative")
        ),
        sa.CheckConstraint(
            "title = btrim(title) AND title <> ''", name=op.f("ck_banners_title_format")
        ),
        sa.CheckConstraint(
            "target_type IN ('product', 'category', 'page', 'none')",
            name=op.f("ck_banners_valid_target_type"),
        ),
        sa.CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at",
            name=op.f("ck_banners_valid_window"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_banners_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["image_media_id"],
            ["media.id"],
            name=op.f("fk_banners_image_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mobile_image_media_id"],
            ["media.id"],
            name=op.f("fk_banners_mobile_image_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_banners_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_banners")),
    )
    op.create_index(op.f("ix_banners_created_at"), "banners", ["created_at"], unique=False)
    op.create_index(op.f("ix_banners_deleted_at"), "banners", ["deleted_at"], unique=False)
    op.create_index("ix_banners_display_order", "banners", ["display_order", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_banners_display_order", table_name="banners")
    op.drop_index(op.f("ix_banners_deleted_at"), table_name="banners")
    op.drop_index(op.f("ix_banners_created_at"), table_name="banners")
    op.drop_table("banners")
