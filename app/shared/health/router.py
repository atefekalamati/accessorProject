from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.middleware import get_request_id
from app.shared.health.dependencies import get_health_service
from app.shared.health.schemas import HealthResponse
from app.shared.health.service import HealthService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Check API liveness")
async def health(
    service: Annotated[HealthService, Depends(get_health_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> HealthResponse:
    return await service.get_health(request_id)
