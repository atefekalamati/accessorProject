"""Create return requests, their items and status history (ORD-08, ADR-063).

New tables only; no existing row changes. The schema already holds what review,
inspection with restock (ORD-09) and the manual refund (ORD-10) need.

Revision ID: 20261113_0034
Revises: 20261113_0033
Create Date: 2026-11-13 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261113_0034"
down_revision: str | None = "20261113_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "return_requests",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="requested", nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refund_amount", sa.BigInteger(), nullable=True),
        sa.Column("refund_reference", sa.String(length=100), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_by", sa.UUID(), nullable=True),
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
            "(status = 'refunded') = (refund_reference IS NOT NULL) AND (refund_reference IS "
            "NULL) = (refunded_at IS NULL) AND (refund_reference IS NULL) = (refunded_by IS "
            "NULL) AND (refund_reference IS NULL OR refund_amount > 0)",
            name=op.f("ck_return_requests_refund_record_complete"),
        ),
        sa.CheckConstraint(
            "(status IN ('approved', 'rejected', 'received', 'inspected', 'refund_required', "
            "'refunded', 'closed')) = (decided_at IS NOT NULL)",
            name=op.f("ck_return_requests_decided_when_decided"),
        ),
        sa.CheckConstraint(
            "(status IN ('inspected', 'refund_required', 'refunded', 'closed')) = (inspected_at "
            "IS NOT NULL)",
            name=op.f("ck_return_requests_inspected_when_inspected"),
        ),
        sa.CheckConstraint(
            "reason IN ('defective', 'wrong_item', 'not_as_described', 'changed_mind', 'other')",
            name=op.f("ck_return_requests_valid_reason"),
        ),
        sa.CheckConstraint(
            "received_at IS NULL OR status IN ('received', 'inspected', 'refund_required', "
            "'refunded', 'closed')",
            name=op.f("ck_return_requests_received_only_after_receipt"),
        ),
        sa.CheckConstraint(
            "refund_reference IS NULL OR (refund_reference = btrim(refund_reference) AND "
            "refund_reference ~ '^[^\\x01-\\x1f\\x7f-\\x9f\\u2028\\u2029]+$')",
            name=op.f("ck_return_requests_refund_reference_format"),
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL",
            name=op.f("ck_return_requests_rejected_has_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'cancelled', 'received', "
            "'inspected', 'refund_required', 'refunded', 'closed')",
            name=op.f("ck_return_requests_valid_status"),
        ),
        sa.CheckConstraint(
            "admin_note IS NULL OR (admin_note = btrim(admin_note) AND char_length(admin_note) "
            "BETWEEN 1 AND 2000)",
            name=op.f("ck_return_requests_admin_note_length"),
        ),
        sa.CheckConstraint(
            "note IS NULL OR (note = btrim(note) AND char_length(note) BETWEEN 1 AND 1000)",
            name=op.f("ck_return_requests_note_length"),
        ),
        sa.CheckConstraint(
            "refund_amount IS NULL OR refund_amount >= 0",
            name=op.f("ck_return_requests_refund_amount_range"),
        ),
        sa.CheckConstraint(
            "reject_reason IS NULL OR (reject_reason = btrim(reject_reason) AND "
            "char_length(reject_reason) BETWEEN 1 AND 1000)",
            name=op.f("ck_return_requests_reject_reason_length"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_return_requests_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_return_requests_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["refunded_by"],
            ["users.id"],
            name=op.f("fk_return_requests_refunded_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_return_requests_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_return_requests")),
        sa.UniqueConstraint("refund_reference", name=op.f("uq_return_requests_refund_reference")),
    )
    op.create_index(
        op.f("ix_return_requests_created_at"), "return_requests", ["created_at"], unique=False
    )
    op.create_index("ix_return_requests_order_id", "return_requests", ["order_id"], unique=False)
    op.create_index(
        "ix_return_requests_status_created_at",
        "return_requests",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_return_requests_user_id_created_at",
        "return_requests",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "return_status_history",
        sa.Column("return_request_id", sa.UUID(), nullable=False),
        sa.Column("old_status", sa.String(length=16), nullable=True),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "new_status IN ('requested', 'approved', 'rejected', 'cancelled', 'received', "
            "'inspected', 'refund_required', 'refunded', 'closed')",
            name=op.f("ck_return_status_history_valid_new_status"),
        ),
        sa.CheckConstraint(
            "old_status IS NULL OR old_status IN ('requested', 'approved', 'rejected', "
            "'cancelled', 'received', 'inspected', 'refund_required', 'refunded', 'closed')",
            name=op.f("ck_return_status_history_valid_old_status"),
        ),
        sa.CheckConstraint(
            "old_status IS NULL OR old_status <> new_status",
            name=op.f("ck_return_status_history_status_changes"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_return_status_history_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["return_request_id"],
            ["return_requests.id"],
            name=op.f("fk_return_status_history_return_request_id_return_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_return_status_history")),
    )
    op.create_index(
        op.f("ix_return_status_history_created_at"),
        "return_status_history",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_return_status_history_return_request_id_created_at",
        "return_status_history",
        ["return_request_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "return_items",
        sa.Column("return_request_id", sa.UUID(), nullable=False),
        sa.Column("order_item_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("accepted_quantity", sa.Integer(), nullable=True),
        sa.Column("condition", sa.String(length=10), nullable=True),
        sa.Column("refundable", sa.Boolean(), nullable=True),
        sa.Column("refund_amount", sa.BigInteger(), nullable=True),
        sa.Column("inspection_note", sa.Text(), nullable=True),
        sa.Column("inventory_movement_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "condition IS NULL OR condition IN ('sellable', 'damaged')",
            name=op.f("ck_return_items_valid_condition"),
        ),
        sa.CheckConstraint(
            "inventory_movement_id IS NULL OR condition = 'sellable'",
            name=op.f("ck_return_items_restock_only_sellable"),
        ),
        sa.CheckConstraint(
            "(condition IS NULL) = (accepted_quantity IS NULL) AND (condition IS NULL) = "
            "(refundable IS NULL)",
            name=op.f("ck_return_items_inspection_complete"),
        ),
        sa.CheckConstraint(
            "accepted_quantity IS NULL OR accepted_quantity BETWEEN 0 AND quantity",
            name=op.f("ck_return_items_accepted_quantity_range"),
        ),
        sa.CheckConstraint(
            "inspection_note IS NULL OR (inspection_note = btrim(inspection_note) AND "
            "char_length(inspection_note) BETWEEN 1 AND 2000)",
            name=op.f("ck_return_items_inspection_note_length"),
        ),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 1000000", name=op.f("ck_return_items_quantity_range")
        ),
        sa.CheckConstraint(
            "refund_amount IS NULL OR refund_amount >= 0",
            name=op.f("ck_return_items_refund_amount_range"),
        ),
        sa.CheckConstraint(
            "refundable IS TRUE OR COALESCE(refund_amount, 0) = 0",
            name=op.f("ck_return_items_refund_only_if_refundable"),
        ),
        sa.ForeignKeyConstraint(
            ["inventory_movement_id"],
            ["inventory_movements.id"],
            name=op.f("fk_return_items_inventory_movement_id_inventory_movements"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_items.id"],
            name=op.f("fk_return_items_order_item_id_order_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["return_request_id"],
            ["return_requests.id"],
            name=op.f("fk_return_items_return_request_id_return_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_return_items")),
        sa.UniqueConstraint(
            "inventory_movement_id", name=op.f("uq_return_items_inventory_movement_id")
        ),
        sa.UniqueConstraint(
            "return_request_id", "order_item_id", name=op.f("uq_return_items_return_request_id")
        ),
    )
    op.create_index(
        op.f("ix_return_items_created_at"), "return_items", ["created_at"], unique=False
    )
    op.create_index(
        "ix_return_items_order_item_id", "return_items", ["order_item_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_return_items_order_item_id", table_name="return_items")
    op.drop_index(op.f("ix_return_items_created_at"), table_name="return_items")
    op.drop_table("return_items")
    op.drop_index(
        "ix_return_status_history_return_request_id_created_at", table_name="return_status_history"
    )
    op.drop_index(op.f("ix_return_status_history_created_at"), table_name="return_status_history")
    op.drop_table("return_status_history")
    op.drop_index("ix_return_requests_user_id_created_at", table_name="return_requests")
    op.drop_index("ix_return_requests_status_created_at", table_name="return_requests")
    op.drop_index("ix_return_requests_order_id", table_name="return_requests")
    op.drop_index(op.f("ix_return_requests_created_at"), table_name="return_requests")
    op.drop_table("return_requests")
