"""Add the colour swatch hex to variant_options (CAT-18, D42).

Revision ID: 20261026_0025
Revises: 20261019_0024
Create Date: 2026-10-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261026_0025"
down_revision: str | None = "20261019_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literal copied from the models at the time of this migration (ADR-021).
HEX_COLOR_PATTERN = "^#[0-9A-F]{6}$"


def upgrade() -> None:
    # Nullable: existing colours have no swatch until an admin sets one.
    op.add_column("variant_options", sa.Column("hex", sa.String(length=7), nullable=True))
    op.create_check_constraint(
        op.f("ck_variant_options_hex_only_on_color"),
        "variant_options",
        f"hex IS NULL OR (option_key = 'color' AND hex ~ '{HEX_COLOR_PATTERN}')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_variant_options_hex_only_on_color"), "variant_options", type_="check"
    )
    op.drop_column("variant_options", "hex")
