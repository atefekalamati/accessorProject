from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.core.config import Environment


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    environment: Environment
    request_id: UUID
