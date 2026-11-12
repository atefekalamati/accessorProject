"""Payment model, gateway interface and the fake gateway (PAY-01, ADR-049, ADR-051)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import MakeOrder
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Environment, Settings
from app.core.time import utc_now
from app.db.models import FakeGatewaySession, Payment, PaymentEvent
from app.modules.payments.gateways import build_payment_gateway
from app.modules.payments.gateways.base import (
    REDACTED,
    VerifyOutcome,
    redact_payload,
    rial_to_toman,
    toman_to_rial,
    valid_reference,
)
from app.modules.payments.gateways.fake import FakeGateway
from app.modules.payments.state import can_move

# --- pure ------------------------------------------------------------------------------


def test_toman_and_rial_convert_only_whole_toman() -> None:
    assert toman_to_rial(12_345) == 123_450
    assert rial_to_toman(123_450) == 12_345
    assert rial_to_toman(123_455) is None  # not a whole toman: an amount mismatch
    assert rial_to_toman(-10) is None
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            toman_to_rial(bad)  # type: ignore[arg-type]


def test_redaction_keeps_allowed_scalars_and_masks_card_numbers() -> None:
    payload = {
        "reference": "REF-1",
        "card": "6037991234567890",
        "status": "ok 6037-9912-3456-7890 / 6037 9912 3456 7890 / 6037991234567890",
        "tracking_code": "123456789012345",
        "amount_rial": 120_000,
        "pan_number": 6037991234567890,
        "nested": {"x": 1},
    }
    allowed = frozenset({"reference", "status", "amount_rial", "pan_number", "tracking_code"})
    kept = redact_payload(payload, allowed)
    assert kept == {
        "reference": "REF-1",
        "status": f"ok {REDACTED} / {REDACTED} / {REDACTED}",
        # Long numeric references are not card data and are needed for disputes.
        "tracking_code": "123456789012345",
        "amount_rial": 120_000,
        "pan_number": REDACTED,
    }
    assert "card" not in kept and "nested" not in kept


def test_references_are_printable_ascii() -> None:
    assert valid_reference("FAKE-abc_123") == "FAKE-abc_123"
    for bad in ("", "a b", "x" * 129, 5, None, "Ã˜Â±"):
        assert valid_reference(bad) is None


@pytest.mark.parametrize(
    ("current", "new", "allowed"),
    [
        ("pending", "paid", True),
        ("pending", "failed", True),
        ("pending", "refund_required", True),
        ("failed", "paid", True),
        ("failed", "refund_required", True),
        ("failed", "pending", False),
        ("paid", "failed", False),
        ("paid", "refund_required", False),
        ("refund_required", "paid", False),
        ("pending", "pending", False),
    ],
)
def test_payment_row_transitions(current: str, new: str, allowed: bool) -> None:
    assert can_move(current, new) is allowed


def test_production_never_gets_the_fake_gateway(settings: Settings) -> None:
    production = settings.model_copy(update={"environment": Environment.PRODUCTION})
    with pytest.raises(RuntimeError, match="production"):
        build_payment_gateway(production, engine=None)  # type: ignore[arg-type]
    assert isinstance(build_payment_gateway(settings, engine=None), FakeGateway)  # type: ignore[arg-type]


def test_the_stale_age_must_exceed_the_gateway_timeout(settings: Settings) -> None:
    values = settings.model_dump() | {
        "payment_gateway_timeout_seconds": 30,
        "payment_pending_stale_seconds": 60,
    }
    with pytest.raises(ValidationError, match="3x the gateway timeout"):
        Settings(_env_file=None, **values)


# --- the fake gateway (its sessions are in the database) -------------------------------


integration = pytest.mark.integration


@pytest_asyncio.fixture
async def fake(db_engine: AsyncEngine) -> AsyncIterator[FakeGateway]:
    gateway = FakeGateway(db_engine, base_url="http://testserver/pay", session_seconds=900)
    yield gateway


@integration
async def test_the_fake_request_and_verify_round_trip(fake: FakeGateway) -> None:
    payment_id = uuid4()
    request = await fake.request(payment_id=payment_id, amount=150_000, callback_url="x")

    assert request.redirect_url == f"http://testserver/pay/{request.reference}"
    assert valid_reference(request.reference)
    assert (await fake.verify(reference=request.reference, amount=150_000)).outcome is (
        VerifyOutcome.PENDING
    )
    assert await fake.complete(request.reference, paid=True)
    paid = await fake.verify(reference=request.reference, amount=150_000)
    assert (paid.outcome, paid.amount) == (VerifyOutcome.PAID, 150_000)
    assert paid.raw == {"reference": request.reference, "status": "paid", "amount_rial": 1_500_000}
    assert not await fake.complete(request.reference, paid=False)  # already finished


@integration
async def test_an_expired_fake_session_cannot_be_paid(
    fake: FakeGateway, db_engine: AsyncEngine
) -> None:
    request = await fake.request(payment_id=uuid4(), amount=1_000, callback_url="x")
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(FakeGatewaySession)
            .where(FakeGatewaySession.reference == request.reference)
            .values(expires_at=utc_now() - timedelta(seconds=1))
        )

    assert not await fake.complete(request.reference, paid=True)
    late = await fake.verify(reference=request.reference, amount=1_000)
    assert late.outcome is VerifyOutcome.FAILED


@integration
async def test_the_fake_reports_failures_odd_amounts_and_unknown_references(
    fake: FakeGateway, db_engine: AsyncEngine
) -> None:
    declined = await fake.request(payment_id=uuid4(), amount=1_000, callback_url="x")
    odd = await fake.request(payment_id=uuid4(), amount=1_000, callback_url="x")
    expired = await fake.request(payment_id=uuid4(), amount=1_000, callback_url="x")
    await fake.complete(declined.reference, paid=False)
    await fake.complete(odd.reference, paid=True, amount_rial=10_005)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(FakeGatewaySession)
            .where(FakeGatewaySession.reference == expired.reference)
            .values(expires_at=utc_now() - timedelta(seconds=1))
        )

    failed = await fake.verify(reference=declined.reference, amount=1_000)
    assert (failed.outcome, failed.failure_reason) == (VerifyOutcome.FAILED, "declined")
    mismatch = await fake.verify(reference=odd.reference, amount=1_000)
    assert (mismatch.outcome, mismatch.amount) == (VerifyOutcome.PAID, None)
    late = await fake.verify(reference=expired.reference, amount=1_000)
    assert (late.outcome, late.failure_reason) == (VerifyOutcome.FAILED, "session_expired")
    unknown = await fake.verify(reference="FAKE-nope", amount=1_000)
    assert unknown.outcome is VerifyOutcome.PENDING  # never invents a result


def test_the_fake_parses_only_the_reference(fake_parser: FakeGateway) -> None:
    assert fake_parser.parse_callback({"reference": "FAKE-1", "status": "paid"}) == "FAKE-1"
    assert fake_parser.parse_callback({"reference": "a b"}) is None
    assert fake_parser.parse_callback({}) is None
    assert fake_parser.redact_callback({"reference": "R", "card": "6037991234567890"}) == {
        "reference": "R"
    }


@pytest.fixture
def fake_parser() -> FakeGateway:
    return FakeGateway(None, base_url="http://x", session_seconds=60)  # type: ignore[arg-type]


# --- the payments table ----------------------------------------------------------------


async def _payment(session: AsyncSession, order_id: UUID, **values: object) -> Payment:
    fields: dict[str, object] = {
        "order_id": order_id,
        "gateway": "fake",
        "amount": 1_000,
        "idempotency_key": str(uuid4()),
    }
    payment = Payment(**(fields | values))
    session.add(payment)
    await session.flush()
    return payment


@integration
@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"amount": 0}, "amount_positive"),
        ({"status": "unpaid"}, "valid_status"),
        ({"status": "paid"}, "paid_has_paid_at"),
        ({"paid_at": utc_now()}, "paid_at_when_paid"),
        ({"status": "failed"}, "closed_has_reason"),
        ({"failure_reason": "x"}, "closed_has_reason"),
        ({"gateway_reference": "R", "gateway_expires_at": utc_now()}, "redirect_with_reference"),
        ({"gateway_reference": "R", "redirect_url": "u"}, "expires_with_reference"),
        ({"status": "refund_required", "failure_reason": "x"}, "refund_was_paid"),
        ({"paid_amount": -1}, "paid_amount_range"),
        (
            {"gateway_reference": "a b", "redirect_url": "u", "gateway_expires_at": utc_now()},
            "gateway_reference_format",
        ),
    ],
)
async def test_payment_checks(
    make_order: MakeOrder, db_engine: AsyncEngine, values: dict[str, object], constraint: str
) -> None:
    order_id = await make_order()
    async with AsyncSession(db_engine) as session, session.begin():
        with pytest.raises(IntegrityError, match=constraint):
            await _payment(session, order_id, **values)


@integration
async def test_one_pending_payment_per_order_and_unique_references(
    make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    first, second = await make_order(), await make_order()
    async with AsyncSession(db_engine) as session, session.begin():
        await _payment(session, first)
        await _payment(session, first, status="failed", failure_reason="declined")
        with pytest.raises(IntegrityError, match="uq_payments_one_pending_per_order"):
            async with session.begin_nested():
                await _payment(session, first)
        await _payment(
            session, second, gateway_reference="R-1", redirect_url="u", gateway_expires_at=utc_now()
        )
        with pytest.raises(IntegrityError, match="uq_payments_gateway_reference"):
            async with session.begin_nested():
                await _payment(
                    session,
                    second,
                    status="failed",
                    failure_reason="x",
                    gateway_reference="R-1",
                    redirect_url="u",
                    gateway_expires_at=utc_now(),
                )


@integration
async def test_the_lifecycle_updates_pass_the_checks(
    make_order: MakeOrder, db_engine: AsyncEngine
) -> None:
    order_id = await make_order()
    async with AsyncSession(db_engine) as session, session.begin():
        late = await _payment(session, order_id, status="failed", failure_reason="superseded")
        # failed → paid (late verify) clears the reason in the same update.
        late.status, late.failure_reason, late.paid_at, late.paid_amount = (
            "paid",
            None,
            utc_now(),
            1_000,
        )
        await session.flush()
        twice = await _payment(session, order_id)
        twice.status, twice.failure_reason, twice.paid_at = (
            "refund_required",
            "duplicate_payment",
            utc_now(),
        )
        await session.flush()
        stuck = await _payment(session, order_id, status="failed", failure_reason="x")
        stuck.status, stuck.failure_reason, stuck.paid_at = (
            "refund_required",
            "reservation_expired",
            utc_now(),
        )
        await session.flush()


@integration
async def test_payment_event_checks(db_engine: AsyncEngine) -> None:
    async with AsyncSession(db_engine) as session, session.begin():
        for values, constraint in (
            ({"kind": "reconcile"}, "valid_kind"),
            ({"kind": "callback", "gateway": "Bad"}, "gateway_format"),
        ):
            with pytest.raises(IntegrityError, match=constraint):
                async with session.begin_nested():
                    session.add(PaymentEvent(**({"gateway": "fake", "payload": {}} | values)))
                    await session.flush()
