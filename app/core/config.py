from __future__ import annotations

import json
import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import urlsplit

from fastapi import Request
from pydantic import BeforeValidator, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


def _parse_str_list(value: Any) -> Any:
    if isinstance(value, str):
        raw_value = value.strip()
        if raw_value.startswith("["):
            return json.loads(raw_value)
        return [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return value


CorsOrigins = Annotated[list[str], NoDecode, BeforeValidator(_parse_str_list)]
HostList = Annotated[list[str], NoDecode, BeforeValidator(_parse_str_list)]

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOSTNAME = re.compile(rf"^{_LABEL}(?:\.{_LABEL})*$")


class MediaStorage(StrEnum):
    LOCAL = "local"
    MEMORY = "memory"  # tests only; holds files in process memory


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
    # Wrong codes allowed per OTP before it is invalidated.
    otp_max_attempts: int = Field(default=5, ge=1, le=10)
    # Short-lived access JWT (body) and long-lived refresh token (cookie), ADR-012.
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    log_level: str = "INFO"
    # Media (CAT-05, ADR-028). The public base URL's host must be in MEDIA_ALLOWED_HOSTS.
    media_storage: MediaStorage = MediaStorage.LOCAL
    media_root: Path = Path("var/media")
    media_public_base_url: str = "http://localhost:8000/media"
    media_allowed_hosts: HostList = Field(default_factory=lambda: ["localhost"])
    # Cleanup of expired reservations (INV-06): seconds between sweeps; 0 turns it off.
    reservation_sweep_seconds: int = Field(default=60, ge=0, le=3600)
    # Failed discount-code attempts (DSC-03, D34): counted over a rolling window per owner
    # (user, or guest cart), per client IP and store-wide; reaching a cap gives 429.
    # Behind a reverse proxy the IP cap needs the trusted-proxy setup of OPS-04 (ADR-043).
    discount_attempt_window_seconds: int = Field(default=900, ge=60, le=86_400)
    discount_max_failed_per_owner: int = Field(default=10, ge=1)
    discount_max_failed_per_ip: int = Field(default=30, ge=1)
    # Store-wide switch against a distributed flood; high, since reaching it blocks everyone.
    discount_max_failed_global: int = Field(default=10_000, ge=1)

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

    @field_validator("media_allowed_hosts")
    @classmethod
    def validate_media_allowed_hosts(cls, value: list[str]) -> list[str]:
        invalid = [host for host in value if _HOSTNAME.fullmatch(host) is None]
        if invalid:
            raise ValueError("MEDIA_ALLOWED_HOSTS entries must be lowercase host names")
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
            if self.media_storage is MediaStorage.MEMORY:
                raise ValueError("MEDIA_STORAGE=memory is forbidden in production")
        self._check_media_base_url()
        return self

    def _check_media_base_url(self) -> None:
        parts = urlsplit(self.media_public_base_url)
        https_only = self.environment is Environment.PRODUCTION
        allowed_schemes = {"https"} if https_only else {"http", "https"}
        if (
            parts.scheme not in allowed_schemes
            or parts.hostname is None
            or parts.username is not None
            or parts.query
            or parts.fragment
        ):
            raise ValueError(
                "MEDIA_PUBLIC_BASE_URL must be an absolute "
                + ("https" if https_only else "http(s)")
                + " URL without credentials, query or fragment"
            )
        if parts.hostname not in self.media_allowed_hosts:
            raise ValueError("MEDIA_PUBLIC_BASE_URL host must be in MEDIA_ALLOWED_HOSTS")

    @property
    def cors_origins_list(self) -> list[str]:
        return list(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)
