"""Discount redemptions keep an HMAC of the mobile, never the number (DSC-06, ADR-063 A2).

``phone`` is replaced by ``phone_hmac`` (HMAC-SHA256 hex) and ``phone_key_id`` (which
``PHONE_HMAC_KEYS`` entry made it). Existing rows are backfilled with the write key, so
upgrading a database that has redemptions needs ``PHONE_HMAC_KEYS`` set. The per-customer
limit index moves to the digest.

Downgrade restores ``phone`` from the order's snapshot (``orders.phone``); an order whose
snapshot was anonymized (ACC-05) gets a placeholder number.

Revision ID: 20261126_0035
Revises: 20261113_0034
Create Date: 2026-11-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261126_0035"
down_revision: str | None = "20261113_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "discount_redemptions"
LIVE = "status IN ('pending', 'confirmed')"
DIGEST = "^[0-9a-f]{64}$"
KEY_ID = "^[a-z0-9][a-z0-9_-]{0,15}$"
MOBILE = r"^\+989[0-9]{9}$"
PLACEHOLDER_PHONE = "+989000000000"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("phone_hmac", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("phone_key_id", sa.String(length=16), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, phone FROM {TABLE}")).all()
    if rows:
        from app.core.config import get_settings  # only when there is something to hash

        key = get_settings().phone_keys().write
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET phone_hmac = :digest, phone_key_id = :key WHERE id = :id"),
            [{"id": row.id, "digest": key.digest(row.phone), "key": key.key_id} for row in rows],
        )

    op.alter_column(TABLE, "phone_hmac", nullable=False)
    op.alter_column(TABLE, "phone_key_id", nullable=False)
    op.drop_index("ix_discount_redemptions_live_code_phone", table_name=TABLE)
    op.drop_constraint(op.f("ck_discount_redemptions_phone_format"), TABLE, type_="check")
    op.drop_column(TABLE, "phone")
    op.create_check_constraint(
        op.f("ck_discount_redemptions_phone_hmac_format"), TABLE, f"phone_hmac ~ '{DIGEST}'"
    )
    op.create_check_constraint(
        op.f("ck_discount_redemptions_phone_key_id_format"), TABLE, f"phone_key_id ~ '{KEY_ID}'"
    )
    op.create_index(
        "ix_discount_redemptions_live_code_phone_hmac",
        TABLE,
        ["discount_code_id", "phone_hmac", "phone_key_id"],
        postgresql_where=sa.text(LIVE),
    )


def downgrade() -> None:
    op.add_column(TABLE, sa.Column("phone", sa.String(length=16), nullable=True))
    op.execute(
        f"""
        UPDATE {TABLE} AS r
        SET phone = CASE WHEN o.phone ~ '{MOBILE}' THEN o.phone ELSE '{PLACEHOLDER_PHONE}' END
        FROM orders AS o
        WHERE o.id = r.order_id
        """
    )
    op.execute(f"UPDATE {TABLE} SET phone = '{PLACEHOLDER_PHONE}' WHERE phone IS NULL")
    op.alter_column(TABLE, "phone", nullable=False)
    op.drop_index("ix_discount_redemptions_live_code_phone_hmac", table_name=TABLE)
    op.drop_constraint(op.f("ck_discount_redemptions_phone_key_id_format"), TABLE, type_="check")
    op.drop_constraint(op.f("ck_discount_redemptions_phone_hmac_format"), TABLE, type_="check")
    op.drop_column(TABLE, "phone_key_id")
    op.drop_column(TABLE, "phone_hmac")
    op.create_check_constraint(
        op.f("ck_discount_redemptions_phone_format"), TABLE, f"phone ~ '{MOBILE}'"
    )
    op.create_index(
        "ix_discount_redemptions_live_code_phone",
        TABLE,
        ["discount_code_id", "phone"],
        postgresql_where=sa.text(LIVE),
    )
