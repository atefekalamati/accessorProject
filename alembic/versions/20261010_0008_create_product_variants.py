"""Create product_variants: unique SKU among non-deleted rows, no stock column.

Revision ID: 20261010_0008
Revises: 20261010_0007
Create Date: 2026-10-10 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261010_0008"
down_revision: str | None = "20261010_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literal copy of app.db.models.catalog.SKU_PATTERN at the time of this revision.
_SKU_FORMAT = "sku ~ '^[A-Z0-9-]{1,64}$'"


def upgrade() -> None:
    op.create_table(
        "product_variants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_purchasable", sa.Boolean(), server_default="true", nullable=False),
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
        sa.CheckConstraint(_SKU_FORMAT, name=op.f("ck_product_variants_sku_format")),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_product_variants_display_order_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_variants_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_variants")),
    )
    op.create_index("ix_product_variants_created_at", "product_variants", ["created_at"])
    op.create_index("ix_product_variants_deleted_at", "product_variants", ["deleted_at"])
    op.create_index(
        "ix_product_variants_product_id_display_order",
        "product_variants",
        ["product_id", "display_order"],
    )
    op.create_index(
        "uq_product_variants_sku",
        "product_variants",
        ["sku"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_product_variants_sku", table_name="product_variants")
    op.drop_index("ix_product_variants_product_id_display_order", table_name="product_variants")
    op.drop_index("ix_product_variants_deleted_at", table_name="product_variants")
    op.drop_index("ix_product_variants_created_at", table_name="product_variants")
    op.drop_table("product_variants")
