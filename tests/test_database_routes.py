from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.core.config import Environment, Settings
from app.main import create_app


async def test_development_database_status_is_absent_in_production() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/project_ak",
        jwt_secret="test-secret-that-is-at-least-32-characters",
        environment=Environment.PRODUCTION,
        cors_origins=["https://shop.example.com"],
        otp_mock_enabled=False,
    )
    application = create_app(settings)
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/dev/database-status")
        openapi_response = await client.get("/openapi.json")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"
    assert "/api/v1/dev/database-status" not in openapi_response.json()["paths"]
