from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.phone import normalize_phone


class RequestOtpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mobile: str = Field(min_length=1, max_length=32)

    @field_validator("mobile")
    @classmethod
    def normalize_mobile(cls, value: str) -> str:
        # InvalidPhoneError is a ValueError, so an invalid number becomes a 400.
        return normalize_phone(value)


class RequestOtpResponse(BaseModel):
    expires_in_seconds: int
    resend_after_seconds: int


class VerifyOtpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mobile: str = Field(min_length=1, max_length=32)
    code: str = Field(pattern=r"^\d{6}$")

    @field_validator("mobile")
    @classmethod
    def normalize_mobile(cls, value: str) -> str:
        return normalize_phone(value)


class TokenResponse(BaseModel):
    """Access token only; the refresh token travels in an HttpOnly cookie (ADR-012)."""

    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


NAME_MAX_LENGTH: Final = 100
EMAIL_MAX_LENGTH: Final = 254


class ProfileResponse(BaseModel):
    """The current user; roles and permissions are read from the database per request."""

    id: UUID
    mobile: str
    first_name: str | None
    last_name: str | None
    email: str | None
    status: str
    mobile_verified_at: datetime | None
    roles: list[str]
    permissions: list[str]


class UpdateProfileRequest(BaseModel):
    """Only these fields are editable; anything else (mobile, role, status...) is a 400.

    Omitted fields are left unchanged; ``email: null`` clears the email.
    """

    model_config = ConfigDict(extra="forbid")

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value: str | None) -> str:
        # Validators skip omitted fields, so None here means an explicit null.
        if value is None:
            raise ValueError("must not be null")
        name = value.strip()
        if not name:
            raise ValueError("must not be blank")
        if len(name) > NAME_MAX_LENGTH:
            raise ValueError(f"must be at most {NAME_MAX_LENGTH} characters")
        return name

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        email = value.strip()
        if len(email) > EMAIL_MAX_LENGTH:
            raise ValueError(f"must be at most {EMAIL_MAX_LENGTH} characters")
        try:
            # Syntax only: no DNS or deliverability lookups.
            normalized = validate_email(email, check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise ValueError("must be a valid email address") from exc
        return normalized.lower()
