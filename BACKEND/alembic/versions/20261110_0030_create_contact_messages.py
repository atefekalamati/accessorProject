"""Create the contact messages table (CNT-06).

Revision ID: 20261110_0030
Revises: 20261110_0029
Create Date: 2026-11-10 00:02:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261110_0030"
down_revision: str | None = "20261110_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_messages",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="new", nullable=False),
        sa.Column("internal_note", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("handled_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(message) BETWEEN 1 AND 2000",
            name=op.f("ck_contact_messages_message_length"),
        ),
        sa.CheckConstraint(
            "internal_note IS NULL OR char_length(internal_note) BETWEEN 1 AND 2000",
            name=op.f("ck_contact_messages_note_length"),
        ),
        sa.CheckConstraint(
            r"phone ~ '^\+989[0-9]{9}$'", name=op.f("ck_contact_messages_phone_format")
        ),
        sa.CheckConstraint(
            "status IN ('new', 'in_progress', 'closed')",
            name=op.f("ck_contact_messages_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["handled_by"],
            ["users.id"],
            name=op.f("fk_contact_messages_handled_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_contact_messages_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_messages")),
    )
    op.create_index(
        op.f("ix_contact_messages_created_at"), "contact_messages", ["created_at"], unique=False
    )
    op.create_index(
        "ix_contact_messages_ip_created_at", "contact_messages", ["ip", "created_at"], unique=False
    )
    op.create_index(
        "ix_contact_messages_phone_created_at",
        "contact_messages",
        ["phone", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_contact_messages_status_created_at",
        "contact_messages",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_contact_messages_status_created_at", table_name="contact_messages")
    op.drop_index("ix_contact_messages_phone_created_at", table_name="contact_messages")
    op.drop_index("ix_contact_messages_ip_created_at", table_name="contact_messages")
    op.drop_index(op.f("ix_contact_messages_created_at"), table_name="contact_messages")
    op.drop_table("contact_messages")
