"""Payment gateway adapters (PAY-01). Rial exists only inside this package (ADR-001)."""

from __future__ import annotations

import logging
import re
from typing import Final, cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Environment, PaymentGatewayName, Settings, get_app_settings
from app.core.errors import AppError, ErrorCode
from app.modules.payments.gateways.base import PaymentGateway
from app.modules.payments.gateways.fake import FakeGateway
from app.modules.payments.gateways.zarinpal import ZarinpalGateway

FAKE_PAGE_PATH = "/api/v1/payments/fake"
# Zarinpal merchant ids are UUID-shaped (36 characters).
MERCHANT_ID: Final = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")

logger = logging.getLogger(__name__)


def build_payment_gateway(settings: Settings, engine: AsyncEngine) -> PaymentGateway:
    """Select the gateway (PAYMENT_PROVIDER).

    Production fails closed for every gateway until go-live (D13, ADR-058, ADR-064): the
    fake is never allowed there, and Zarinpal waits for the go-live checklist.
    """
    if settings.environment is Environment.PRODUCTION:
        raise RuntimeError("Payments stay disabled in production until go-live (D13)")
    if settings.payment_gateway is PaymentGatewayName.FAKE:
        base = settings.payment_callback_url.split("/api/v1/", 1)[0]
        return FakeGateway(
            engine,
            base_url=f"{base}{FAKE_PAGE_PATH}",
            session_seconds=settings.payment_fake_session_seconds,
        )
    if settings.payment_gateway is PaymentGatewayName.ZARINPAL:
        merchant = settings.zarinpal_merchant_id
        # The message never echoes the value.
        if merchant is None or not MERCHANT_ID.fullmatch(merchant.get_secret_value()):
            raise RuntimeError("ZARINPAL_MERCHANT_ID must be the 36-character merchant id")
        return ZarinpalGateway(
            merchant_id=merchant.get_secret_value(),
            sandbox=settings.zarinpal_sandbox,
            timeout_seconds=settings.payment_gateway_timeout_seconds,
        )
    raise RuntimeError(f"Unknown payment gateway {settings.payment_gateway!r}")


async def close_payment_gateway(gateway: object) -> None:
    """Release a gateway's connections (Zarinpal's HTTP client); others have none."""
    close = getattr(gateway, "aclose", None)
    if close is not None:
        await close()


def get_payment_gateway(request: Request) -> PaymentGateway:
    """FastAPI dependency: one gateway per application, overridable in tests.

    No usable gateway (production before go-live, a bad config) is 503, never a payment.
    """
    gateway = getattr(request.app.state, "payment_gateway", None)
    if gateway is None:
        try:
            gateway = build_payment_gateway(get_app_settings(request), request.app.state.db_engine)
        except RuntimeError as error:
            logger.error("payment.gateway_not_configured", extra={"error": str(error)})
            raise AppError(
                code=ErrorCode.PAYMENT_GATEWAY_UNAVAILABLE,
                message="The payment gateway is unavailable",
            ) from error
        request.app.state.payment_gateway = gateway
    return cast(PaymentGateway, gateway)
