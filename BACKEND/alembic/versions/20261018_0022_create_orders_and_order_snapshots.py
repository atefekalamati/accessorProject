"""Create orders, order_items, order snapshots and status history; reference orders from
reservations and redemptions (ORD-01, ADR-046).

Revision ID: 20261018_0022
Revises: 20261018_0021
Create Date: 2026-10-18 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261018_0022"
down_revision: str | None = "20261018_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# CHECK literals are copied from the models at the time of this migration (ADR-021).


def _refuse_orphans(table: str) -> None:
    """Never delete data: stop with a clear error if a row points at no order."""
    orphans = (
        op.get_bind()
        .execute(sa.text(f"SELECT count(*) FROM {table} WHERE order_id IS NOT NULL"))
        .scalar_one()
    )
    if orphans:
        raise RuntimeError(
            f"{table} has {orphans} row(s) with an order_id but no orders table existed;"
            " remove them by hand before upgrading (ORD-01)"
        )


def upgrade() -> None:
    _refuse_orphans("inventory_reservations")
    _refuse_orphans("discount_redemptions")
    # Global, never reset yearly; gaps from rolled back orders are fine.
    op.execute(sa.schema.CreateSequence(sa.Sequence("order_number_seq")))
    op.create_table(
        "orders",
        sa.Column("order_number", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending_payment", nullable=False),
        sa.Column("payment_status", sa.String(length=16), server_default="unpaid", nullable=False),
        sa.Column(
            "shipment_status", sa.String(length=16), server_default="not_shipped", nullable=False
        ),
        sa.Column("cancel_reason", sa.String(length=16), nullable=True),
        sa.Column("subtotal", sa.BigInteger(), nullable=False),
        sa.Column("product_discount_total", sa.BigInteger(), nullable=False),
        sa.Column("discount_code_amount", sa.BigInteger(), nullable=False),
        sa.Column("tax_amount", sa.BigInteger(), nullable=False),
        sa.Column("shipping_amount", sa.BigInteger(), nullable=False),
        sa.Column("grand_total", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="TOMAN", nullable=False),
        sa.Column("discount_code_id", sa.UUID(), nullable=True),
        sa.Column("discount_code", sa.String(length=32), nullable=True),
        sa.Column("shipping_method_id", sa.UUID(), nullable=False),
        sa.Column("shipping_method_title", sa.String(length=100), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancel_reason IS NOT NULL)",
            name=op.f("ck_orders_cancelled_has_reason"),
        ),
        sa.CheckConstraint(
            "cancel_reason IS NULL OR cancel_reason IN ('customer', 'expired', 'admin')",
            name=op.f("ck_orders_valid_cancel_reason"),
        ),
        sa.CheckConstraint("currency = 'TOMAN'", name=op.f("ck_orders_currency_toman")),
        sa.CheckConstraint(
            "order_number ~ '^ORD-[0-9]{4}-[0-9]{6,}$'", name=op.f("ck_orders_order_number_format")
        ),
        sa.CheckConstraint(
            "payment_status IN ('unpaid', 'pending', 'paid', 'failed', 'refund_required')",
            name=op.f("ck_orders_valid_payment_status"),
        ),
        sa.CheckConstraint("phone ~ '^\\+989[0-9]{9}$'", name=op.f("ck_orders_phone_format")),
        sa.CheckConstraint(
            "shipment_status IN ('not_shipped', 'preparing', 'shipped', 'delivered')",
            name=op.f("ck_orders_valid_shipment_status"),
        ),
        sa.CheckConstraint(
            "shipping_method_title = btrim(shipping_method_title) AND shipping_method_title <> ''",
            name=op.f("ck_orders_shipping_method_title_format"),
        ),
        sa.CheckConstraint(
            "status IN ('pending_payment', 'confirmed', 'completed', 'cancelled')",
            name=op.f("ck_orders_valid_status"),
        ),
        sa.CheckConstraint(
            "order_number !~ '^ORD-[0-9]{4}-[0-9]{6,}$'"
            " OR substring(order_number from 5 for 4)::int"
            " = extract(year from created_at AT TIME ZONE 'UTC')::int",
            name=op.f("ck_orders_order_number_year"),
        ),
        sa.CheckConstraint(
            "(discount_code_id IS NULL) = (discount_code IS NULL)",
            name=op.f("ck_orders_code_snapshot_pair"),
        ),
        sa.CheckConstraint(
            "discount_code_id IS NOT NULL OR discount_code_amount = 0",
            name=op.f("ck_orders_code_amount_needs_code"),
        ),
        sa.CheckConstraint(
            "grand_total::numeric = subtotal::numeric - product_discount_total"
            " - discount_code_amount + tax_amount + shipping_amount",
            name=op.f("ck_orders_grand_total_sum"),
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND product_discount_total >= 0 AND discount_code_amount >= 0"
            " AND tax_amount >= 0 AND shipping_amount >= 0 AND grand_total >= 0",
            name=op.f("ck_orders_amounts_non_negative"),
        ),
        sa.CheckConstraint(
            "subtotal::numeric - product_discount_total - discount_code_amount >= 0",
            name=op.f("ck_orders_discounts_within_subtotal"),
        ),
        sa.ForeignKeyConstraint(
            ["discount_code_id"],
            ["discount_codes.id"],
            name=op.f("fk_orders_discount_code_id_discount_codes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shipping_method_id"],
            ["shipping_methods.id"],
            name=op.f("fk_orders_shipping_method_id_shipping_methods"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_orders_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("order_number", name=op.f("uq_orders_order_number")),
    )
    op.create_index(op.f("ix_orders_created_at"), "orders", ["created_at"], unique=False)
    op.create_index("ix_orders_payment_status", "orders", ["payment_status"], unique=False)
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)
    op.create_index(
        "ix_orders_user_id_created_at", "orders", ["user_id", "created_at"], unique=False
    )
    op.create_table(
        "order_addresses",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("source_address_id", sa.UUID(), nullable=True),
        sa.Column("recipient_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("province", sa.String(length=100), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("address_line", sa.String(length=500), nullable=False),
        sa.Column("plaque", sa.String(length=20), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.CheckConstraint(
            "phone ~ '^\\+989[0-9]{9}$'", name=op.f("ck_order_addresses_phone_format")
        ),
        sa.CheckConstraint(
            "postal_code ~ '^[0-9]{10}$'", name=op.f("ck_order_addresses_postal_code_format")
        ),
        sa.CheckConstraint(
            "length(btrim(recipient_name)) > 0",
            name=op.f("ck_order_addresses_recipient_name_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_addresses_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("order_id", name=op.f("pk_order_addresses")),
    )
    op.create_table(
        "order_price_snapshots",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("pricing_version", sa.Integer(), nullable=False),
        sa.Column("tax_enabled", sa.Boolean(), nullable=False),
        sa.Column("tax_rate_bps", sa.Integer(), nullable=False),
        sa.Column("rounding_mode", sa.String(length=10), nullable=False),
        sa.Column("rounding_step", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipping_method_cost", sa.BigInteger(), nullable=False),
        sa.Column("shipping_free_threshold", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_order_price_snapshots_fingerprint_format"),
        ),
        sa.CheckConstraint(
            "rounding_mode IN ('up', 'down', 'nearest')",
            name=op.f("ck_order_price_snapshots_valid_rounding_mode"),
        ),
        sa.CheckConstraint(
            "pricing_version >= 1", name=op.f("ck_order_price_snapshots_pricing_version_positive")
        ),
        sa.CheckConstraint(
            "rounding_step BETWEEN 1 AND 1000000",
            name=op.f("ck_order_price_snapshots_rounding_step_range"),
        ),
        sa.CheckConstraint(
            "shipping_free_threshold IS NULL"
            " OR shipping_free_threshold BETWEEN 1 AND 1000000000000",
            name=op.f("ck_order_price_snapshots_shipping_free_threshold_range"),
        ),
        sa.CheckConstraint(
            "shipping_method_cost BETWEEN 0 AND 1000000000000",
            name=op.f("ck_order_price_snapshots_shipping_method_cost_range"),
        ),
        sa.CheckConstraint(
            "tax_rate_bps BETWEEN 0 AND 10000", name=op.f("ck_order_price_snapshots_tax_rate_range")
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_price_snapshots_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("order_id", name=op.f("pk_order_price_snapshots")),
    )
    op.create_table(
        "order_status_history",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.String(length=10), nullable=False),
        sa.Column("old_status", sa.String(length=16), nullable=True),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "field IN ('order', 'payment', 'shipment')",
            name=op.f("ck_order_status_history_valid_field"),
        ),
        sa.CheckConstraint(
            "old_status IS NULL OR old_status <> new_status",
            name=op.f("ck_order_status_history_status_changes"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_order_status_history_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_status_history_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_status_history")),
    )
    op.create_index(
        op.f("ix_order_status_history_created_at"),
        "order_status_history",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_order_status_history_order_id_created_at",
        "order_status_history",
        ["order_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "order_items",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=False),
        sa.Column("product_title", sa.String(length=200), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("variant_label", sa.String(length=300), server_default="", nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.BigInteger(), nullable=False),
        sa.Column("unit_final_price", sa.BigInteger(), nullable=False),
        sa.Column("subtotal", sa.BigInteger(), nullable=False),
        sa.Column("product_discount", sa.BigInteger(), nullable=False),
        sa.Column("code_discount", sa.BigInteger(), nullable=False),
        sa.Column("discount_amount", sa.BigInteger(), nullable=False),
        sa.Column("tax_amount", sa.BigInteger(), nullable=False),
        sa.Column("final_line_total", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "product_title = btrim(product_title) AND product_title <> ''",
            name=op.f("ck_order_items_product_title_format"),
        ),
        sa.CheckConstraint(
            "discount_amount::numeric = product_discount::numeric + code_discount",
            name=op.f("ck_order_items_discount_amount_sum"),
        ),
        sa.CheckConstraint(
            "final_line_total::numeric = subtotal::numeric - discount_amount + tax_amount",
            name=op.f("ck_order_items_final_line_total_sum"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_order_items_position_non_negative")),
        sa.CheckConstraint(
            "product_discount >= 0 AND code_discount >= 0 AND tax_amount >= 0"
            " AND final_line_total >= 0",
            name=op.f("ck_order_items_amounts_non_negative"),
        ),
        sa.CheckConstraint(
            "product_discount::numeric = (unit_price::numeric - unit_final_price) * quantity",
            name=op.f("ck_order_items_product_discount_product"),
        ),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 1000000", name=op.f("ck_order_items_quantity_range")
        ),
        sa.CheckConstraint(
            "subtotal::numeric - discount_amount >= 0",
            name=op.f("ck_order_items_discount_within_subtotal"),
        ),
        sa.CheckConstraint(
            "subtotal::numeric = unit_price::numeric * quantity",
            name=op.f("ck_order_items_subtotal_product"),
        ),
        sa.CheckConstraint(
            "unit_price BETWEEN 0 AND 1000000000000 AND unit_final_price BETWEEN 0 AND unit_price",
            name=op.f("ck_order_items_unit_prices_range"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_items_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_order_items_variant_id_product_variants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
        sa.UniqueConstraint("order_id", "position", name=op.f("uq_order_items_order_id")),
    )
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"], unique=False)
    op.create_index("ix_order_items_variant_id", "order_items", ["variant_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_discount_redemptions_order_id_orders"),
        "discount_redemptions",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_inventory_reservations_order_id_orders"),
        "inventory_reservations",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_inventory_reservations_order_id_orders"),
        "inventory_reservations",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_discount_redemptions_order_id_orders"), "discount_redemptions", type_="foreignkey"
    )
    op.drop_index("ix_order_items_variant_id", table_name="order_items")
    op.drop_index("ix_order_items_product_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_order_status_history_order_id_created_at", table_name="order_status_history")
    op.drop_index(op.f("ix_order_status_history_created_at"), table_name="order_status_history")
    op.drop_table("order_status_history")
    op.drop_table("order_price_snapshots")
    op.drop_table("order_addresses")
    op.drop_index("ix_orders_user_id_created_at", table_name="orders")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_payment_status", table_name="orders")
    op.drop_index(op.f("ix_orders_created_at"), table_name="orders")
    op.drop_table("orders")
    op.execute(sa.schema.DropSequence(sa.Sequence("order_number_seq")))
