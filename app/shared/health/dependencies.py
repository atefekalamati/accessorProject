from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_app_settings
from app.shared.health.repository import HealthRepository
from app.shared.health.service import HealthService


def get_health_repository(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> HealthRepository:
    return HealthRepository(settings)


def get_health_service(
    repository: Annotated[HealthRepository, Depends(get_health_repository)],
) -> HealthService:
    return HealthService(repository)
