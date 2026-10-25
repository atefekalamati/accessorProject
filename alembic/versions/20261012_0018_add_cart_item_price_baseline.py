"""Add the per-line price baseline to cart_items (CART-03, ADR-041).

Revision ID: 20261012_0018
Revises: 20261012_0017
Create Date: 2026-10-12 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261012_0018"
down_revision: str | None = "20261012_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literal copied from the models at the time of this migration (ADR-021).
MAX_PRICE_TOMAN = 1_000_000_000_000

# Existing lines start from today's final unit price: the sale price inside its half-open
# window [start, end), else the base price; an unpriced variant gives 0.
_BACKFILL = """
UPDATE cart_items AS item
SET seen_unit_price = COALESCE(
        CASE
            WHEN variant.sale_price IS NOT NULL
                 AND (variant.sale_start_at IS NULL OR variant.sale_start_at <= now())
                 AND (variant.sale_end_at IS NULL OR now() < variant.sale_end_at)
            THEN variant.sale_price
            ELSE variant.base_price
        END,
        0
    ),
    seen_price_version = variant.price_version
FROM product_variants AS variant
WHERE variant.id = item.variant_id
"""


def upgrade() -> None:
    op.add_column("cart_items", sa.Column("seen_unit_price", sa.BigInteger(), nullable=True))
    op.add_column("cart_items", sa.Column("seen_price_version", sa.Integer(), nullable=True))
    op.execute(_BACKFILL)
    op.alter_column("cart_items", "seen_unit_price", nullable=False)
    op.alter_column("cart_items", "seen_price_version", nullable=False)
    op.create_check_constraint(
        op.f("ck_cart_items_seen_unit_price_range"),
        "cart_items",
        f"seen_unit_price BETWEEN 0 AND {MAX_PRICE_TOMAN}",
    )
    op.create_check_constraint(
        op.f("ck_cart_items_seen_price_version_non_negative"),
        "cart_items",
        "seen_price_version >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_cart_items_seen_price_version_non_negative"), "cart_items", type_="check"
    )
    op.drop_constraint(op.f("ck_cart_items_seen_unit_price_range"), "cart_items", type_="check")
    op.drop_column("cart_items", "seen_price_version")
    op.drop_column("cart_items", "seen_unit_price")
