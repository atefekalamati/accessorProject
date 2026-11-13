"""audit_logs is append-only in the database (SEC-04).

UPDATE, DELETE and TRUNCATE are refused by triggers (SQLSTATE 23000); the only update let
through is the foreign key's ON DELETE SET NULL when a user is deleted.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import AuditLog, User

pytestmark = pytest.mark.integration

INTEGRITY_VIOLATION = "23000"


async def _user(engine: AsyncEngine) -> UUID:
    user = User(phone=f"+989{uuid4().int % 1_000_000_000:09d}")
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return user.id


async def _audit(engine: AsyncEngine, actor: UUID | None) -> AuditLog:
    row = AuditLog(
        actor_user_id=actor,
        action="test.recorded",
        entity_type="test",
        entity_id=uuid4(),
        metadata_={"diff": {"x": {"before": 1, "after": 2, "changed": True}}},
        ip="203.0.113.7",
    )
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(row)
    return row


async def _refused(engine: AsyncEngine, statement: Any) -> None:
    async with AsyncSession(engine) as session:
        with pytest.raises(DBAPIError) as raised:
            async with session.begin():
                await session.execute(statement)
    assert getattr(raised.value.orig, "sqlstate", None) == INTEGRITY_VIOLATION


async def _row(engine: AsyncEngine, row_id: UUID) -> AuditLog:
    async with AsyncSession(engine) as session:
        return (await session.scalars(select(AuditLog).where(AuditLog.id == row_id))).one()


@pytest.mark.parametrize(
    "values",
    [
        {"action": "test.rewritten"},
        {"metadata_": {}},
        {"ip": "198.51.100.1"},
        {"entity_id": uuid4()},
        {"actor_user_id": None, "action": "test.rewritten"},
    ],
)
async def test_updates_are_refused_and_change_nothing(
    db_engine: AsyncEngine, values: dict[str, Any]
) -> None:
    actor = await _user(db_engine)
    row = await _audit(db_engine, actor)

    await _refused(db_engine, update(AuditLog).where(AuditLog.id == row.id).values(**values))

    stored = await _row(db_engine, row.id)
    assert (stored.action, stored.actor_user_id, stored.metadata_) == (
        row.action,
        actor,
        row.metadata_,
    )


async def test_moving_a_row_to_another_actor_is_refused(db_engine: AsyncEngine) -> None:
    row = await _audit(db_engine, await _user(db_engine))
    other = await _user(db_engine)

    await _refused(
        db_engine, update(AuditLog).where(AuditLog.id == row.id).values(actor_user_id=other)
    )


async def test_setting_an_actor_on_an_anonymous_row_is_refused(db_engine: AsyncEngine) -> None:
    row = await _audit(db_engine, None)
    actor = await _user(db_engine)

    await _refused(
        db_engine, update(AuditLog).where(AuditLog.id == row.id).values(actor_user_id=actor)
    )


async def test_delete_and_truncate_are_refused(db_engine: AsyncEngine) -> None:
    row = await _audit(db_engine, None)

    await _refused(db_engine, delete(AuditLog).where(AuditLog.id == row.id))
    await _refused(db_engine, text("TRUNCATE audit_logs"))
    assert (await _row(db_engine, row.id)).id == row.id


async def test_deleting_a_user_only_clears_the_actor_of_their_rows(
    db_engine: AsyncEngine,
) -> None:
    actor = await _user(db_engine)
    row = await _audit(db_engine, actor)

    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.id == actor))

    stored = await _row(db_engine, row.id)
    assert stored.actor_user_id is None
    assert (stored.action, stored.metadata_, str(stored.ip), stored.created_at) == (
        row.action,
        row.metadata_,
        "203.0.113.7",
        row.created_at,
    )


async def test_an_update_matching_no_row_is_harmless(db_engine: AsyncEngine) -> None:
    async with AsyncSession(db_engine) as session, session.begin():
        result = await session.execute(
            update(AuditLog).where(AuditLog.id == uuid4()).values(action="test.none")
        )
    assert result.rowcount == 0  # type: ignore[attr-defined]


async def test_the_triggers_fire_always(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT tgname, tgenabled::text FROM pg_trigger"
                " WHERE tgrelid = 'audit_logs'::regclass AND NOT tgisinternal"
            )
        )
        triggers = {name: str(enabled) for name, enabled in rows}

    for name in (
        "trg_audit_logs_prevent_delete",
        "trg_audit_logs_prevent_update",
        "trg_audit_logs_prevent_truncate",
    ):
        assert triggers.get(name) == "A", name


async def test_replica_mode_does_not_skip_the_triggers(db_engine: AsyncEngine) -> None:
    row = await _audit(db_engine, None)

    async with AsyncSession(db_engine) as session:
        with pytest.raises(DBAPIError) as raised:
            async with session.begin():
                await session.execute(text("SET LOCAL session_replication_role = replica"))
                role = await session.scalar(text("SHOW session_replication_role"))
                assert role == "replica"
                await session.execute(
                    update(AuditLog).where(AuditLog.id == row.id).values(action="test.replica")
                )
    assert getattr(raised.value.orig, "sqlstate", None) == INTEGRITY_VIOLATION
    assert (await _row(db_engine, row.id)).action == row.action
