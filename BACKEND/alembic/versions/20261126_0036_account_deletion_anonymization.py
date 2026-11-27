"""Allow the identity of a deleted account to be removed (ACC-05, D37, ADR-063 A1/A3).

``users.phone`` may be NULL, but only for a deleted account. The order's mobile and the
identity fields of the order's address snapshot (recipient, mobile, postal code, address
line, anonymized together) may be NULL, as may a contact message's name and mobile
(together). Province, city, items and amounts are never removed.

Downgrade fills anonymized rows with fixed placeholders, so the NOT NULL columns can be
restored; it never brings the data back.

Revision ID: 20261126_0036
Revises: 20261126_0035
Create Date: 2026-11-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261126_0036"
down_revision: str | None = "20261126_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLACEHOLDER_PHONE = "+989000000000"
DELETED = "deleted"
ADDRESS_TOGETHER = (
    "(recipient_name IS NULL) = (phone IS NULL)"
    " AND (recipient_name IS NULL) = (postal_code IS NULL)"
    " AND (recipient_name IS NULL) = (address_line IS NULL)"
)


def upgrade() -> None:
    op.alter_column("users", "phone", existing_type=sa.String(length=16), nullable=True)
    op.create_check_constraint(
        op.f("ck_users_phone_unless_deleted"),
        "users",
        "phone IS NOT NULL OR deleted_at IS NOT NULL",
    )
    op.alter_column("orders", "phone", existing_type=sa.String(length=16), nullable=True)
    for column, length in (
        ("recipient_name", 200),
        ("phone", 16),
        ("postal_code", 20),
        ("address_line", 500),
    ):
        op.alter_column(
            "order_addresses", column, existing_type=sa.String(length=length), nullable=True
        )
    op.create_check_constraint(
        op.f("ck_order_addresses_anonymized_together"), "order_addresses", ADDRESS_TOGETHER
    )
    op.alter_column("contact_messages", "name", existing_type=sa.String(length=100), nullable=True)
    op.alter_column("contact_messages", "phone", existing_type=sa.String(length=20), nullable=True)
    op.create_check_constraint(
        op.f("ck_contact_messages_anonymized_together"),
        "contact_messages",
        "(name IS NULL) = (phone IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_contact_messages_anonymized_together"), "contact_messages", type_="check"
    )
    op.execute(
        f"UPDATE contact_messages SET name = '{DELETED}', phone = '{PLACEHOLDER_PHONE}'"
        " WHERE name IS NULL"
    )
    op.alter_column("contact_messages", "phone", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("contact_messages", "name", existing_type=sa.String(length=100), nullable=False)

    op.drop_constraint(
        op.f("ck_order_addresses_anonymized_together"), "order_addresses", type_="check"
    )
    op.execute(
        f"UPDATE order_addresses SET recipient_name = '{DELETED}', phone = '{PLACEHOLDER_PHONE}',"
        " postal_code = '0000000000', address_line = '" + DELETED + "'"
        " WHERE recipient_name IS NULL"
    )
    for column, length in (
        ("address_line", 500),
        ("postal_code", 20),
        ("phone", 16),
        ("recipient_name", 200),
    ):
        op.alter_column(
            "order_addresses", column, existing_type=sa.String(length=length), nullable=False
        )
    op.execute(f"UPDATE orders SET phone = '{PLACEHOLDER_PHONE}' WHERE phone IS NULL")
    op.alter_column("orders", "phone", existing_type=sa.String(length=16), nullable=False)

    op.drop_constraint(op.f("ck_users_phone_unless_deleted"), "users", type_="check")
    # A deleted account keeps no number; the old schema needs one (still free: deleted).
    op.execute(f"UPDATE users SET phone = '{PLACEHOLDER_PHONE}' WHERE phone IS NULL")
    op.alter_column("users", "phone", existing_type=sa.String(length=16), nullable=False)
