"""Make audit_logs append-only in the database (SEC-04).

Rows can no longer be updated or truncated (deleting was already refused since 0001). The
one update let through is the foreign key's ``ON DELETE SET NULL``: when a user is hard
deleted, ``actor_user_id`` of their rows becomes NULL and nothing else changes.

All three triggers fire ``ALWAYS``, so ``session_replication_role = replica`` does not
skip them. The table owner can still drop or disable them; the application must not run
as the owner in production (OPS-04, ADR-059).

Revision ID: 20261113_0033
Revises: 20261111_0032
Create Date: 2026-11-13 00:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261113_0033"
down_revision: str | None = "20261111_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            -- ON DELETE SET NULL of actor_user_id (a user was deleted): nothing else changes.
            IF OLD.actor_user_id IS NOT NULL
               AND NEW.actor_user_id IS NULL
               AND to_jsonb(NEW) - 'actor_user_id' = to_jsonb(OLD) - 'actor_user_id' THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'audit_logs rows cannot be updated'
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_truncate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs cannot be truncated'
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_prevent_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_update()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_prevent_truncate
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_log_truncate()
        """
    )
    for trigger in (
        "trg_audit_logs_prevent_delete",
        "trg_audit_logs_prevent_update",
        "trg_audit_logs_prevent_truncate",
    ):
        op.execute(f"ALTER TABLE audit_logs ENABLE ALWAYS TRIGGER {trigger}")


def downgrade() -> None:
    # The delete trigger belongs to 0001: back to its default (origin) mode, kept in place.
    op.execute("ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_logs_prevent_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_prevent_truncate ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_prevent_update ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_truncate()")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_update()")
