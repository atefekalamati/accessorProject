"""The fake payment gateway for development, tests and staging (PAY-01, ADR-051).

It behaves like a real one where the shop can tell: it keeps amounts in rial (so the
toman ↔ rial edge is exercised), its sessions expire, and ``verify`` is the only source
of truth. Its sessions live in ``fake_gateway_sessions`` so a restart, a second worker
or a replica never loses one. Each call uses its own short transaction (never the
caller's: a gateway call happens outside the shop's transactions).

``complete`` plays the customer at the gateway's page (paying or giving up); only the
development router exposes it, and never in production.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import FakeGatewaySession
from app.modules.payments.gateways.base import (
    GatewayRequest,
    VerifyOutcome,
    VerifyResult,
    redact_payload,
    rial_to_toman,
    toman_to_rial,
    valid_reference,
)

FAKE_GATEWAY: Final = "fake"
_CALLBACK_KEYS: Final = frozenset({"reference", "status"})
_VERIFY_KEYS: Final = frozenset({"reference", "status", "amount_rial", "tracking_code"})


class FakeGateway:
    name = FAKE_GATEWAY

    def __init__(self, engine: AsyncEngine, *, base_url: str, session_seconds: int) -> None:
        self._engine = engine
        self._base_url = base_url.rstrip("/")
        self._session_ttl = timedelta(seconds=session_seconds)

    async def request(self, *, payment_id: UUID, amount: int, callback_url: str) -> GatewayRequest:
        reference = f"FAKE-{secrets.token_urlsafe(18)}"
        expires_at = utc_now() + self._session_ttl
        async with AsyncSession(self._engine) as session, session.begin():
            session.add(
                FakeGatewaySession(
                    reference=reference,
                    payment_id=payment_id,
                    amount_rial=toman_to_rial(amount),
                    expires_at=expires_at,
                )
            )
        return GatewayRequest(
            reference=reference,
            redirect_url=f"{self._base_url}/{reference}",
            expires_at=expires_at,
        )

    async def verify(self, *, reference: str, amount: int) -> VerifyResult:
        async with AsyncSession(self._engine) as session:
            fake = await session.get(FakeGatewaySession, reference)
        if fake is None:
            # Never invent a result for a reference it does not know.
            raw = redact_payload({"reference": reference}, _VERIFY_KEYS)
            return VerifyResult(VerifyOutcome.PENDING, raw=raw)
        raw = redact_payload(
            {"reference": reference, "status": fake.status, "amount_rial": fake.paid_amount_rial},
            _VERIFY_KEYS,
        )
        if fake.status == "paid":
            assert fake.paid_amount_rial is not None
            return VerifyResult(
                VerifyOutcome.PAID, amount=rial_to_toman(fake.paid_amount_rial), raw=raw
            )
        if fake.status == "failed":
            return VerifyResult(VerifyOutcome.FAILED, failure_reason="declined", raw=raw)
        if utc_now() >= fake.expires_at:
            return VerifyResult(VerifyOutcome.FAILED, failure_reason="session_expired", raw=raw)
        return VerifyResult(VerifyOutcome.PENDING, raw=raw)

    def parse_callback(self, payload: Mapping[str, Any]) -> str | None:
        return valid_reference(payload.get("reference"))

    def redact_callback(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return redact_payload(payload, _CALLBACK_KEYS)

    async def complete(self, reference: str, *, paid: bool, amount_rial: int | None = None) -> bool:
        """The customer pays (``amount_rial`` defaults to the requested amount) or gives up.

        False for an unknown, already finished or expired session.
        """
        async with AsyncSession(self._engine) as session, session.begin():
            fake = (
                await session.scalars(
                    select(FakeGatewaySession)
                    .where(FakeGatewaySession.reference == reference)
                    .with_for_update()
                )
            ).one_or_none()
            # An expired session was already reported as finally failed by ``verify``.
            if fake is None or fake.status != "pending" or utc_now() >= fake.expires_at:
                return False
            if paid:
                fake.status = "paid"
                fake.paid_amount_rial = amount_rial if amount_rial is not None else fake.amount_rial
            else:
                fake.status = "failed"
        return True
