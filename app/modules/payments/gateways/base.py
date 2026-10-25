"""The payment gateway interface (PAY-01, ADR-009, ADR-049).

Everything outside ``app/modules/payments/gateways`` speaks integer toman (ADR-001); an
adapter converts to and from rial at its edge with ``toman_to_rial``/``rial_to_toman``.
Gateway calls happen outside any database transaction: callers never hold a lock across
the network.

A callback is untrusted: ``parse_callback`` only extracts the reference that finds the
payment. Only ``verify`` (server to server) can change a payment's state.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Final, Protocol
from uuid import UUID

RIAL_PER_TOMAN: Final = 10
# Card numbers (PAN), also written with spaces or dashes.
_LONG_DIGITS: Final = re.compile(r"(?:\d[ -]?){11,18}\d")
# Gateway references and tracking codes are often long numbers; they are needed for
# disputes and are not card data, so their values are kept (after reference validation).
_REFERENCE_KEYS: Final = frozenset({"reference", "tracking_code"})
REDACTED: Final = "[REDACTED]"
MAX_REFERENCE_LENGTH: Final = 128
_REFERENCE: Final = re.compile(rf"[!-~]{{1,{MAX_REFERENCE_LENGTH}}}")


def toman_to_rial(amount_toman: int) -> int:
    if isinstance(amount_toman, bool) or not isinstance(amount_toman, int) or amount_toman < 1:
        raise ValueError("amount must be a positive integer toman")
    return amount_toman * RIAL_PER_TOMAN


def rial_to_toman(amount_rial: int) -> int | None:
    """Toman, or None when the rial amount is not a whole toman (an amount mismatch)."""
    if isinstance(amount_rial, bool) or not isinstance(amount_rial, int) or amount_rial < 0:
        return None
    if amount_rial % RIAL_PER_TOMAN:
        return None
    return amount_rial // RIAL_PER_TOMAN


def redact_payload(payload: Mapping[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    """Only ``allowed`` keys with scalar values; card-number-like digit runs masked."""
    kept: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in allowed:
            continue
        if key in _REFERENCE_KEYS:
            kept[key] = valid_reference(value) or REDACTED
        elif isinstance(value, str):
            kept[key] = _LONG_DIGITS.sub(REDACTED, value)[:256]
        elif isinstance(value, bool) or value is None:
            kept[key] = value
        elif isinstance(value, int):
            # A 12+ digit number could be a card number; no amount here is that large.
            kept[key] = REDACTED if abs(value) >= 10**11 else value
    return kept


def valid_reference(value: object) -> str | None:
    return value if isinstance(value, str) and _REFERENCE.fullmatch(value) else None


class VerifyOutcome(StrEnum):
    PAID = "paid"
    # Final: the gateway says this payment will never be paid.
    FAILED = "failed"
    # Not decided yet (customer still at the gateway) or unknown to it: change nothing.
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    reference: str
    redirect_url: str
    # When the gateway stops accepting the customer for this payment.
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class VerifyResult:
    outcome: VerifyOutcome
    # Toman the gateway confirms it took (PAID only); None if it is not a whole toman.
    amount: int | None = None
    failure_reason: str | None = None
    # Allowlisted and redacted; stored on the payment and in its verify event.
    raw: dict[str, Any] = field(default_factory=dict)


class GatewayUnavailable(Exception):
    """The gateway did not answer (network error or timeout).

    Adapters raise it for every transport error of their HTTP client; callers also map
    ``TimeoutError``/``OSError`` to it.
    """


class PaymentGateway(Protocol):
    name: str

    async def request(
        self, *, payment_id: UUID, amount: int, callback_url: str
    ) -> GatewayRequest: ...

    async def verify(self, *, reference: str, amount: int) -> VerifyResult: ...

    def parse_callback(self, payload: Mapping[str, Any]) -> str | None:
        """The payment reference of a callback, or None if it has none."""
        ...

    def redact_callback(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...
