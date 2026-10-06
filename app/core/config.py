from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Any, cast

from fastapi import Request
from pydantic import BeforeValidator, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


def _parse_cors_origins(value: Any) -> Any:
    if isinstance(value, str):
        raw_value = value.strip()
        if raw_value.startswith("["):
            return json.loads(raw_value)
        return [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return value


CorsOrigins = Annotated[list[str], NoDecode, BeforeValidator(_parse_cors_origins)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Project AK API"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    database_url: str = Field(min_length=1)
    jwt_secret: SecretStr = Field(min_length=32)
    cors_origins: CorsOrigins = Field(default_factory=list)
    otp_mock_enabled: bool = True
    otp_mock_code: str = Field(default="123456", pattern=r"^\d{6}$")
    otp_ttl_seconds: int = Field(default=120, ge=30, le=600)
    # HMAC key for OTP hashes; required in production, kept separate from JWT_SECRET.
    otp_hash_secret: SecretStr | None = Field(default=None, min_length=32)
    # OTP request limits; counted from otp_codes over a rolling one-hour window.
    otp_resend_cooldown_seconds: int = Field(default=60, ge=1, le=600)
    otp_max_per_mobile_per_hour: int = Field(default=5, ge=1)
    otp_max_per_ip_per_hour: int = Field(default=60, ge=1)
    # Hard cap on SMS volume (SMS-bombing cost protection).
    otp_max_global_per_hour: int = Field(default=500, ge=1)
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str]) -> list[str]:
        invalid = [
            origin
            for origin in value
            if origin != "*" and not origin.startswith(("http://", "https://"))
        ]
        if invalid:
            raise ValueError("CORS_ORIGINS entries must be HTTP(S) origins")
        return value

    @model_validator(mode="after")
    def enforce_environment_safety(self) -> Settings:
        if self.environment is Environment.PRODUCTION:
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origin is forbidden in production")
            if self.otp_mock_enabled:
                raise ValueError("Mock OTP must be disabled in production")
            if self.otp_hash_secret is None:
                raise ValueError("OTP_HASH_SECRET is required in production")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return list(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)
