"""Create home page sections and their items (CNT-01, D36, D41).

Revision ID: 20261111_0031
Revises: 20261110_0030
Create Date: 2026-11-11 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261111_0031"
down_revision: str | None = "20261110_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literals copied from the models at the time of this migration (ADR-021).
_TYPES = "'hero', 'category_grid', 'product_carousel', 'benefits', 'editorial'"
_SOURCES = "'manual', 'newest', 'best_selling', 'discount', 'category'"
_TARGETS = "'product', 'category', 'page', 'none'"


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "home_sections",
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=300), nullable=True),
        sa.Column("layout_variant", sa.String(length=50), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_type", sa.String(length=16), server_default="none", nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("product_source", sa.String(length=16), nullable=True),
        sa.Column("source_category_id", sa.UUID(), nullable=True),
        sa.Column("product_limit", sa.Integer(), server_default="12", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(product_source IS NOT DISTINCT FROM 'category') = (source_category_id IS NOT NULL)",
            name=op.f("ck_home_sections_source_category_complete"),
        ),
        sa.CheckConstraint(
            "(target_type = 'none') = (target_id IS NULL)",
            name=op.f("ck_home_sections_target_complete"),
        ),
        sa.CheckConstraint(
            "(type = 'product_carousel') = (product_source IS NOT NULL)",
            name=op.f("ck_home_sections_carousel_source"),
        ),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_home_sections_display_order_non_negative")
        ),
        sa.CheckConstraint(
            "product_limit BETWEEN 1 AND 20", name=op.f("ck_home_sections_product_limit_range")
        ),
        sa.CheckConstraint(
            "title = btrim(title) AND title <> ''", name=op.f("ck_home_sections_title_format")
        ),
        sa.CheckConstraint(
            f"product_source IS NULL OR product_source IN ({_SOURCES})",
            name=op.f("ck_home_sections_valid_product_source"),
        ),
        sa.CheckConstraint(
            f"target_type IN ({_TARGETS})", name=op.f("ck_home_sections_valid_target_type")
        ),
        sa.CheckConstraint(f"type IN ({_TYPES})", name=op.f("ck_home_sections_valid_type")),
        sa.CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at",
            name=op.f("ck_home_sections_valid_window"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_home_sections_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_category_id"],
            ["categories.id"],
            name=op.f("fk_home_sections_source_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_home_sections_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_home_sections")),
    )
    op.create_index(
        op.f("ix_home_sections_created_at"), "home_sections", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_home_sections_deleted_at"), "home_sections", ["deleted_at"], unique=False
    )
    op.create_index(
        "uq_home_sections_display_order",
        "home_sections",
        ["display_order"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "home_section_items",
        sa.Column("section_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=True),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("title_override", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("image_media_id", sa.UUID(), nullable=True),
        sa.Column("icon_key", sa.String(length=50), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "body IS NULL OR char_length(body) BETWEEN 1 AND 2000",
            name=op.f("ck_home_section_items_body_length"),
        ),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_home_section_items_display_order_non_negative")
        ),
        sa.CheckConstraint(
            "num_nonnulls(product_id, category_id) <= 1",
            name=op.f("ck_home_section_items_one_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_home_section_items_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["image_media_id"],
            ["media.id"],
            name=op.f("fk_home_section_items_image_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_home_section_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["home_sections.id"],
            name=op.f("fk_home_section_items_section_id_home_sections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_home_section_items")),
    )
    op.create_index(
        op.f("ix_home_section_items_created_at"),
        "home_section_items",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_home_section_items_section_id_display_order",
        "home_section_items",
        ["section_id", "display_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_home_section_items_section_id_display_order", table_name="home_section_items")
    op.drop_index(op.f("ix_home_section_items_created_at"), table_name="home_section_items")
    op.drop_table("home_section_items")
    op.drop_index("uq_home_sections_display_order", table_name="home_sections")
    op.drop_index(op.f("ix_home_sections_deleted_at"), table_name="home_sections")
    op.drop_index(op.f("ix_home_sections_created_at"), table_name="home_sections")
    op.drop_table("home_sections")
