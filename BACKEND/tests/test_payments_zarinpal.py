"""The purchase flow with the Zarinpal adapter against its mocked API (PAY-07, ADR-064).

Same endpoints and contracts as with the fake gateway (init, callback ``{reference}`` →
``{outcome}``); the frontend result page forwards Zarinpal's ``Authority`` as the
reference. Covers success, NOK/cancel, verify failure, amount mismatch, 101/duplicates,
concurrency, a late success after the reservation expired, IDOR and tampered amounts.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from conftest import Catalog
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_cancel import _expire_now, _placed, _reservation
from test_orders_create import (
    MakeBuyer,
    _error,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)
from test_payments_callback import _callback, _item, _order_ready, _started
from test_payments_init import _app, _init, _order, _payments
from zarinpal_mock import CARD_HASH, MASKED_PAN, MERCHANT, ZarinpalMock, error_body

from app.core.time import utc_now
from app.db.models import AuditLog, Order, Payment, PaymentEvent
from app.modules.payments.gateways import close_payment_gateway
from app.modules.payments.gateways.zarinpal import (
    INQUIRY_PATH,
    REQUEST_PATH,
    VERIFY_PATH,
    ZarinpalGateway,
)
from app.modules.payments.jobs import reconcile_pending_payments

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures


class Zarinpal:
    def __init__(self, mock: ZarinpalMock, gateway: ZarinpalGateway) -> None:
        self.mock = mock
        self.gateway = gateway


@pytest_asyncio.fixture
async def zarinpal(auth_client: AsyncClient) -> AsyncIterator[Zarinpal]:
    """The application's gateway is Zarinpal (mocked API) for this test."""
    app = _app(auth_client)
    saved = getattr(app.state, "payment_gateway", None)
    mock = ZarinpalMock()
    gateway = mock.gateway()
    app.state.payment_gateway = gateway
    try:
        yield Zarinpal(mock, gateway)
    finally:
        app.state.payment_gateway = saved
        await close_payment_gateway(gateway)


async def _paid_order(
    catalog: Catalog, buyer: MakeBuyer, zarinpal: Zarinpal
) -> tuple[Any, Any, Payment]:
    variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    return variant, ready, payment


async def _audits(engine: AsyncEngine, payment: Payment) -> list[AuditLog]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_id == payment.id)
                .order_by(AuditLog.created_at)
            )
        )


async def _reconcile(client: AsyncClient, gateway: ZarinpalGateway, **kwargs: Any) -> Any:
    app = _app(client)
    return await reconcile_pending_payments(
        app.state.db_engine,
        gateway,
        app.state.settings,
        now=kwargs.pop("now", utc_now() + timedelta(minutes=10)),
        **kwargs,
    )


# --- success -------------------------------------------------------------------------------


async def test_a_zarinpal_payment_confirms_the_order(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    variant, ready, payment = await _paid_order(catalog, buyer, zarinpal)
    authority = payment.gateway_reference
    assert authority is not None and authority.startswith("S")
    assert payment.gateway == "zarinpal"
    assert payment.redirect_url == f"https://sandbox.zarinpal.com/pg/StartPay/{authority}"
    [request] = zarinpal.mock.calls_to(REQUEST_PATH)
    assert (request["amount"], request["currency"]) == (payment.amount * 10, "IRR")

    zarinpal.mock.pay(authority)
    # The result page forwards ?Authority=…&Status=OK as the reference.
    response = await _callback(auth_client, authority, status="OK")

    assert (response.status_code, response.json()["outcome"]) == (200, "success")
    [paid] = await _payments(db_engine, payment.order_id)
    assert (paid.status, paid.paid_amount) == ("paid", payment.amount)
    assert paid.raw_event is not None
    assert paid.raw_event["tracking_code"] == str(zarinpal.mock.sessions[authority].ref_id)
    assert paid.raw_event["card_pan"] == MASKED_PAN
    order = await _order(db_engine, payment.order_id)
    assert (order.status, order.payment_status) == ("confirmed", "paid")
    assert (await _reservation(db_engine, payment.order_id)).status == "committed"
    assert (await _item(db_engine, variant)).total_quantity == 4

    # The gateway (or a reload) repeats it: 101, applied once.
    again = await _callback(auth_client, authority)
    assert again.json()["outcome"] == "success"
    assert [b["amount"] for b in zarinpal.mock.calls_to(VERIFY_PATH)] == [payment.amount * 10] * 2
    assert (await _item(db_engine, variant)).total_quantity == 4
    assert [p.status for p in await _payments(db_engine, payment.order_id)] == ["paid"]


async def test_concurrent_callbacks_apply_once(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    variant, ready, payment = await _paid_order(catalog, buyer, zarinpal)
    zarinpal.mock.pay(payment.gateway_reference or "")

    responses = await asyncio.gather(
        *(_callback(auth_client, payment.gateway_reference) for _ in range(3))
    )

    assert [r.json()["outcome"] for r in responses] == ["success"] * 3
    # One verify event per applied callback: the first verify settles, the others see 101.
    assert sorted(await _events(db_engine, payment, "verify")) == [100, 101, 101]
    assert (await _item(db_engine, variant)).total_quantity == 4
    assert [p.status for p in await _payments(db_engine, payment.order_id)] == ["paid"]


async def test_a_concurrent_callback_whose_verify_fails_changes_nothing(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    _, _, payment = await _paid_order(catalog, buyer, zarinpal)
    zarinpal.mock.pay(payment.gateway_reference or "")
    real = zarinpal.mock.handle
    calls = 0

    def second_is_broken(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == VERIFY_PATH:
            calls += 1
            if calls == 2:
                return httpx.Response(200, json=error_body(-52))
        return real(request)

    gateway = ZarinpalGateway(
        merchant_id=MERCHANT,
        sandbox=True,
        timeout_seconds=5,
        transport=httpx.MockTransport(second_is_broken),
    )
    _app(auth_client).state.payment_gateway = gateway
    try:
        responses = await asyncio.gather(
            *(_callback(auth_client, payment.gateway_reference) for _ in range(2))
        )
    finally:
        _app(auth_client).state.payment_gateway = zarinpal.gateway
        await close_payment_gateway(gateway)

    # -52 decides nothing: that callback is pending (or sees the other's success).
    assert sorted(r.json()["outcome"] for r in responses) in (
        ["pending", "success"],
        ["success", "success"],
    )
    assert [p.status for p in await _payments(db_engine, payment.order_id)] == ["paid"]


async def _events(engine: AsyncEngine, payment: Payment, kind: str) -> list[Any]:
    async with AsyncSession(engine) as session:
        payloads: Any = await session.scalars(
            select(PaymentEvent.payload).where(
                PaymentEvent.payment_id == payment.id, PaymentEvent.kind == kind
            )
        )
        return [payload.get("code") for payload in payloads]


# --- not paid ------------------------------------------------------------------------------


async def test_a_cancelled_payment_fails_and_the_order_can_be_paid_again(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    _, ready, payment = await _paid_order(catalog, buyer, zarinpal)
    zarinpal.mock.cancel(payment.gateway_reference or "")

    response = await _callback(auth_client, payment.gateway_reference, status="NOK")

    assert response.json()["outcome"] == "failed"
    [failed] = await _payments(db_engine, payment.order_id)
    assert (failed.status, failed.failure_reason) == ("failed", "declined")
    order = await _order(db_engine, payment.order_id)
    assert (order.status, order.payment_status) == ("pending_payment", "failed")

    retry = await _init(ready, payment.order_id)
    assert retry.status_code == 201, retry.text
    second = (await _payments(db_engine, payment.order_id))[-1]
    assert second.gateway_reference not in (None, payment.gateway_reference)
    assert retry.json()["redirect_url"].endswith(f"/pg/StartPay/{second.gateway_reference}")
    zarinpal.mock.pay(second.gateway_reference or "")
    assert (await _callback(auth_client, second.gateway_reference)).json()["outcome"] == "success"


async def test_status_ok_is_never_trusted(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    _, _, payment = await _paid_order(catalog, buyer, zarinpal)

    # Still at the bank (IN_BANK), whatever the forged Status says.
    still = await _callback(auth_client, payment.gateway_reference, status="OK")
    assert still.json()["outcome"] == "pending"
    assert (await _payments(db_engine, payment.order_id))[0].status == "pending"

    zarinpal.mock.cancel(payment.gateway_reference or "")
    forged = await _callback(auth_client, payment.gateway_reference, status="OK")
    assert forged.json()["outcome"] == "failed"
    assert (await _payments(db_engine, payment.order_id))[0].status == "failed"


async def test_an_unreachable_verify_is_503_then_the_retry_succeeds(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    _, _, payment = await _paid_order(catalog, buyer, zarinpal)
    zarinpal.mock.pay(payment.gateway_reference or "")
    down = httpx.ConnectError("unreachable")
    zarinpal.mock.script(VERIFY_PATH, down, down, down)

    _error(
        await _callback(auth_client, payment.gateway_reference), 503, "PAYMENT_GATEWAY_UNAVAILABLE"
    )
    assert (await _payments(db_engine, payment.order_id))[0].status == "pending"

    assert (await _callback(auth_client, payment.gateway_reference)).json()["outcome"] == "success"


async def test_a_refused_request_fails_the_attempt_with_503(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    zarinpal.mock.script(REQUEST_PATH, (200, error_body(-14)))

    _error(await _init(ready, order_id), 503, "PAYMENT_GATEWAY_UNAVAILABLE")

    [failed] = await _payments(db_engine, order_id)
    assert (failed.status, failed.failure_reason) == ("failed", "gateway_error")
    assert len(zarinpal.mock.calls_to(REQUEST_PATH)) == 1
    assert (await _init(ready, order_id)).status_code == 201  # the next try works


# --- amounts -------------------------------------------------------------------------------


async def test_an_amount_zarinpal_rejects_fails_without_a_refund_case(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, ready, payment = await _paid_order(catalog, buyer, zarinpal)
    zarinpal.mock.pay(payment.gateway_reference or "")
    async with AsyncSession(db_engine) as session, session.begin():
        # The stored amount no longer matches what the gateway asked the customer for.
        await session.execute(
            update(Payment).where(Payment.id == payment.id).values(amount=payment.amount + 1)
        )

    with caplog.at_level(logging.ERROR, logger="app.modules.payments.gateways.zarinpal"):
        response = await _callback(auth_client, payment.gateway_reference)

    assert response.json()["outcome"] == "failed"
    [failed] = await _payments(db_engine, payment.order_id)
    assert (failed.status, failed.failure_reason) == ("failed", "gateway_amount_rejected")
    assert failed.paid_at is None  # nothing was settled: no refund case
    assert any(r.getMessage() == "payment.zarinpal_amount_rejected" for r in caplog.records)
    audit = [a for a in await _audits(db_engine, payment) if a.action == "payment.status_changed"]
    diff = audit[-1].metadata_["diff"]
    assert (diff["status"]["after"], diff["reason"]["after"]) == (
        "failed",
        "gateway_amount_rejected",
    )
    order = await _order(db_engine, payment.order_id)
    assert (order.status, order.payment_status) == ("pending_payment", "failed")
    assert (await _reservation(db_engine, payment.order_id)).status == "active"


async def test_a_tampered_order_total_is_refund_required(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    variant, ready, payment = await _paid_order(catalog, buyer, zarinpal)
    zarinpal.mock.pay(payment.gateway_reference or "")
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(Order)
            .where(Order.id == payment.order_id)
            .values(
                grand_total=Order.grand_total + 1_000,
                shipping_amount=Order.shipping_amount + 1_000,
            )
        )

    response = await _callback(auth_client, payment.gateway_reference)

    # Zarinpal took the stored amount, but it is not the order's total: money to return.
    assert response.json()["outcome"] == "failed"
    [mismatch] = await _payments(db_engine, payment.order_id)
    assert (mismatch.status, mismatch.failure_reason) == ("refund_required", "amount_mismatch")
    assert (await _item(db_engine, variant)).total_quantity == 5  # nothing consumed


async def test_the_client_never_sets_the_amount(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, zarinpal: Zarinpal
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    headers = ready.account.headers | {"Idempotency-Key": "k-" + str(order_id)}

    response = await auth_client.post(
        "/api/v1/payments/init",
        json={"order_id": str(order_id), "amount": 1, "currency": "IRT"},
        headers=headers,
    )

    _error(response, 400, "VALIDATION_ERROR")
    assert zarinpal.mock.calls_to(REQUEST_PATH) == []


async def test_an_order_above_the_payment_cap_is_refused_before_the_gateway(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    _, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    total = (await _order(db_engine, order_id)).grand_total
    app = _app(auth_client)
    saved = app.state.settings
    key = f"cap-{order_id}"
    app.state.settings = saved.model_copy(update={"payment_max_amount": total - 1})
    try:
        response = await _init(ready, order_id, key)
    finally:
        app.state.settings = saved

    _error(response, 422, "PAYMENT_AMOUNT_TOO_LARGE")
    assert response.json()["error"]["details"] == [
        {"field": "order", "type": "amount_too_large", "maximum": total - 1}
    ]
    assert await _payments(db_engine, order_id) == []
    assert zarinpal.mock.calls_to(REQUEST_PATH) == []
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("pending_payment", "unpaid")
    assert (await _reservation(db_engine, order_id)).status == "active"

    # Exactly the cap is allowed, with the same key (a 422 stores nothing).
    app.state.settings = saved.model_copy(update={"payment_max_amount": total})
    try:
        assert (await _init(ready, order_id, key)).status_code == 201
    finally:
        app.state.settings = saved


# --- late success --------------------------------------------------------------------------


async def test_a_late_success_after_the_reservation_expired_is_refund_required(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    variant, ready, payment = await _paid_order(catalog, buyer, zarinpal)
    zarinpal.mock.pay(payment.gateway_reference or "")
    await _expire_now(db_engine, payment.order_id)

    with caplog.at_level(logging.WARNING, logger="app.modules.payments.processing"):
        response = await _callback(auth_client, payment.gateway_reference)

    assert response.json()["outcome"] == "failed"
    [refund] = await _payments(db_engine, payment.order_id)
    assert (refund.status, refund.failure_reason) == ("refund_required", "reservation_expired")
    order = await _order(db_engine, payment.order_id)
    assert (order.status, order.cancel_reason) == ("cancelled", "expired")
    assert (await _item(db_engine, variant)).total_quantity == 5
    actions = {a.action for a in await _audits(db_engine, payment)}
    assert "payment.refund_required" in actions
    assert any(r.getMessage() == "payment.refund_required" for r in caplog.records)


# --- IDOR ----------------------------------------------------------------------------------


async def test_no_one_pays_or_reads_another_customers_payment(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    _, ready, payment = await _paid_order(catalog, buyer, zarinpal)
    _, other = await _order_ready(catalog, buyer)

    _error(await _init(other, payment.order_id), 404, "NOT_FOUND")
    # A well-formed authority the shop never issued, or another gateway's reference.
    for reference in ("S" + "0" * 35, "FAKE-abc"):
        _error(await _callback(auth_client, reference), 404, "NOT_FOUND")
    _error(await _callback(auth_client, "has space"), 400, "VALIDATION_ERROR")
    assert [p.id for p in await _payments(db_engine, payment.order_id)] == [payment.id]


# --- reconciliation ------------------------------------------------------------------------


async def test_reconciliation_applies_a_lost_callback(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    _, _, payment = await _paid_order(catalog, buyer, zarinpal)
    zarinpal.mock.pay(payment.gateway_reference or "")  # the customer never comes back

    await _reconcile(auth_client, zarinpal.gateway)

    assert (await _payments(db_engine, payment.order_id))[0].status == "paid"


async def test_broken_payments_never_stop_a_round(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    broken = [(await _paid_order(catalog, buyer, zarinpal))[2] for _ in range(3)]
    for payment in broken:
        zarinpal.mock.verify_codes[payment.gateway_reference or ""] = -52
    _, _, paid = await _paid_order(catalog, buyer, zarinpal)
    zarinpal.mock.pay(paid.gateway_reference or "")

    result = await _reconcile(auth_client, zarinpal.gateway)

    assert result.failed == 0
    assert (await _payments(db_engine, paid.order_id))[0].status == "paid"
    for payment in broken:
        assert (await _payments(db_engine, payment.order_id))[0].status == "pending"


async def test_an_abandoned_payment_paid_late_is_still_applied(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
) -> None:
    _, _, payment = await _paid_order(catalog, buyer, zarinpal)
    assert payment.gateway_expires_at is not None
    # IN_BANK long after the session ended: reconciliation gives up on it.
    late = payment.gateway_expires_at + timedelta(minutes=6)
    await _reconcile(auth_client, zarinpal.gateway, now=late)
    [abandoned] = await _payments(db_engine, payment.order_id)
    assert (abandoned.status, abandoned.failure_reason) == ("failed", "abandoned")
    assert zarinpal.mock.calls_to(INQUIRY_PATH)

    # The customer did pay after all: verify (100) is applied to the failed attempt.
    zarinpal.mock.pay(payment.gateway_reference or "")
    assert (await _callback(auth_client, payment.gateway_reference)).json()["outcome"] == "success"
    assert (await _payments(db_engine, payment.order_id))[0].status == "paid"
    # A 101 afterwards on the now paid row changes nothing.
    assert (await _callback(auth_client, payment.gateway_reference)).json()["outcome"] == "success"


# --- secrets -------------------------------------------------------------------------------


async def test_the_merchant_id_and_card_hash_are_never_stored_or_logged(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
    zarinpal: Zarinpal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        _, _, ok = await _paid_order(catalog, buyer, zarinpal)
        zarinpal.mock.pay(ok.gateway_reference or "")
        await _callback(auth_client, ok.gateway_reference, card="6037991234567890")
        _, _, bad = await _paid_order(catalog, buyer, zarinpal)
        zarinpal.mock.verify_codes[bad.gateway_reference or ""] = -11
        await _callback(auth_client, bad.gateway_reference)
        zarinpal.mock.verify_codes[bad.gateway_reference or ""] = -9
        await _callback(auth_client, bad.gateway_reference)

    assert MERCHANT not in caplog.text and CARD_HASH not in caplog.text
    async with AsyncSession(db_engine) as session:
        events = [str(e.payload) for e in await session.scalars(select(PaymentEvent))]
        raws = [str(p.raw_event) for p in await session.scalars(select(Payment))]
    stored = " ".join(events + raws)
    assert MERCHANT not in stored and CARD_HASH not in stored
    assert "6037991234567890" not in stored
