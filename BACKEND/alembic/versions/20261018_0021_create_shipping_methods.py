"""Create shipping_methods (ADDR-02, ADR-045).

Revision ID: 20261018_0021
Revises: 20261018_0020
Create Date: 2026-10-18 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261018_0021"
down_revision: str | None = "20261018_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literal copied from the models at the time of this migration (ADR-021).
MAX_PRICE_TOMAN = 1_000_000_000_000


def _check(name: str, sql: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=op.f(f"ck_shipping_methods_{name}"))


def upgrade() -> None:
    op.create_table(
        "shipping_methods",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("cost", sa.BigInteger(), nullable=False),
        sa.Column("free_shipping_threshold", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
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
        _check("title_format", "title = btrim(title) AND title <> ''"),
        _check("cost_range", f"cost BETWEEN 0 AND {MAX_PRICE_TOMAN}"),
        _check(
            "free_shipping_threshold_range",
            "free_shipping_threshold IS NULL"
            f" OR free_shipping_threshold BETWEEN 1 AND {MAX_PRICE_TOMAN}",
        ),
        _check("display_order_non_negative", "display_order >= 0"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shipping_methods")),
    )
    op.create_index(op.f("ix_shipping_methods_created_at"), "shipping_methods", ["created_at"])
    op.create_index(op.f("ix_shipping_methods_deleted_at"), "shipping_methods", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("shipping_methods")
