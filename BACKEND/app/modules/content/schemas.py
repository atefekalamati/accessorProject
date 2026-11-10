"""Content API shapes (CNT-04).

Server-owned fields a client echoes back are dropped, never applied; any other unknown
field is 400.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    StringConstraints,
    model_validator,
)

from app.db.models.catalog import SLUG_PATTERN
from app.db.models.content import MAX_PAGE_BODY_LENGTH, PageStatus
from app.modules.content.markdown import check_markdown

_SYSTEM_FIELDS: Final = frozenset(
    {"id", "created_at", "updated_at", "deleted_at", "published_at", "created_by", "updated_by"}
)
# Printable only: no control characters (a NUL would fail in PostgreSQL).
_NO_CONTROL: Final = r"^[^\x00-\x1f\x7f]+$"

Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
PageTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=_NO_CONTROL)
]
PageBody = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_PAGE_BODY_LENGTH),
    AfterValidator(check_markdown),
]


def drop_system_fields(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: value for key, value in data.items() if key not in _SYSTEM_FIELDS}
    return data


def require_some_non_null(model: BaseModel, nullable: frozenset[str] = frozenset()) -> None:
    """A PATCH changes at least one field and clears only the nullable ones."""
    sent = model.model_fields_set
    if not sent:
        raise ValueError("at least one field is required")
    nulls = sorted(name for name in sent - nullable if getattr(model, name) is None)
    if nulls:
        raise ValueError(f"must not be null: {', '.join(nulls)}")


class CreatePageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    title: PageTitle
    body: PageBody
    status: PageStatus = PageStatus.DRAFT

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)


class UpdatePageRequest(BaseModel):
    """Sent fields change; the slug is fixed at creation, so sending it is a 400."""

    model_config = ConfigDict(extra="forbid")

    title: PageTitle | None = None
    body: PageBody | None = None
    status: PageStatus | None = None

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return drop_system_fields(data)

    @model_validator(mode="after")
    def _fields(self) -> UpdatePageRequest:
        require_some_non_null(self)
        return self


class AdminPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    title: str
    body: str
    status: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PublicPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    body: str
    updated_at: datetime
