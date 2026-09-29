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
