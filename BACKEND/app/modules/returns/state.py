"""Return request rules as pure functions (ORD-08..ORD-10, PRD «مرجوعی» ✓, ADR-063).

Global lock order for every path that changes a return request (ADR-048 extended):
order advisory lock → order row ``FOR UPDATE`` → return request row ``FOR UPDATE`` →
inventory items → … . The customer cancel locks only the request row: it touches no
order, stock or money and only frees quantity, and creating a request never locks
request rows, so the two cannot wait on each other. Staff transitions that touch stock
or money (ORD-09, ORD-10) must take the order locks first and not copy that shorter path.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Final

from app.core.errors import BusinessRuleError, ErrorCode
from app.db.models import ReturnStatus

_S = ReturnStatus
TRANSITIONS: Final[Mapping[ReturnStatus, frozenset[ReturnStatus]]] = {
    _S.REQUESTED: frozenset({_S.APPROVED, _S.REJECTED, _S.CANCELLED}),
    _S.APPROVED: frozenset({_S.RECEIVED}),
    _S.RECEIVED: frozenset({_S.INSPECTED}),
    # Some refund owed → refund_required; nothing to refund → closed.
    _S.INSPECTED: frozenset({_S.REFUND_REQUIRED, _S.CLOSED}),
    _S.REFUND_REQUIRED: frozenset({_S.REFUNDED}),
    _S.REJECTED: frozenset(),
    _S.CANCELLED: frozenset(),
    _S.REFUNDED: frozenset(),
    _S.CLOSED: frozenset(),
}
# Still in progress: an account with one of these cannot be deleted (ACC-05).
OPEN_STATUSES: Final = frozenset(
    {_S.REQUESTED, _S.APPROVED, _S.RECEIVED, _S.INSPECTED, _S.REFUND_REQUIRED}
)


def can_transition(current: ReturnStatus, new: ReturnStatus) -> bool:
    return new in TRANSITIONS[current]


def check_transition(current: str, new: ReturnStatus) -> None:
    """Raise 422 ``INVALID_STATE_TRANSITION`` unless ``current → new`` is allowed."""
    if not can_transition(ReturnStatus(current), new):
        raise BusinessRuleError(
            code=ErrorCode.INVALID_STATE_TRANSITION,
            message="This return status change is not allowed",
            details=[{"field": "status", "from": current, "to": new.value, "type": "not_allowed"}],
        )


def return_deadline(delivered_at: datetime, window_days: int) -> datetime:
    """The first moment a return can no longer be requested (exclusive end)."""
    if delivered_at.tzinfo is None:
        raise ValueError("delivered_at must be timezone-aware")
    if isinstance(window_days, bool) or window_days < 1:
        raise ValueError("window_days must be a positive int")
    return delivered_at + timedelta(days=window_days)


def window_open(delivered_at: datetime, window_days: int, now: datetime) -> bool:
    return now < return_deadline(delivered_at, window_days)


def returnable_quantity(purchased: int, claimed: int) -> int:
    """What is left to request on a line: never negative."""
    if purchased < 0 or claimed < 0:
        raise ValueError("quantities must not be negative")
    return max(0, purchased - claimed)
