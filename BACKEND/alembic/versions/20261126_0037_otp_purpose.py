"""OTP codes carry a purpose: a login code cannot delete an account and back (ACC-06).

Existing codes are login codes (server default). Downgrade drops the column; any
``account_delete`` code still open then becomes a login code of the same mobile, so the
downgrade first removes them.

Revision ID: 20261126_0037
Revises: 20261126_0036
Create Date: 2026-11-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261126_0037"
down_revision: str | None = "20261126_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "otp_codes",
        sa.Column("purpose", sa.String(length=20), server_default="login", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_otp_codes_valid_purpose"),
        "otp_codes",
        "purpose IN ('login', 'account_delete')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM otp_codes WHERE purpose <> 'login'")
    op.drop_constraint(op.f("ck_otp_codes_valid_purpose"), "otp_codes", type_="check")
    op.drop_column("otp_codes", "purpose")
