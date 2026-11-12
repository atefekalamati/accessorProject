"""Record manual refunds: the refunded status and the refund columns (ADM-08, D35).

Revision ID: 20261026_0027
Revises: 20261026_0026
Create Date: 2026-10-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261026_0027"
down_revision: str | None = "20261026_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literals copied from the models at the time of this migration (ADR-021).
_OLD_ROW = "'pending', 'paid', 'failed', 'refund_required'"
_NEW_ROW = "'pending', 'paid', 'failed', 'refund_required', 'refunded'"
_OLD_ORDER = "'unpaid', 'pending', 'paid', 'failed', 'refund_required'"
_NEW_ORDER = "'unpaid', 'pending', 'paid', 'failed', 'refund_required', 'refunded'"
REFUND_REFERENCE_PATTERN = r"^[^\x01-\x1f\x7f-\x9f\u2028\u2029]+$"

# (name, old, new) of the payments CHECKs that learn about refunded.
_PAYMENT_CHECKS = (
    ("valid_status", f"status IN ({_OLD_ROW})", f"status IN ({_NEW_ROW})"),
    (
        "paid_at_when_paid",
        "paid_at IS NULL OR status IN ('paid', 'refund_required')",
        "paid_at IS NULL OR status IN ('paid', 'refund_required', 'refunded')",
    ),
    (
        "closed_has_reason",
        "(status IN ('failed', 'refund_required')) = (failure_reason IS NOT NULL)",
        "(status IN ('failed', 'refund_required', 'refunded')) = (failure_reason IS NOT NULL)",
    ),
    (
        "refund_was_paid",
        "status <> 'refund_required' OR paid_at IS NOT NULL",
        "status NOT IN ('refund_required', 'refunded') OR paid_at IS NOT NULL",
    ),
)

_NEW_PAYMENT_CHECKS = (
    (
        "refund_record_complete",
        "(status = 'refunded') = (refund_reference IS NOT NULL)"
        " AND (refund_reference IS NULL) = (refund_amount IS NULL)"
        " AND (refund_reference IS NULL) = (refund_amount_source IS NULL)"
        " AND (refund_reference IS NULL) = (refunded_at IS NULL)"
        " AND (refund_reference IS NULL) = (refunded_by IS NULL)",
    ),
    ("refund_amount_positive", "refund_amount IS NULL OR refund_amount > 0"),
    (
        "refund_amount_source_valid",
        "refund_amount_source IS NULL OR refund_amount_source IN ('gateway', 'admin_entered')",
    ),
    (
        "gateway_refund_is_paid_amount",
        "refund_amount_source IS DISTINCT FROM 'gateway' OR refund_amount = paid_amount",
    ),
    (
        "refund_reference_format",
        "refund_reference IS NULL OR (refund_reference = btrim(refund_reference)"
        f" AND refund_reference ~ '{REFUND_REFERENCE_PATTERN}')",
    ),
)


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check")
    op.create_check_constraint(op.f(f"ck_{table}_{name}"), table, condition)


def upgrade() -> None:
    op.add_column("payments", sa.Column("refund_reference", sa.String(length=100)))
    op.add_column("payments", sa.Column("refund_amount", sa.BigInteger()))
    op.add_column("payments", sa.Column("refund_amount_source", sa.String(length=16)))
    op.add_column("payments", sa.Column("refunded_at", sa.DateTime(timezone=True)))
    op.add_column("payments", sa.Column("refunded_by", sa.UUID()))
    op.create_foreign_key(
        op.f("fk_payments_refunded_by_users"),
        "payments",
        "users",
        ["refunded_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    for name, _old, new in _PAYMENT_CHECKS:
        _replace_check("payments", name, new)
    for name, condition in _NEW_PAYMENT_CHECKS:
        op.create_check_constraint(op.f(f"ck_payments_{name}"), "payments", condition)
    op.create_index(
        "uq_payments_refund_reference",
        "payments",
        ["refund_reference"],
        unique=True,
        postgresql_where=sa.text("refund_reference IS NOT NULL"),
    )
    _replace_check("orders", "valid_payment_status", f"payment_status IN ({_NEW_ORDER})")


def downgrade() -> None:
    # Never lose a recorded refund: refuse while any exists (move them by hand first).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM payments WHERE status = 'refunded')
               OR EXISTS (SELECT 1 FROM orders WHERE payment_status = 'refunded') THEN
                RAISE EXCEPTION 'refunded payments exist; downgrade of 20261026_0027 refused';
            END IF;
        END $$;
        """
    )
    _replace_check("orders", "valid_payment_status", f"payment_status IN ({_OLD_ORDER})")
    op.drop_index("uq_payments_refund_reference", table_name="payments")
    for name, _condition in reversed(_NEW_PAYMENT_CHECKS):
        op.drop_constraint(op.f(f"ck_payments_{name}"), "payments", type_="check")
    for name, old, _new in reversed(_PAYMENT_CHECKS):
        _replace_check("payments", name, old)
    op.drop_constraint(op.f("fk_payments_refunded_by_users"), "payments", type_="foreignkey")
    for column in (
        "refunded_by",
        "refunded_at",
        "refund_amount_source",
        "refund_amount",
        "refund_reference",
    ):
        op.drop_column("payments", column)
