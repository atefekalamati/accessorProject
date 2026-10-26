from __future__ import annotations

import logging

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.shared.database.repository import DatabaseHealthRepository
from app.shared.database.schemas import DatabaseReadinessResponse, DatabaseStatusResponse

logger = logging.getLogger("app.database")


class DatabaseHealthService:
    def __init__(self, repository: DatabaseHealthRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    async def get_readiness(self, request_id: str) -> DatabaseReadinessResponse:
        try:
            available = await self._repository.ping()
        except SQLAlchemyError:
            logger.warning("database.readiness_failed", extra={"request_id": request_id})
            available = False

        if not available:
            raise AppError(
                code=ErrorCode.DATABASE_UNAVAILABLE,
                message="Database is unavailable",
            )

        return DatabaseReadinessResponse(
            version=self._settings.app_version,
            environment=self._settings.environment,
            request_id=request_id,
        )

    async def get_status(self, request_id: str) -> DatabaseStatusResponse:
        try:
            snapshot = await self._repository.get_status()
        except SQLAlchemyError as exc:
            logger.warning("database.status_failed", extra={"request_id": request_id})
            raise AppError(
                code=ErrorCode.DATABASE_UNAVAILABLE,
                message="Database is unavailable",
            ) from exc

        return DatabaseStatusResponse(
            database=snapshot.database,
            postgres_version=snapshot.postgres_version,
            timezone=snapshot.timezone,
            migration_revision=snapshot.migration_revision,
            request_id=request_id,
        )
