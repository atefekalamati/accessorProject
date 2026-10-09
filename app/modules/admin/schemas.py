from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import UserStatus
from app.db.seed import DEFAULT_ROLES

# Only the roles of the current release are assignable; leftovers in the database
# (e.g. ``warehouse_manager``) are not (ADR-004, ADR-019).
ASSIGNABLE_ROLES: Final = frozenset(role.name for role in DEFAULT_ROLES)
MAX_ROLES: Final = len(DEFAULT_ROLES)


class AdminUserResponse(BaseModel):
    id: UUID
    mobile: str
    first_name: str | None
    last_name: str | None
    email: str | None
    status: str
    roles: list[str]
    mobile_verified_at: datetime | None
    created_at: datetime


class UpdateUserStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: UserStatus


class UpdateUserRolesRequest(BaseModel):
    """The complete new role set of the user; it replaces the current one."""

    model_config = ConfigDict(extra="forbid")

    roles: list[str] = Field(min_length=1, max_length=MAX_ROLES)

    @field_validator("roles")
    @classmethod
    def check_roles(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - ASSIGNABLE_ROLES)
        if unknown:
            raise ValueError(f"unknown roles: {', '.join(unknown)}")
        if len(set(value)) != len(value):
            raise ValueError("roles must be unique")
        return sorted(value)
