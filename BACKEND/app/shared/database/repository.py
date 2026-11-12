from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True, slots=True)
class DatabaseSnapshot:
    database: str
    postgres_version: str
    timezone: str
    migration_revision: str | None


class DatabaseHealthRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def ping(self) -> bool:
        async with self._engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            return cast(int, result.scalar_one()) == 1

    async def get_status(self) -> DatabaseSnapshot:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT
                        current_database()::text AS database,
                        current_setting('server_version') AS postgres_version,
                        current_setting('TimeZone') AS timezone,
                        to_regclass('public.alembic_version') IS NOT NULL AS has_migrations
                    """
                )
            )
            row = result.mappings().one()
            migration_revision: str | None = None
            if row["has_migrations"]:
                revision_result = await connection.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                migration_revision = revision_result.scalar_one_or_none()

        return DatabaseSnapshot(
            database=str(row["database"]),
            postgres_version=str(row["postgres_version"]),
            timezone=str(row["timezone"]),
            migration_revision=migration_revision,
        )
