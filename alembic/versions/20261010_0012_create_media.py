"""Create media and product_media; replace categories.image_url with image_media_id.

CAT-05, ADR-025, ADR-028. categories.image_url values are dropped (no API ever wrote a
production value); downgrade restores an empty image_url column.

Revision ID: 20261010_0012
Revises: 20261010_0011
Create Date: 2026-10-10 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261010_0012"
down_revision: str | None = "20261010_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literals copied from the models at the time of this migration (ADR-021).
IMAGE_TYPES_SQL = "'image/jpeg', 'image/png', 'image/webp'"
MAX_STORED_BYTES = 20_971_520
MAX_DIMENSION = 6000


def _uuid(name: str, *, nullable: bool) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _id() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _created_at() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "media",
        _id(),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        _uuid("created_by", nullable=True),
        _created_at(),
        sa.CheckConstraint(
            f"content_type IN ({IMAGE_TYPES_SQL})", name=op.f("ck_media_valid_content_type")
        ),
        sa.CheckConstraint(
            f"size_bytes BETWEEN 1 AND {MAX_STORED_BYTES}", name=op.f("ck_media_size_range")
        ),
        sa.CheckConstraint(
            f"width BETWEEN 1 AND {MAX_DIMENSION}", name=op.f("ck_media_width_range")
        ),
        sa.CheckConstraint(
            f"height BETWEEN 1 AND {MAX_DIMENSION}", name=op.f("ck_media_height_range")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_media_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_media_storage_key")),
    )
    op.create_index("ix_media_created_at", "media", ["created_at"])

    op.create_unique_constraint(
        "uq_product_variants_id_product_id", "product_variants", ["id", "product_id"]
    )
    op.create_table(
        "product_media",
        _id(),
        _uuid("product_id", nullable=False),
        _uuid("variant_id", nullable=True),
        _uuid("media_id", nullable=False),
        sa.Column("alt_text", sa.String(length=200), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_main", sa.Boolean(), server_default="false", nullable=False),
        _uuid("created_by", nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_product_media_display_order_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_media_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_product_media_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name=op.f("fk_product_media_media_id_media"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_product_media_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_media")),
        sa.UniqueConstraint("media_id", name=op.f("uq_product_media_media_id")),
    )
    op.create_index("ix_product_media_created_at", "product_media", ["created_at"])
    op.create_index(
        "ix_product_media_product_id_display_order",
        "product_media",
        ["product_id", "display_order"],
    )
    op.create_index(
        "uq_product_media_main",
        "product_media",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_main"),
    )

    op.drop_column("categories", "image_url")
    op.add_column("categories", _uuid("image_media_id", nullable=True))
    op.create_foreign_key(
        op.f("fk_categories_image_media_id_media"),
        "categories",
        "media",
        ["image_media_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_categories_image_media_id_media"), "categories", type_="foreignkey")
    op.drop_column("categories", "image_media_id")
    op.add_column("categories", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.drop_index("uq_product_media_main", table_name="product_media")
    op.drop_index("ix_product_media_product_id_display_order", table_name="product_media")
    op.drop_index("ix_product_media_created_at", table_name="product_media")
    op.drop_table("product_media")
    op.drop_constraint("uq_product_variants_id_product_id", "product_variants", type_="unique")
    op.drop_index("ix_media_created_at", table_name="media")
    op.drop_table("media")
