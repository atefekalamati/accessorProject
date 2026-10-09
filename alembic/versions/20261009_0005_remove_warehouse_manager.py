"""Remove the deferred warehouse_manager role when no user holds it (ADR-004).

Data only: migration 20260913_0001 inserted the role, so every fresh database has it.
A role that is still assigned is left in place rather than silently revoked.

Revision ID: 20261009_0005
Revises: 20261006_0004
Create Date: 2026-10-09 00:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261009_0005"
down_revision: str | None = "20261006_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM roles
        WHERE name = 'warehouse_manager'
          AND NOT EXISTS (SELECT 1 FROM user_roles WHERE user_roles.role_id = roles.id)
        """
    )


def downgrade() -> None:
    # Same id and values as 20260913_0001; a role kept by upgrade stays untouched.
    op.execute(
        """
        INSERT INTO roles (id, name, description, is_system)
        VALUES ('d092d5a1-5d54-5abd-9dbc-d5921a375a2f', 'warehouse_manager',
                'Warehouse manager', true)
        ON CONFLICT (name) DO NOTHING
        """
    )
