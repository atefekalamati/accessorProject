from __future__ import annotations

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
