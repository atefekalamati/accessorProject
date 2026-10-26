"""The three independent order statuses and their allowed moves (ORD-05, ADR-047).

Pure. Each field has its own transition table; a few moves also depend on another field
(e.g. an order is confirmed only once paid). ``check_transition`` returns why a move is
invalid, or None.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from app.db.models import OrderStatus, PaymentStatus, ShipmentStatus, StatusField

_O, _P, _S = OrderStatus, PaymentStatus, ShipmentStatus

TRANSITIONS: Final[Mapping[StatusField, Mapping[str, frozenset[str]]]] = MappingProxyType(
    {
        StatusField.ORDER: MappingProxyType(
            {
                _O.PENDING_PAYMENT: frozenset({_O.CONFIRMED, _O.CANCELLED}),
                _O.CONFIRMED: frozenset({_O.COMPLETED}),
            }
        ),
        StatusField.PAYMENT: MappingProxyType(
            {
                _P.UNPAID: frozenset({_P.PENDING}),
                _P.PENDING: frozenset({_P.PAID, _P.FAILED, _P.REFUND_REQUIRED}),
                # Retry, a late verify of the failed attempt, or a late success after cancel.
                _P.FAILED: frozenset({_P.PENDING, _P.PAID, _P.REFUND_REQUIRED}),
                # Staff recorded the manual refund (ADM-08, D35).
                _P.REFUND_REQUIRED: frozenset({_P.REFUNDED}),
                # Another attempt of the cancelled order paid late: money is owed again
                # (D35; the refund_required guard below keeps it to cancelled orders).
                _P.REFUNDED: frozenset({_P.REFUND_REQUIRED}),
            }
        ),
        StatusField.SHIPMENT: MappingProxyType(
            {
                _S.NOT_SHIPPED: frozenset({_S.PREPARING}),
                _S.PREPARING: frozenset({_S.SHIPPED}),
                _S.SHIPPED: frozenset({_S.DELIVERED}),
            }
        ),
    }
)

VALUES: Final[Mapping[StatusField, frozenset[str]]] = MappingProxyType(
    {
        StatusField.ORDER: frozenset(_O),
        StatusField.PAYMENT: frozenset(_P),
        StatusField.SHIPMENT: frozenset(_S),
    }
)


@dataclass(frozen=True, slots=True)
class OrderState:
    status: str
    payment_status: str
    shipment_status: str

    def of(self, field: StatusField) -> str:
        return {
            StatusField.ORDER: self.status,
            StatusField.PAYMENT: self.payment_status,
            StatusField.SHIPMENT: self.shipment_status,
        }[field]


def check_transition(state: OrderState, field: StatusField, new: str) -> str | None:
    """Why ``field`` may not move to ``new`` from ``state``, or None when it may."""
    if new not in VALUES[field]:
        return "unknown_status"
    current = state.of(field)
    if new == current:
        # Distinct from not_allowed so a retried cancel can be told apart (ORD-04/06).
        return "same_status"
    if new not in TRANSITIONS[field].get(current, frozenset()):
        return "not_allowed"
    match field, new:
        case StatusField.ORDER, _O.CONFIRMED if state.payment_status != _P.PAID:
            return "requires_payment_paid"
        case StatusField.ORDER, _O.COMPLETED if state.shipment_status != _S.DELIVERED:
            return "requires_shipment_delivered"
        case StatusField.ORDER, _O.CANCELLED if state.payment_status == _P.PAID:
            return "already_paid"
        case StatusField.PAYMENT, (_P.PENDING | _P.PAID) if state.status != _O.PENDING_PAYMENT:
            return "requires_order_pending_payment"
        case StatusField.PAYMENT, _P.REFUND_REQUIRED if state.status != _O.CANCELLED:
            return "requires_order_cancelled"
        case StatusField.SHIPMENT, _S.PREPARING if state.status != _O.CONFIRMED:
            return "requires_order_confirmed"
    return None
