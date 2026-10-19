"""Payment gateway adapters (PAY-01). Rial exists only inside this package (ADR-001)."""

from __future__ import annotations

from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Environment, PaymentGatewayName, Settings, get_app_settings
from app.modules.payments.gateways.base import PaymentGateway
from app.modules.payments.gateways.fake import FakeGateway

FAKE_PAGE_PATH = "/api/v1/payments/fake"


def build_payment_gateway(settings: Settings, engine: AsyncEngine) -> PaymentGateway:
    """Select the gateway; fails closed in production until PAY-07 (D8, ADR-049)."""
    if settings.environment is Environment.PRODUCTION:
        raise RuntimeError("No real payment gateway is configured for production")
    if settings.payment_gateway is PaymentGatewayName.FAKE:
        base = settings.payment_callback_url.split("/api/v1/", 1)[0]
        return FakeGateway(
            engine,
            base_url=f"{base}{FAKE_PAGE_PATH}",
            session_seconds=settings.payment_fake_session_seconds,
        )
    raise RuntimeError(f"Unknown payment gateway {settings.payment_gateway!r}")


def get_payment_gateway(request: Request) -> PaymentGateway:
    """FastAPI dependency: one gateway per application, overridable in tests."""
    gateway = getattr(request.app.state, "payment_gateway", None)
    if gateway is None:
        gateway = build_payment_gateway(get_app_settings(request), request.app.state.db_engine)
        request.app.state.payment_gateway = gateway
    return cast(PaymentGateway, gateway)
