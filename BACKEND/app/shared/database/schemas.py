from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.core.config import Environment


class DatabaseReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"
    database: Literal["available"] = "available"
    version: str
    environment: Environment
    request_id: UUID


class DatabaseStatusResponse(BaseModel):
    status: Literal["connected"] = "connected"
    database: str
    postgres_version: str
    timezone: str
    migration_revision: str | None
    request_id: UUID
