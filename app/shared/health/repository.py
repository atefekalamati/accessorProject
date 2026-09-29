from dataclasses import dataclass

from app.core.config import Environment, Settings


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    version: str
    environment: Environment


class HealthRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_snapshot(self) -> HealthSnapshot:
        return HealthSnapshot(
            version=self._settings.app_version,
            environment=self._settings.environment,
        )
