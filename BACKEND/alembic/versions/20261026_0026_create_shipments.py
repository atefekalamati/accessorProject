"""Create shipments: tracking code and shipping times of an order (ADM-02, ADR-053).

Revision ID: 20261026_0026
Revises: 20261026_0025
Create Date: 2026-10-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261026_0026"
down_revision: str | None = "20261026_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipments",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("tracking_code", sa.String(length=64), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
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
            "tracking_code IS NULL"
            " OR (tracking_code = btrim(tracking_code) AND tracking_code <> '')",
            name=op.f("ck_shipments_tracking_code_not_blank"),
        ),
        sa.CheckConstraint(
            "shipped_at IS NULL OR tracking_code IS NOT NULL",
            name=op.f("ck_shipments_shipped_has_code"),
        ),
        sa.CheckConstraint(
            "delivered_at IS NULL OR (shipped_at IS NOT NULL AND delivered_at >= shipped_at)",
            name=op.f("ck_shipments_delivered_after_shipped"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_shipments_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shipments")),
        sa.UniqueConstraint("order_id", name=op.f("uq_shipments_order_id")),
    )
    op.create_index(op.f("ix_shipments_created_at"), "shipments", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_shipments_created_at"), table_name="shipments")
    op.drop_table("shipments")
