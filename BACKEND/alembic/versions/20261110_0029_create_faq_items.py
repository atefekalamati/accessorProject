"""Create the FAQ items table (CNT-05, D40).

Revision ID: 20261110_0029
Revises: 20261110_0028
Create Date: 2026-11-10 00:01:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261110_0029"
down_revision: str | None = "20261110_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "faq_items",
        sa.Column("group_title", sa.String(length=100), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(answer) BETWEEN 1 AND 5000", name=op.f("ck_faq_items_answer_length")
        ),
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_faq_items_display_order_non_negative")
        ),
        sa.CheckConstraint(
            "group_title = btrim(group_title) AND group_title <> ''",
            name=op.f("ck_faq_items_group_format"),
        ),
        sa.CheckConstraint(
            "question = btrim(question) AND question <> ''",
            name=op.f("ck_faq_items_question_format"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_faq_items_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_faq_items_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_faq_items")),
    )
    op.create_index(op.f("ix_faq_items_created_at"), "faq_items", ["created_at"], unique=False)
    op.create_index(op.f("ix_faq_items_deleted_at"), "faq_items", ["deleted_at"], unique=False)
    op.create_index("ix_faq_items_public_order", "faq_items", ["display_order", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_faq_items_public_order", table_name="faq_items")
    op.drop_index(op.f("ix_faq_items_deleted_at"), table_name="faq_items")
    op.drop_index(op.f("ix_faq_items_created_at"), table_name="faq_items")
    op.drop_table("faq_items")
