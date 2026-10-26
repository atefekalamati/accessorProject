"""Create inventory_reservations and inventory_reservation_items (INV-04, ADR-036).

Revision ID: 20261012_0016
Revises: 20261012_0015
Create Date: 2026-10-12 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261012_0016"
down_revision: str | None = "20261012_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literals copied from the models at the time of this migration (ADR-021).
MAX_STOCK_QUANTITY = 1_000_000
RESERVATION_STATUSES_SQL = "'active', 'released', 'committed', 'expired'"
ITEM_STATUSES_SQL = "'active', 'released', 'committed'"


def _id() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "inventory_reservations",
        _id(),
        _uuid("order_id", nullable=True),
        _uuid("cart_id", nullable=True),
        _uuid("user_id", nullable=True),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        *(
            sa.Column(
                name,
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
            for name in ("created_at", "updated_at")
        ),
        sa.CheckConstraint(
            f"status IN ({RESERVATION_STATUSES_SQL})",
            name=op.f("ck_inventory_reservations_valid_status"),
        ),
        sa.CheckConstraint(
            "(status = 'committed') = (committed_at IS NOT NULL)",
            name=op.f("ck_inventory_reservations_committed_has_time"),
        ),
        sa.CheckConstraint(
            "(status IN ('released', 'expired')) = (released_at IS NOT NULL)",
            name=op.f("ck_inventory_reservations_released_has_time"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_inventory_reservations_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_reservations")),
    )
    op.create_index(
        op.f("ix_inventory_reservations_created_at"), "inventory_reservations", ["created_at"]
    )
    op.create_index(
        "uq_inventory_reservations_live_order",
        "inventory_reservations",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'committed') AND order_id IS NOT NULL"),
    )
    op.create_index(
        "ix_inventory_reservations_status_expires_at",
        "inventory_reservations",
        ["status", "expires_at"],
    )

    op.create_table(
        "inventory_reservation_items",
        _id(),
        _uuid("reservation_id"),
        _uuid("inventory_item_id"),
        _uuid("product_id"),
        _uuid("variant_id"),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"quantity BETWEEN 1 AND {MAX_STOCK_QUANTITY}",
            name=op.f("ck_inventory_reservation_items_quantity_range"),
        ),
        sa.CheckConstraint(
            f"status IN ({ITEM_STATUSES_SQL})",
            name=op.f("ck_inventory_reservation_items_valid_status"),
        ),
        sa.CheckConstraint(
            "(status = 'released') = (released_at IS NOT NULL)",
            name=op.f("ck_inventory_reservation_items_released_has_time"),
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["inventory_reservations.id"],
            name="fk_inventory_reservation_items_reservation_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"],
            ["inventory_items.id"],
            name="fk_inventory_reservation_items_inventory_item_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_inventory_reservation_items_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_reservation_items")),
        sa.UniqueConstraint(
            "reservation_id",
            "inventory_item_id",
            name=op.f("uq_inventory_reservation_items_reservation_id"),
        ),
    )
    op.create_index(
        "ix_inventory_reservation_items_active_item",
        "inventory_reservation_items",
        ["inventory_item_id"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_inventory_reservation_items_reservation_id",
        "inventory_reservation_items",
        ["reservation_id"],
    )
    # Backstops on the INV-02 table: one reserve, one release-or-commit per item and
    # reservation.
    op.create_index(
        "uq_inventory_movements_reservation_reserve",
        "inventory_movements",
        ["inventory_item_id", "reference_id"],
        unique=True,
        postgresql_where=sa.text("reference_type = 'reservation' AND movement_type = 'reserve'"),
    )
    op.create_index(
        "uq_inventory_movements_reservation_close",
        "inventory_movements",
        ["inventory_item_id", "reference_id"],
        unique=True,
        postgresql_where=sa.text(
            "reference_type = 'reservation' AND movement_type IN ('release', 'commit')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_inventory_movements_reservation_close", table_name="inventory_movements")
    op.drop_index("uq_inventory_movements_reservation_reserve", table_name="inventory_movements")
    op.drop_table("inventory_reservation_items")
    op.drop_table("inventory_reservations")
