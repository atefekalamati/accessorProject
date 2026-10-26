"""Create warehouses (with the v1 default) and inventory_items (INV-01, ADR-005, ADR-029).

Revision ID: 20261010_0013
Revises: 20261010_0012
Create Date: 2026-10-10 00:00:00+00:00
"""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261010_0013"
down_revision: str | None = "20261010_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literals copied from the models at the time of this migration (ADR-021).
MAX_STOCK_QUANTITY = 1_000_000
WAREHOUSE_STATUSES_SQL = "'active', 'inactive'"
DEFAULT_WAREHOUSE_ID = uuid5(NAMESPACE_URL, "project-ak:default_warehouse")


def _uuid(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=False)


def _timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column(
            name,
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "warehouses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_warehouses_name_not_blank")),
        sa.CheckConstraint(
            "city IS NULL OR length(trim(city)) > 0", name=op.f("ck_warehouses_city_not_blank")
        ),
        sa.CheckConstraint(
            f"status IN ({WAREHOUSE_STATUSES_SQL})", name=op.f("ck_warehouses_valid_status")
        ),
        sa.CheckConstraint(
            "NOT is_default OR status = 'active'", name=op.f("ck_warehouses_default_is_active")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_warehouses")),
    )
    op.create_index("ix_warehouses_created_at", "warehouses", ["created_at"])
    op.create_index(
        "uq_warehouses_default",
        "warehouses",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.create_table(
        "inventory_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        _uuid("warehouse_id"),
        _uuid("product_id"),
        _uuid("variant_id"),
        sa.Column("total_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            f"total_quantity BETWEEN 0 AND {MAX_STOCK_QUANTITY}",
            name=op.f("ck_inventory_items_total_quantity_range"),
        ),
        sa.CheckConstraint(
            "reserved_quantity BETWEEN 0 AND total_quantity",
            name=op.f("ck_inventory_items_reserved_quantity_range"),
        ),
        sa.CheckConstraint(
            f"low_stock_threshold BETWEEN 0 AND {MAX_STOCK_QUANTITY}",
            name=op.f("ck_inventory_items_low_stock_threshold_range"),
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name=op.f("fk_inventory_items_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_inventory_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_inventory_items_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_items")),
        sa.UniqueConstraint(
            "variant_id", "warehouse_id", name=op.f("uq_inventory_items_variant_id")
        ),
    )
    op.create_index("ix_inventory_items_created_at", "inventory_items", ["created_at"])
    op.create_index("ix_inventory_items_product_id", "inventory_items", ["product_id"])

    # The single v1 warehouse (ADR-005); a fixed id keeps downgrade/upgrade repeatable.
    op.execute(
        sa.text(
            "INSERT INTO warehouses (id, name, is_default) VALUES (:id, 'Default warehouse', true)"
        ).bindparams(sa.bindparam("id", DEFAULT_WAREHOUSE_ID, type_=postgresql.UUID(as_uuid=True)))
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_items_product_id", table_name="inventory_items")
    op.drop_index("ix_inventory_items_created_at", table_name="inventory_items")
    op.drop_table("inventory_items")
    op.drop_index("uq_warehouses_default", table_name="warehouses")
    op.drop_index("ix_warehouses_created_at", table_name="warehouses")
    op.drop_table("warehouses")
