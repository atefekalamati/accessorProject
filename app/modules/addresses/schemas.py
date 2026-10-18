"""Address API shapes (ADDR-01, ADR-045)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    StrictBool,
    StringConstraints,
    model_validator,
)

from app.core.phone import normalize_phone

SYSTEM_FIELDS: Final = frozenset({"id", "user_id", "created_at", "updated_at"})
NULLABLE_FIELDS: Final = frozenset({"plaque", "unit"})

_LOCAL_DIGITS: Final = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2)
_POSTAL: Final = re.compile(r"[0-9]{10}")


def _postal_code(raw: str) -> str:
    """Ten digits; Persian or Arabic-Indic digits, spaces and hyphens are accepted."""
    cleaned = re.sub(r"[\s-]", "", raw.translate(_LOCAL_DIGITS))
    if not _POSTAL.fullmatch(cleaned):
        raise ValueError("A postal code is 10 digits")
    return cleaned


def _mobile(raw: str) -> str:
    return normalize_phone(raw)


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Mobile = Annotated[str, StringConstraints(max_length=32), AfterValidator(_mobile)]
PostalCode = Annotated[str, StringConstraints(max_length=32), AfterValidator(_postal_code)]


def _drop_system_fields(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: value for key, value in data.items() if key not in SYSTEM_FIELDS}
    return data


class CreateAddressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_name: Name
    phone: Mobile
    province: Text
    city: Text
    postal_code: PostalCode
    address_line: Line
    plaque: Short | None = None
    unit: Short | None = None
    is_default: StrictBool = False

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return _drop_system_fields(data)


class UpdateAddressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_name: Name | None = None
    phone: Mobile | None = None
    province: Text | None = None
    city: Text | None = None
    postal_code: PostalCode | None = None
    address_line: Line | None = None
    plaque: Short | None = None
    unit: Short | None = None
    is_default: StrictBool | None = None

    @model_validator(mode="before")
    @classmethod
    def _system_fields(cls, data: Any) -> Any:
        return _drop_system_fields(data)

    @model_validator(mode="after")
    def _fields(self) -> UpdateAddressRequest:
        sent = self.model_fields_set
        if not sent:
            raise ValueError("at least one field is required")
        nulls = sorted(name for name in sent - NULLABLE_FIELDS if getattr(self, name) is None)
        if nulls:
            raise ValueError(f"must not be null: {', '.join(nulls)}")
        return self


class AddressResponse(BaseModel):
    id: UUID
    recipient_name: str
    phone: str
    province: str
    city: str
    postal_code: str
    address_line: str
    plaque: str | None
    unit: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime
