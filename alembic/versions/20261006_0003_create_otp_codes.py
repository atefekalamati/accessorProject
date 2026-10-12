"""Create otp_codes for hashed, expiring, attempt-limited OTPs.

Revision ID: 20261006_0003
Revises: 20261006_0002
Create Date: 2026-10-06 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261006_0003"
down_revision: str | None = "20261006_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "otp_codes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("mobile", sa.String(length=16), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(r"mobile ~ '^\+989[0-9]{9}$'", name=op.f("ck_otp_codes_mobile_format")),
        sa.CheckConstraint(
            "code_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_otp_codes_code_hash_format")
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name=op.f("ck_otp_codes_attempt_count_non_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_otp_codes")),
    )
    op.create_index("ix_otp_codes_created_at", "otp_codes", ["created_at"])
    op.create_index("ix_otp_codes_mobile_created_at", "otp_codes", ["mobile", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_otp_codes_mobile_created_at", table_name="otp_codes")
    op.drop_index("ix_otp_codes_created_at", table_name="otp_codes")
    op.drop_table("otp_codes")
