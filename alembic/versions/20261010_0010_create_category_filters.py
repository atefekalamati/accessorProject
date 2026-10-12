"""Create category_filters.

Revision ID: 20261010_0010
Revises: 20261010_0009
Create Date: 2026-10-10 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261010_0010"
down_revision: str | None = "20261010_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "category_filters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_key", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("filter_type", sa.String(length=20), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint(
            "length(trim(attribute_key)) > 0",
            name=op.f("ck_category_filters_attribute_key_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(label)) > 0", name=op.f("ck_category_filters_label_not_blank")
        ),
        sa.CheckConstraint(
            "filter_type IN ('checkbox', 'range', 'color', 'select')",
            name=op.f("ck_category_filters_valid_filter_type"),
        ),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_category_filters_display_order_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_category_filters_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_category_filters")),
        sa.UniqueConstraint(
            "category_id", "attribute_key", name=op.f("uq_category_filters_category_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("category_filters")
