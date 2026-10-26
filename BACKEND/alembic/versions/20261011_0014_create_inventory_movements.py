"""Create inventory_movements (INV-02, ADR-034).

Revision ID: 20261011_0014
Revises: 20261010_0013
Create Date: 2026-10-11 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261011_0014"
down_revision: str | None = "20261010_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literals copied from the models at the time of this migration (ADR-021).
MAX_STOCK_QUANTITY = 1_000_000
MAX_REASON_LENGTH = 500
MOVEMENT_TYPES_SQL = (
    "'increase', 'decrease', 'reserve', 'release', 'commit', 'correction', 'return'"
)
REFERENCE_TYPES_SQL = "'reservation', 'order', 'payment', 'return'"
MOVEMENT_DELTAS_SQL = (
    "(movement_type IN ('increase', 'return')"
    " AND total_after = total_before + quantity AND reserved_after = reserved_before)"
    " OR (movement_type = 'decrease'"
    " AND total_after = total_before - quantity AND reserved_after = reserved_before)"
    " OR (movement_type = 'correction'"
    " AND abs(total_after - total_before) = quantity AND reserved_after = reserved_before)"
    " OR (movement_type = 'reserve'"
    " AND reserved_after = reserved_before + quantity AND total_after = total_before)"
    " OR (movement_type = 'release'"
    " AND reserved_after = reserved_before - quantity AND total_after = total_before)"
    " OR (movement_type = 'commit' AND total_after = total_before - quantity"
    " AND reserved_after = reserved_before - quantity)"
)


def upgrade() -> None:
    op.create_table(
        "inventory_movements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("total_before", sa.Integer(), nullable=False),
        sa.Column("total_after", sa.Integer(), nullable=False),
        sa.Column("reserved_before", sa.Integer(), nullable=False),
        sa.Column("reserved_after", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(length=30), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.String(length=MAX_REASON_LENGTH), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"movement_type IN ({MOVEMENT_TYPES_SQL})",
            name=op.f("ck_inventory_movements_valid_movement_type"),
        ),
        sa.CheckConstraint(
            f"quantity BETWEEN 1 AND {MAX_STOCK_QUANTITY}",
            name=op.f("ck_inventory_movements_quantity_range"),
        ),
        sa.CheckConstraint(
            f"total_before BETWEEN 0 AND {MAX_STOCK_QUANTITY}"
            f" AND total_after BETWEEN 0 AND {MAX_STOCK_QUANTITY}",
            name=op.f("ck_inventory_movements_total_range"),
        ),
        sa.CheckConstraint(
            "reserved_before BETWEEN 0 AND total_before"
            " AND reserved_after BETWEEN 0 AND total_after",
            name=op.f("ck_inventory_movements_reserved_range"),
        ),
        sa.CheckConstraint(
            MOVEMENT_DELTAS_SQL, name=op.f("ck_inventory_movements_consistent_delta")
        ),
        sa.CheckConstraint(
            "(reference_type IS NULL) = (reference_id IS NULL)",
            name=op.f("ck_inventory_movements_reference_complete"),
        ),
        sa.CheckConstraint(
            f"reference_type IS NULL OR reference_type IN ({REFERENCE_TYPES_SQL})",
            name=op.f("ck_inventory_movements_valid_reference_type"),
        ),
        sa.CheckConstraint(
            "movement_type NOT IN ('reserve', 'release', 'commit') OR reference_id IS NOT NULL",
            name=op.f("ck_inventory_movements_reservation_has_reference"),
        ),
        sa.CheckConstraint(
            "movement_type NOT IN ('increase', 'decrease', 'correction') OR reason IS NOT NULL",
            name=op.f("ck_inventory_movements_manual_has_reason"),
        ),
        sa.CheckConstraint(
            f"reason IS NULL OR length(trim(reason)) BETWEEN 1 AND {MAX_REASON_LENGTH}",
            name=op.f("ck_inventory_movements_reason_length"),
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"],
            ["inventory_items.id"],
            name=op.f("fk_inventory_movements_inventory_item_id_inventory_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_inventory_movements_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_movements")),
    )
    op.create_index(
        op.f("ix_inventory_movements_created_at"), "inventory_movements", ["created_at"]
    )
    op.create_index(
        "ix_inventory_movements_item_created_at",
        "inventory_movements",
        ["inventory_item_id", "created_at", "id"],
    )
    op.create_index(
        "ix_inventory_movements_reference",
        "inventory_movements",
        ["reference_type", "reference_id"],
    )


def downgrade() -> None:
    op.drop_table("inventory_movements")
