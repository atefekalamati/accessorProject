"""Create product_attributes and variant_options (color/size/model).

Revision ID: 20261010_0009
Revises: 20261010_0008
Create Date: 2026-10-10 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261010_0009"
down_revision: str | None = "20261010_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_attributes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_key", sa.String(length=50), nullable=False),
        sa.Column("attribute_value", sa.String(length=200), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "length(trim(attribute_key)) > 0",
            name=op.f("ck_product_attributes_attribute_key_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(attribute_value)) > 0",
            name=op.f("ck_product_attributes_attribute_value_not_blank"),
        ),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_product_attributes_display_order_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_attributes_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_attributes")),
        sa.UniqueConstraint(
            "product_id", "attribute_key", name=op.f("uq_product_attributes_product_id")
        ),
    )
    op.create_index("ix_product_attributes_attribute_key", "product_attributes", ["attribute_key"])

    op.create_table(
        "variant_options",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_key", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=50), nullable=False),
        sa.CheckConstraint(
            "option_key IN ('color', 'size', 'model')",
            name=op.f("ck_variant_options_valid_option_key"),
        ),
        sa.CheckConstraint(
            "length(trim(value)) > 0", name=op.f("ck_variant_options_value_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name=op.f("fk_variant_options_variant_id_product_variants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_variant_options")),
        sa.UniqueConstraint("variant_id", "option_key", name=op.f("uq_variant_options_variant_id")),
    )
    op.create_index(
        "ix_variant_options_option_key_value", "variant_options", ["option_key", "value"]
    )


def downgrade() -> None:
    op.drop_index("ix_variant_options_option_key_value", table_name="variant_options")
    op.drop_table("variant_options")
    op.drop_index("ix_product_attributes_attribute_key", table_name="product_attributes")
    op.drop_table("product_attributes")
