"""Create discount_codes and discount_redemptions; add carts.discount_code_id (DSC-01).

Revision ID: 20261018_0019
Revises: 20261012_0018
Create Date: 2026-10-18 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261018_0019"
down_revision: str | None = "20261012_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literals copied from the models at the time of this migration (ADR-021).
MAX_PRICE_TOMAN = 1_000_000_000_000
MAX_PERCENT_BPS = 10_000
CODE_PATTERN = "^[A-Z0-9_-]{3,32}$"
MOBILE_PATTERN = r"^\+989[0-9]{9}$"
LIVE = "status IN ('pending', 'confirmed')"


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            name,
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
        for name in ("created_at", "updated_at")
    ]


def _check(table: str, name: str, sql: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=op.f(f"ck_{table}_{name}"))


def upgrade() -> None:
    t = "discount_codes"
    op.create_table(
        t,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("max_amount", sa.BigInteger(), nullable=True),
        sa.Column("min_order_amount", sa.BigInteger(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_limit_total", sa.Integer(), nullable=True),
        sa.Column("usage_limit_per_user", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        _uuid("created_by", nullable=True),
        _uuid("updated_by", nullable=True),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        _check(t, "code_format", f"code ~ '{CODE_PATTERN}'"),
        _check(t, "valid_type", "type IN ('percent', 'fixed')"),
        _check(
            t,
            "value_range",
            f"(type = 'percent' AND value BETWEEN 1 AND {MAX_PERCENT_BPS})"
            f" OR (type = 'fixed' AND value BETWEEN 1 AND {MAX_PRICE_TOMAN})",
        ),
        _check(
            t,
            "max_amount_range",
            "max_amount IS NULL OR (type = 'percent'"
            f" AND max_amount BETWEEN 1 AND {MAX_PRICE_TOMAN})",
        ),
        _check(
            t,
            "min_order_amount_range",
            f"min_order_amount IS NULL OR min_order_amount BETWEEN 1 AND {MAX_PRICE_TOMAN}",
        ),
        _check(t, "valid_window", "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at"),
        _check(t, "usage_limit_total_range", "usage_limit_total IS NULL OR usage_limit_total >= 1"),
        _check(
            t,
            "usage_limit_per_user_range",
            "usage_limit_per_user IS NULL OR usage_limit_per_user >= 1",
        ),
        _check(
            t,
            "per_user_within_total",
            "usage_limit_per_user IS NULL OR usage_limit_total IS NULL"
            " OR usage_limit_per_user <= usage_limit_total",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_discount_codes_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_discount_codes_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discount_codes")),
    )
    op.create_index(op.f("ix_discount_codes_created_at"), t, ["created_at"])
    op.create_index(op.f("ix_discount_codes_deleted_at"), t, ["deleted_at"])
    op.create_index(
        "uq_discount_codes_code",
        t,
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    r = "discount_redemptions"
    op.create_table(
        r,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        _uuid("discount_code_id"),
        _uuid("order_id"),
        _uuid("user_id", nullable=True),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _check(r, "valid_status", "status IN ('pending', 'confirmed', 'released')"),
        _check(r, "phone_format", f"phone ~ '{MOBILE_PATTERN}'"),
        _check(r, "code_format", f"code ~ '{CODE_PATTERN}'"),
        _check(r, "amount_range", f"amount BETWEEN 0 AND {MAX_PRICE_TOMAN}"),
        _check(r, "released_has_time", "(status = 'released') = (released_at IS NOT NULL)"),
        _check(
            r,
            "confirmed_has_time",
            "(status <> 'confirmed' OR confirmed_at IS NOT NULL)"
            " AND (status <> 'pending' OR confirmed_at IS NULL)",
        ),
        _check(
            r,
            "released_after_confirmed",
            "released_at IS NULL OR confirmed_at IS NULL OR released_at >= confirmed_at",
        ),
        sa.ForeignKeyConstraint(
            ["discount_code_id"],
            ["discount_codes.id"],
            name=op.f("fk_discount_redemptions_discount_code_id_discount_codes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_discount_redemptions_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discount_redemptions")),
    )
    op.create_index(op.f("ix_discount_redemptions_created_at"), r, ["created_at"])
    op.create_index("ix_discount_redemptions_order_id", r, ["order_id"])
    op.create_index(
        "uq_discount_redemptions_live_order",
        r,
        ["order_id"],
        unique=True,
        postgresql_where=sa.text(LIVE),
    )
    op.create_index(
        "ix_discount_redemptions_live_code_phone",
        r,
        ["discount_code_id", "phone"],
        postgresql_where=sa.text(LIVE),
    )

    op.add_column("carts", _uuid("discount_code_id", nullable=True))
    op.create_foreign_key(
        op.f("fk_carts_discount_code_id_discount_codes"),
        "carts",
        "discount_codes",
        ["discount_code_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_carts_discount_code_id_discount_codes"), "carts", type_="foreignkey"
    )
    op.drop_column("carts", "discount_code_id")
    op.drop_table("discount_redemptions")
    op.drop_table("discount_codes")
