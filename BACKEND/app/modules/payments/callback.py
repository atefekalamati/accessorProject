"""POST /payments/callback: the gateway's notice that a customer finished (PAY-03).

Untrusted (ADR-049): the body only yields a reference that finds the payment; the verify
call (server to server, outside any transaction) is the only source of truth. Every
callback is stored redacted in ``payment_events`` and counted for the per-IP rate limit
(429). A processed callback always answers 200 with the outcome in the body, so the
gateway never retries into a storm (ADR-051); an unknown reference is 404 and a body
without one 400.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Final

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import BadRequestError, NotFoundError, RateLimitedError
from app.core.time import utc_now
from app.db.models import Payment, PaymentEvent
from app.db.models.payments import PaymentEventKind
from app.modules.payments.common import record_event
from app.modules.payments.gateways.base import GatewayUnavailable, PaymentGateway, VerifyResult
from app.modules.payments.processing import Applied, PaymentProcessor
from app.modules.payments.service import call_gateway, gateway_unavailable
from app.shared.audit import client_ip

MAX_CALLBACK_BYTES: Final = 8 * 1024

logger = logging.getLogger(__name__)


def _invalid(message: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": "body", "message": message, "type": "value_error"}],
    )


async def read_body(request: Request) -> dict[str, Any]:
    """The JSON object body, capped before it is read (Content-Length, then streamed)."""
    too_large = _invalid(f"at most {MAX_CALLBACK_BYTES} bytes")
    length = request.headers.get("content-length")
    if length is not None and (not length.isdigit() or int(length) > MAX_CALLBACK_BYTES):
        logger.info("payment.callback_rejected", extra={"reason": "too_large"})
        raise too_large
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_CALLBACK_BYTES:
            logger.info("payment.callback_rejected", extra={"reason": "too_large"})
            raise too_large
    try:
        payload = json.loads(bytes(raw))
    except (ValueError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict):
        # Not stored and not counted (nothing to store); logged for monitoring.
        logger.info("payment.callback_rejected", extra={"reason": "not_json_object"})
        raise _invalid("must be a JSON object")
    return payload


class CallbackService:
    def __init__(self, session: AsyncSession, gateway: PaymentGateway, settings: Settings) -> None:
        self._session = session
        self._gateway = gateway
        self._settings = settings

    async def handle(self, payload: dict[str, Any], request: Request | None = None) -> Applied:
        ip = client_ip(request)
        reference = self._gateway.parse_callback(payload)
        async with self._session.begin():
            await self._limit(ip)
            payment_id = None
            amount = 0
            if reference is not None:
                found = (
                    await self._session.execute(
                        select(Payment.id, Payment.amount).where(
                            Payment.gateway == self._gateway.name,
                            Payment.gateway_reference == reference,
                        )
                    )
                ).one_or_none()
                if found is not None:
                    payment_id, amount = found
            await record_event(
                self._session,
                gateway=self._gateway.name,
                kind=PaymentEventKind.CALLBACK,
                payload=self._gateway.redact_callback(payload),
                reference=reference,
                payment_id=payment_id,
                ip=ip,
            )
        if reference is None:
            raise _invalid("no payment reference")
        if payment_id is None:
            raise NotFoundError(message="Unknown payment")
        try:
            result: VerifyResult = await call_gateway(
                self._gateway.verify(reference=reference, amount=amount),
                self._settings.payment_gateway_timeout_seconds,
            )
        except GatewayUnavailable:
            raise gateway_unavailable() from None
        return await PaymentProcessor(self._session).apply(payment_id, result, request=request)

    async def _limit(self, ip: str | None) -> None:
        """429 once this IP sent the window's maximum (not stored then: no amplification)."""
        if ip is None:
            return
        window = self._settings.payment_callback_window_seconds
        since = utc_now() - timedelta(seconds=window)
        count = await self._session.scalar(
            select(func.count())
            .select_from(PaymentEvent)
            .where(
                PaymentEvent.kind == PaymentEventKind.CALLBACK,
                PaymentEvent.ip == ip,
                PaymentEvent.created_at > since,
            )
        )
        if int(count or 0) >= self._settings.payment_callback_max_per_ip:
            raise RateLimitedError(retry_after=window, message="Too many payment callbacks")
