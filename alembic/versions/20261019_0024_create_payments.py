"""Create payments, payment_events and fake_gateway_sessions (PAY-01, ADR-049, ADR-051).

Revision ID: 20261019_0024
Revises: 20261018_0023
Create Date: 2026-10-19 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261019_0024"
down_revision: str | None = "20261018_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fake_gateway_sessions",
        sa.Column("reference", sa.String(length=128), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("amount_rial", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("paid_amount_rial", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'paid') = (paid_amount_rial IS NOT NULL)",
            name=op.f("ck_fake_gateway_sessions_paid_has_amount"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'failed')",
            name=op.f("ck_fake_gateway_sessions_valid_status"),
        ),
        sa.CheckConstraint(
            "amount_rial > 0", name=op.f("ck_fake_gateway_sessions_amount_positive")
        ),
        sa.PrimaryKeyConstraint("reference", name=op.f("pk_fake_gateway_sessions")),
    )
    op.create_index(
        op.f("ix_fake_gateway_sessions_created_at"),
        "fake_gateway_sessions",
        ["created_at"],
        unique=False,
    )
    op.create_table(
        "payments",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("gateway", sa.String(length=32), nullable=False),
        sa.Column("gateway_reference", sa.String(length=128), nullable=True),
        sa.Column("redirect_url", sa.String(length=2048), nullable=True),
        sa.Column("gateway_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("paid_amount", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.Column("raw_event", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
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
            "(status IN ('failed', 'refund_required')) = (failure_reason IS NOT NULL)",
            name=op.f("ck_payments_closed_has_reason"),
        ),
        sa.CheckConstraint(
            "gateway ~ '^[a-z][a-z0-9_]*$'", name=op.f("ck_payments_gateway_format")
        ),
        sa.CheckConstraint(
            "gateway_reference IS NULL OR gateway_reference ~ '^[!-~]+$'",
            name=op.f("ck_payments_gateway_reference_format"),
        ),
        sa.CheckConstraint(
            "paid_at IS NULL OR status IN ('paid', 'refund_required')",
            name=op.f("ck_payments_paid_at_when_paid"),
        ),
        sa.CheckConstraint(
            "status <> 'paid' OR paid_at IS NOT NULL", name=op.f("ck_payments_paid_has_paid_at")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'refund_required')",
            name=op.f("ck_payments_valid_status"),
        ),
        sa.CheckConstraint(
            "(redirect_url IS NULL) = (gateway_reference IS NULL)",
            name=op.f("ck_payments_redirect_with_reference"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount_positive")),
        sa.CheckConstraint(
            "status <> 'refund_required' OR paid_at IS NOT NULL",
            name=op.f("ck_payments_refund_was_paid"),
        ),
        sa.CheckConstraint(
            "paid_amount IS NULL OR paid_amount >= 0", name=op.f("ck_payments_paid_amount_range")
        ),
        sa.CheckConstraint(
            "(gateway_expires_at IS NULL) = (gateway_reference IS NULL)",
            name=op.f("ck_payments_expires_with_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_payments_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(op.f("ix_payments_created_at"), "payments", ["created_at"], unique=False)
    op.create_index("ix_payments_order_id", "payments", ["order_id"], unique=False)
    op.create_index(
        "ix_payments_pending_created_at",
        "payments",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_payments_gateway_reference",
        "payments",
        ["gateway", "gateway_reference"],
        unique=True,
        postgresql_where=sa.text("gateway_reference IS NOT NULL"),
    )
    op.create_index(
        "uq_payments_one_pending_per_order",
        "payments",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "payment_events",
        sa.Column("payment_id", sa.UUID(), nullable=True),
        sa.Column("gateway", sa.String(length=32), nullable=False),
        sa.Column("gateway_reference", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "gateway ~ '^[a-z][a-z0-9_]*$'", name=op.f("ck_payment_events_gateway_format")
        ),
        sa.CheckConstraint(
            "kind IN ('callback', 'verify')", name=op.f("ck_payment_events_valid_kind")
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_payment_events_payment_id_payments"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
    )
    op.create_index(
        op.f("ix_payment_events_created_at"), "payment_events", ["created_at"], unique=False
    )
    op.create_index(
        "ix_payment_events_ip_created_at", "payment_events", ["ip", "created_at"], unique=False
    )
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"], unique=False)
    op.create_index(
        "ix_payment_events_gateway_reference",
        "payment_events",
        ["gateway", "gateway_reference"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_payment_events_gateway_reference", table_name="payment_events")
    op.drop_index("ix_payment_events_payment_id", table_name="payment_events")
    op.drop_index("ix_payment_events_ip_created_at", table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_created_at"), table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index(
        "uq_payments_one_pending_per_order",
        table_name="payments",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(
        "uq_payments_gateway_reference",
        table_name="payments",
        postgresql_where=sa.text("gateway_reference IS NOT NULL"),
    )
    op.drop_index(
        "ix_payments_pending_created_at",
        table_name="payments",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_index(op.f("ix_payments_created_at"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_fake_gateway_sessions_created_at"), table_name="fake_gateway_sessions")
    op.drop_table("fake_gateway_sessions")
