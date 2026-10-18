"""Create discount_attempts for the discount code rate limit (DSC-03, D34, ADR-043).

Revision ID: 20261018_0020
Revises: 20261018_0019
Create Date: 2026-10-18 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261018_0020"
down_revision: str | None = "20261018_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discount_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cart_id IS NOT NULL OR user_id IS NOT NULL",
            name=op.f("ck_discount_attempts_has_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"],
            ["carts.id"],
            name=op.f("fk_discount_attempts_cart_id_carts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_discount_attempts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discount_attempts")),
    )
    op.create_index(op.f("ix_discount_attempts_created_at"), "discount_attempts", ["created_at"])
    op.create_index(
        "ix_discount_attempts_cart_id_created_at", "discount_attempts", ["cart_id", "created_at"]
    )
    op.create_index(
        "ix_discount_attempts_user_id_created_at", "discount_attempts", ["user_id", "created_at"]
    )
    op.create_index("ix_discount_attempts_ip_created_at", "discount_attempts", ["ip", "created_at"])


def downgrade() -> None:
    op.drop_table("discount_attempts")
