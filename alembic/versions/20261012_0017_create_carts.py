"""Create carts and cart_items (CART-01, ADR-039, ADR-040).

Revision ID: 20261012_0017
Revises: 20261012_0016
Create Date: 2026-10-12 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261012_0017"
down_revision: str | None = "20261012_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literals copied from the models at the time of this migration (ADR-021).
MAX_STOCK_QUANTITY = 1_000_000
CART_STATUSES_SQL = "'active', 'merged', 'expired'"


def _id() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _timestamps() -> list[sa.Column[object]]:
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
        "carts",
        _id(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(f"status IN ({CART_STATUSES_SQL})", name=op.f("ck_carts_valid_status")),
        sa.CheckConstraint(
            "(user_id IS NULL) <> (token_hash IS NULL)", name=op.f("ck_carts_one_owner")
        ),
        sa.CheckConstraint(
            "token_hash IS NULL OR token_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_carts_token_hash_format"),
        ),
        sa.CheckConstraint(
            "(token_hash IS NULL) = (expires_at IS NULL)", name=op.f("ck_carts_guest_expires")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_carts_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_carts")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_carts_token_hash")),
    )
    op.create_index(op.f("ix_carts_created_at"), "carts", ["created_at"])
    op.create_index(
        "uq_carts_active_user",
        "carts",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND user_id IS NOT NULL"),
    )

    op.create_table(
        "cart_items",
        _id(),
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            f"quantity BETWEEN 1 AND {MAX_STOCK_QUANTITY}",
            name=op.f("ck_cart_items_quantity_range"),
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"], ["carts.id"], name=op.f("fk_cart_items_cart_id_carts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_cart_items_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cart_items")),
        sa.UniqueConstraint("cart_id", "variant_id", name=op.f("uq_cart_items_cart_id")),
    )
    op.create_index(op.f("ix_cart_items_created_at"), "cart_items", ["created_at"])
    op.create_index("ix_cart_items_variant_id", "cart_items", ["variant_id"])


def downgrade() -> None:
    op.drop_index("ix_cart_items_variant_id", table_name="cart_items")
    op.drop_index(op.f("ix_cart_items_created_at"), table_name="cart_items")
    op.drop_table("cart_items")
    op.drop_index("uq_carts_active_user", table_name="carts")
    op.drop_index(op.f("ix_carts_created_at"), table_name="carts")
    op.drop_table("carts")
