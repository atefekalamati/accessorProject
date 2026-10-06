from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings

BASE_SETTINGS: dict[str, Any] = {
    "database_url": "postgresql+asyncpg://user:password@localhost:5432/project_ak",
    "jwt_secret": "test-secret-that-is-at-least-32-characters",
}


def test_environment_and_comma_separated_cors_are_parsed() -> None:
    settings = Settings(
        **BASE_SETTINGS,
        environment="staging",
        cors_origins="https://shop.example.com, https://admin.example.com",
        otp_mock_enabled=False,
    )

    assert settings.environment is Environment.STAGING
    assert settings.cors_origins_list == [
        "https://shop.example.com",
        "https://admin.example.com",
    ]


def test_json_cors_value_is_parsed() -> None:
    settings = Settings(
        **BASE_SETTINGS,
        cors_origins='["http://localhost:3000", "http://localhost:5173"]',
    )

    assert settings.cors_origins_list == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]


def test_settings_are_loaded_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", BASE_SETTINGS["database_url"])
    monkeypatch.setenv("JWT_SECRET", BASE_SETTINGS["jwt_secret"])
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("CORS_ORIGINS", "https://shop.example.com,https://admin.example.com")
    monkeypatch.setenv("OTP_MOCK_ENABLED", "false")

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.STAGING
    assert settings.cors_origins_list == [
        "https://shop.example.com",
        "https://admin.example.com",
    ]
    assert settings.otp_mock_enabled is False


def test_wildcard_cors_is_forbidden_in_production() -> None:
    with pytest.raises(ValidationError, match="Wildcard CORS origin is forbidden"):
        Settings(
            **BASE_SETTINGS,
            environment="production",
            cors_origins="*",
            otp_mock_enabled=False,
        )


def test_mock_otp_is_forbidden_in_production() -> None:
    with pytest.raises(ValidationError, match="Mock OTP must be disabled"):
        Settings(
            **BASE_SETTINGS,
            environment="production",
            cors_origins="https://shop.example.com",
            otp_mock_enabled=True,
        )


def test_asyncpg_database_driver_is_required() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        Settings(
            **{**BASE_SETTINGS, "database_url": "postgresql://localhost/project_ak"},
        )


PRODUCTION_SETTINGS: dict[str, Any] = {
    **BASE_SETTINGS,
    "environment": "production",
    "cors_origins": "https://shop.example.com",
    "otp_mock_enabled": False,
}
OTP_HASH_SECRET = "test-otp-hash-secret-at-least-32-characters"


def test_otp_hash_secret_is_accepted_in_production() -> None:
    settings = Settings(**PRODUCTION_SETTINGS, otp_hash_secret=OTP_HASH_SECRET)

    assert settings.otp_hash_secret is not None
    assert settings.otp_hash_secret.get_secret_value() == OTP_HASH_SECRET


def test_missing_otp_hash_secret_fails_production_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTP_HASH_SECRET", raising=False)
    monkeypatch.setenv("DATABASE_URL", BASE_SETTINGS["database_url"])
    monkeypatch.setenv("JWT_SECRET", BASE_SETTINGS["jwt_secret"])
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://shop.example.com")
    monkeypatch.setenv("OTP_MOCK_ENABLED", "false")

    with pytest.raises(ValidationError, match="OTP_HASH_SECRET is required in production"):
        Settings(_env_file=None)


@pytest.mark.parametrize("environment", ["production", "development"])
def test_short_otp_hash_secret_is_rejected(environment: str) -> None:
    with pytest.raises(ValidationError, match=r"otp_hash_secret\n.*at least 32"):
        Settings(
            **{**PRODUCTION_SETTINGS, "environment": environment},
            otp_hash_secret="too-short",
        )


def test_otp_hash_secret_is_optional_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTP_HASH_SECRET", raising=False)

    settings = Settings(**BASE_SETTINGS, environment="development", _env_file=None)

    assert settings.otp_hash_secret is None


def test_mock_otp_fails_production_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", BASE_SETTINGS["database_url"])
    monkeypatch.setenv("JWT_SECRET", BASE_SETTINGS["jwt_secret"])
    monkeypatch.setenv("OTP_HASH_SECRET", OTP_HASH_SECRET)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://shop.example.com")
    monkeypatch.setenv("OTP_MOCK_ENABLED", "true")

    with pytest.raises(ValidationError, match="Mock OTP must be disabled in production"):
        Settings(_env_file=None)
