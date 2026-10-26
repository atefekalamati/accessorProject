"""Add variant price fields and the pricing_settings singleton (PRC-01, ADR-027).

Revision ID: 20261010_0011
Revises: 20261010_0010
Create Date: 2026-10-10 00:00:00+00:00
"""

import logging
from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261010_0011"
down_revision: str | None = "20261010_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# Literals copied from the models at the time of this migration (ADR-021).
MAX_PRICE_TOMAN = 1_000_000_000_000
MAX_TAX_RATE_BPS = 10_000
MAX_ROUNDING_STEP = 1_000_000
ROUNDING_MODES_SQL = "'up', 'down', 'nearest'"
PRICING_SETTINGS_ID = uuid5(NAMESPACE_URL, "project-ak:pricing_settings")


def upgrade() -> None:
    op.add_column("product_variants", sa.Column("base_price", sa.BigInteger(), nullable=True))
    op.add_column("product_variants", sa.Column("sale_price", sa.BigInteger(), nullable=True))
    op.add_column(
        "product_variants",
        sa.Column("sale_start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "product_variants", sa.Column("sale_end_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "product_variants",
        sa.Column("tax_enabled", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "product_variants",
        sa.Column("price_version", sa.Integer(), server_default="0", nullable=False),
    )

    # Every existing variant is price-less now, so active ones would break the new CHECK.
    # Deactivating one is only safe when its product is not published: a published product
    # must keep an active variant (PRD «محصولات»), so that case fails loudly instead.
    bind = op.get_bind()
    published = bind.scalar(
        sa.text(
            "SELECT count(*) FROM product_variants v JOIN products p ON p.id = v.product_id "
            "WHERE v.is_active AND v.base_price IS NULL AND v.deleted_at IS NULL "
            "AND p.status = 'published' AND p.deleted_at IS NULL"
        )
    )
    if published:
        raise RuntimeError(
            f"{published} active variant(s) of published products have no price; "
            "set prices or unpublish those products before this migration"
        )
    deactivated = bind.execute(
        sa.text(
            "UPDATE product_variants SET is_active = false WHERE is_active AND base_price IS NULL"
        )
    ).rowcount
    log = logger.warning if deactivated else logger.info
    log("PRC-01: deactivated %s price-less variant(s)", deactivated)

    for name, condition in (
        ("base_price_range", f"base_price IS NULL OR base_price BETWEEN 1 AND {MAX_PRICE_TOMAN}"),
        (
            "sale_price_range",
            "sale_price IS NULL OR "
            "(base_price IS NOT NULL AND sale_price >= 1 AND sale_price <= base_price)",
        ),
        (
            "sale_window_order",
            "sale_start_at IS NULL OR sale_end_at IS NULL OR sale_start_at < sale_end_at",
        ),
        (
            "sale_window_needs_sale_price",
            "sale_price IS NOT NULL OR (sale_start_at IS NULL AND sale_end_at IS NULL)",
        ),
        ("price_version_non_negative", "price_version >= 0"),
        ("active_needs_base_price", "NOT is_active OR base_price IS NOT NULL"),
    ):
        op.create_check_constraint(
            op.f(f"ck_product_variants_{name}"), "product_variants", condition
        )

    op.create_table(
        "pricing_settings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("singleton", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="TOMAN", nullable=False),
        sa.Column("tax_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("default_tax_rate_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rounding_mode", sa.String(length=10), server_default="nearest", nullable=False),
        sa.Column("rounding_step", sa.Integer(), server_default="1", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("singleton", name=op.f("ck_pricing_settings_singleton")),
        sa.CheckConstraint("currency = 'TOMAN'", name=op.f("ck_pricing_settings_currency_toman")),
        sa.CheckConstraint(
            f"default_tax_rate_bps BETWEEN 0 AND {MAX_TAX_RATE_BPS}",
            name=op.f("ck_pricing_settings_tax_rate_range"),
        ),
        sa.CheckConstraint(
            f"rounding_mode IN ({ROUNDING_MODES_SQL})",
            name=op.f("ck_pricing_settings_valid_rounding_mode"),
        ),
        sa.CheckConstraint(
            f"rounding_step BETWEEN 1 AND {MAX_ROUNDING_STEP}",
            name=op.f("ck_pricing_settings_rounding_step_range"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_pricing_settings_version_positive")),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_pricing_settings_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_settings")),
        sa.UniqueConstraint("singleton", name=op.f("uq_pricing_settings_singleton")),
    )
    # The single row with the v1 defaults: tax off (ADR-010), nearest/1 (ADR-014).
    op.execute(
        sa.text("INSERT INTO pricing_settings (id) VALUES (:id)").bindparams(
            sa.bindparam("id", PRICING_SETTINGS_ID, type_=postgresql.UUID(as_uuid=True))
        )
    )


def downgrade() -> None:
    # Drops all prices; variants deactivated by upgrade stay inactive.
    op.drop_table("pricing_settings")
    for name in (
        "active_needs_base_price",
        "price_version_non_negative",
        "sale_window_needs_sale_price",
        "sale_window_order",
        "sale_price_range",
        "base_price_range",
    ):
        op.drop_constraint(op.f(f"ck_product_variants_{name}"), "product_variants", type_="check")
    for column in (
        "price_version",
        "tax_enabled",
        "sale_end_at",
        "sale_start_at",
        "sale_price",
        "base_price",
    ):
        op.drop_column("product_variants", column)
