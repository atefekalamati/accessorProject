"""Align users with the PRD: names, email, mobile verification, E.164 phone.

Revision ID: 20261006_0002
Revises: 20260913_0001
Create Date: 2026-10-06 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_0002"
down_revision: str | None = "20260913_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literal copy of app.core.phone.MOBILE_E164_PATTERN at the time of this revision.
_PHONE_FORMAT = r"phone ~ '^\+989[0-9]{9}$'"


def upgrade() -> None:
    op.drop_constraint(op.f("uq_users_phone"), "users", type_="unique")
    op.create_index(
        "uq_users_phone",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_constraint(op.f("ck_users_phone_not_blank"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_phone_format"), "users", _PHONE_FORMAT)

    op.drop_column("users", "full_name")
    op.add_column("users", sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column(
        "users", sa.Column("mobile_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_users_first_name_not_blank"),
        "users",
        "first_name IS NULL OR length(trim(first_name)) > 0",
    )
    op.create_check_constraint(
        op.f("ck_users_last_name_not_blank"),
        "users",
        "last_name IS NULL OR length(trim(last_name)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_last_name_not_blank"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_first_name_not_blank"), "users", type_="check")
    op.drop_column("users", "mobile_verified_at")
    op.drop_column("users", "email")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
    op.add_column("users", sa.Column("full_name", sa.String(length=200), nullable=True))

    op.drop_constraint(op.f("ck_users_phone_format"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_phone_not_blank"), "users", "length(trim(phone)) > 0")
    # Fails if a soft-deleted user shares a mobile with another user; resolve those rows first.
    op.drop_index("uq_users_phone", table_name="users")
    op.create_unique_constraint(op.f("uq_users_phone"), "users", ["phone"])
