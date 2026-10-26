"""Allowed moves of one payment row (PAY-01, ADR-051). Pure.

Separate from the order's ``payment_status`` (ORD-05), which follows the latest attempt
and has cross-field guards; a payment row has none. ``refund_required`` means the
gateway took money the shop must give back (late, duplicate or wrong amount).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from app.db.models import PaymentStatus

_P = PaymentStatus

PAYMENT_TRANSITIONS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        _P.PENDING: frozenset({_P.PAID, _P.FAILED, _P.REFUND_REQUIRED}),
        # A late verify of a payment closed as failed (lost callback, superseded).
        _P.FAILED: frozenset({_P.PAID, _P.REFUND_REQUIRED}),
    }
)


def can_move(current: str, new: str) -> bool:
    return new in PAYMENT_TRANSITIONS.get(current, frozenset())
