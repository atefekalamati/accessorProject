"""The public callback outcome: coarse, and only the order's payment state (SEC-08, ADR-061)."""

from __future__ import annotations

import pytest

from app.db.models import PaymentStatus
from app.modules.payments.callback import PublicOutcome, public_outcome
from app.modules.payments.processing import Applied, Outcome


def _applied(outcome: Outcome, order_payment_status: PaymentStatus) -> Applied:
    return Applied(
        outcome=outcome,
        order_number="ORD-2026-000001",
        order_status="confirmed",
        order_payment_status=order_payment_status,
        payment_status="paid",
    )


@pytest.mark.parametrize(
    ("outcome", "order_payment", "expected"),
    [
        (Outcome.PAID, PaymentStatus.PAID, PublicOutcome.SUCCESS),
        (Outcome.ALREADY_PROCESSED, PaymentStatus.PAID, PublicOutcome.SUCCESS),
        # A second payment on a paid order: the order is paid; the refund is staff work.
        (Outcome.DUPLICATE, PaymentStatus.PAID, PublicOutcome.SUCCESS),
        # A wrong amount on an old attempt of a paid order: the order state wins.
        (Outcome.AMOUNT_MISMATCH, PaymentStatus.PAID, PublicOutcome.SUCCESS),
        (Outcome.PENDING, PaymentStatus.PENDING, PublicOutcome.PENDING),
        # Pending wins: a second tab's session still at the gateway; it is polled again.
        (Outcome.PENDING, PaymentStatus.PAID, PublicOutcome.PENDING),
        (Outcome.PENDING, PaymentStatus.UNPAID, PublicOutcome.PENDING),
        (Outcome.FAILED, PaymentStatus.FAILED, PublicOutcome.FAILED),
        (Outcome.AMOUNT_MISMATCH, PaymentStatus.FAILED, PublicOutcome.FAILED),
        (Outcome.REFUND_REQUIRED, PaymentStatus.REFUND_REQUIRED, PublicOutcome.FAILED),
        (Outcome.ALREADY_PROCESSED, PaymentStatus.FAILED, PublicOutcome.FAILED),
        (Outcome.ALREADY_PROCESSED, PaymentStatus.REFUND_REQUIRED, PublicOutcome.FAILED),
        (Outcome.ALREADY_PROCESSED, PaymentStatus.REFUNDED, PublicOutcome.FAILED),
    ],
)
def test_the_public_outcome_follows_the_order_payment_state(
    outcome: Outcome, order_payment: PaymentStatus, expected: PublicOutcome
) -> None:
    assert public_outcome(_applied(outcome, order_payment)) is expected


def test_there_are_exactly_three_public_outcomes() -> None:
    assert {value.value for value in PublicOutcome} == {"success", "failed", "pending"}
