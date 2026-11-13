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
        otp_hash_secret="test-otp-hash-secret-at-least-32-characters",
        media_public_base_url="https://cdn.example.com/media",
        media_allowed_hosts=["cdn.example.com"],
    )
    application = create_app(settings)
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/dev/database-status")
        served_spec = await client.get("/openapi.json")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"
    # The spec is not served in production (ADR-060); the route is absent from it too.
    assert served_spec.status_code == 404
    assert "/api/v1/dev/database-status" not in application.openapi()["paths"]
