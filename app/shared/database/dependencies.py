from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_app_settings
from app.db.session import get_db_engine
from app.shared.database.repository import DatabaseHealthRepository
from app.shared.database.service import DatabaseHealthService


def get_database_health_repository(
    engine: Annotated[AsyncEngine, Depends(get_db_engine)],
) -> DatabaseHealthRepository:
    return DatabaseHealthRepository(engine)


def get_database_health_service(
    repository: Annotated[DatabaseHealthRepository, Depends(get_database_health_repository)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DatabaseHealthService:
    return DatabaseHealthService(repository, settings)
