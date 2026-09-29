from app.shared.health.repository import HealthRepository
from app.shared.health.schemas import HealthResponse


class HealthService:
    def __init__(self, repository: HealthRepository) -> None:
        self._repository = repository

    async def get_health(self, request_id: str) -> HealthResponse:
        snapshot = await self._repository.get_snapshot()
        return HealthResponse(
            version=snapshot.version,
            environment=snapshot.environment,
            request_id=request_id,
        )
