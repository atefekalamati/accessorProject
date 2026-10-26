from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.middleware import get_request_id
from app.shared.database.dependencies import get_database_health_service
from app.shared.database.schemas import DatabaseReadinessResponse, DatabaseStatusResponse
from app.shared.database.service import DatabaseHealthService

readiness_router = APIRouter(tags=["health"])
dev_router = APIRouter(prefix="/dev", tags=["development"])


@readiness_router.get(
    "/ready",
    response_model=DatabaseReadinessResponse,
    summary="Check PostgreSQL readiness",
)
async def readiness(
    service: Annotated[DatabaseHealthService, Depends(get_database_health_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> DatabaseReadinessResponse:
    return await service.get_readiness(request_id)


@dev_router.get(
    "/database-status",
    response_model=DatabaseStatusResponse,
    summary="Inspect the development database connection",
)
async def database_status(
    service: Annotated[DatabaseHealthService, Depends(get_database_health_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> DatabaseStatusResponse:
    return await service.get_status(request_id)
