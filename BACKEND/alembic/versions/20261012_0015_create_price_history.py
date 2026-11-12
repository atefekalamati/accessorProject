"""Create price_history (PRC-03, ADR-035).

Revision ID: 20261012_0015
Revises: 20261011_0014
Create Date: 2026-10-12 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261012_0015"
down_revision: str | None = "20261011_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literals copied from the models at the time of this migration (ADR-021).
MAX_PRICE_TOMAN = 1_000_000_000_000
MAX_REASON_LENGTH = 500


def _price_range(column: str, *, nullable: bool) -> str:
    check = f"{column} BETWEEN 1 AND {MAX_PRICE_TOMAN}"
    return f"{column} IS NULL OR {check}" if nullable else check


def _check(sql: str, name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=op.f(f"ck_price_history_{name}"))


def upgrade() -> None:
    op.create_table(
        "price_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_base_price", sa.BigInteger(), nullable=True),
        sa.Column("new_base_price", sa.BigInteger(), nullable=False),
        sa.Column("old_sale_price", sa.BigInteger(), nullable=True),
        sa.Column("new_sale_price", sa.BigInteger(), nullable=True),
        sa.Column("old_sale_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_sale_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("old_sale_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_sale_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=MAX_REASON_LENGTH), nullable=True),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        _check(_price_range("old_base_price", nullable=True), "old_base_range"),
        _check(_price_range("new_base_price", nullable=False), "new_base_range"),
        _check(_price_range("old_sale_price", nullable=True), "old_sale_range"),
        _check(_price_range("new_sale_price", nullable=True), "new_sale_range"),
        _check(
            "new_sale_price IS NULL OR new_sale_price <= new_base_price",
            "new_sale_not_above_base",
        ),
        _check(
            "new_sale_start_at IS NULL OR new_sale_end_at IS NULL"
            " OR new_sale_start_at < new_sale_end_at",
            "new_sale_window_order",
        ),
        _check(
            f"reason IS NULL OR length(trim(reason)) BETWEEN 1 AND {MAX_REASON_LENGTH}",
            "reason_length",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_price_history_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_price_history_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_price_history_changed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_history")),
    )
    op.create_index(op.f("ix_price_history_created_at"), "price_history", ["created_at"])
    op.create_index("ix_price_history_product_id_seq", "price_history", ["product_id", "seq"])
    op.create_index("ix_price_history_variant_id_seq", "price_history", ["variant_id", "seq"])


def downgrade() -> None:
    op.drop_table("price_history")
