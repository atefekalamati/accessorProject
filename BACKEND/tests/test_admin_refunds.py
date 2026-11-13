"""Recording manual refunds: refund_required → refunded (ADM-08, D35, ADR-054)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Account, Catalog, MakeAccount, delete_orders
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_cancel import _expire_now, _placed
from test_orders_create import (
    API,
    Buyer,
    MakeBuyer,
    _error,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)
from test_payments_callback import _callback, _complete, _order_ready, _started
from test_payments_init import _fake, _order

from app.db.models import AuditLog, OrderStatusHistory, Payment

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

PAYMENTS = f"{API}/admin/payments"


@pytest_asyncio.fixture
async def refunder(make_account: MakeAccount, db_engine: AsyncEngine) -> AsyncIterator[Account]:
    """An admin; the orders it refunded go first (payments.refunded_by is RESTRICT)."""
    admin = await make_account("admin")
    yield admin
    async with AsyncSession(db_engine) as session, session.begin():
        ids = list(
            await session.scalars(
                select(Payment.order_id).where(Payment.refunded_by == admin.id).distinct()
            )
        )
        await delete_orders(session, ids)


async def _refund(
    client: AsyncClient, staff: Account, payment_id: UUID, reference: str, **body: Any
) -> Response:
    return await client.post(
        f"{PAYMENTS}/{payment_id}/refund",
        json={"refund_reference": reference} | body,
        headers=staff.headers,
    )


async def _payment(engine: AsyncEngine, payment_id: UUID) -> Payment:
    async with AsyncSession(engine) as session:
        payment = await session.get(Payment, payment_id)
        assert payment is not None
        return payment


async def _audits(engine: AsyncEngine, payment_id: UUID) -> list[AuditLog]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == payment_id, AuditLog.action == "payment.refunded"
                )
            )
        )


async def _late_paid(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> tuple[Buyer, UUID, Payment]:
    """Paid after the reservation expired: order cancelled, payment refund_required."""
    _variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)
    await _expire_now(db_engine, order_id)
    settled = await _callback(auth_client, payment.gateway_reference)
    assert settled.json()["outcome"] == "failed", settled.text
    return ready, order_id, payment


async def _another_paid_attempt(
    auth_client: AsyncClient, db_engine: AsyncEngine, order_id: UUID, amount: int
) -> UUID:
    """A second gateway session of the same order (another tab) that the customer paid."""
    fake = _fake(auth_client)
    payment_id = uuid4()
    answer = await fake.request(payment_id=payment_id, amount=amount, callback_url="x")
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(
            Payment(
                id=payment_id,
                order_id=order_id,
                gateway="fake",
                idempotency_key=f"tab-{payment_id}",
                amount=amount,
                gateway_reference=answer.reference,
                redirect_url=answer.redirect_url,
                gateway_expires_at=answer.expires_at,
            )
        )
    assert await fake.complete(answer.reference, paid=True)
    settled = await _callback(auth_client, answer.reference)
    assert settled.status_code == 200, settled.text
    return payment_id


async def test_a_full_refund_of_the_gateway_amount(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    refunder: Account,
    db_engine: AsyncEngine,
) -> None:
    _ready, order_id, payment = await _late_paid(auth_client, catalog, buyer, db_engine)
    reference = f"BANK-{uuid4().hex[:12]}"
    _error(
        await _refund(auth_client, refunder, payment.id, reference, amount=1),
        422,
        "BUSINESS_RULE_VIOLATION",
        "amount_not_allowed",
    )

    response = await _refund(auth_client, refunder, payment.id, reference, note=" paid by card ")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["status"], body["refund_reference"]) == ("refunded", reference)
    assert (body["refund_amount"], body["refund_amount_source"]) == (payment.amount, "gateway")
    assert body["refunded_by"] == str(refunder.id) and body["refunded_at"]
    stored = await _payment(db_engine, payment.id)
    assert (stored.failure_reason, stored.paid_amount) == ("reservation_expired", payment.amount)
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("cancelled", "refunded")
    [audit] = await _audits(db_engine, payment.id)
    assert audit.actor_user_id == refunder.id
    assert audit.metadata_["diff"]["note"]["after"] == "paid by card"
    async with AsyncSession(db_engine) as session:
        moved = (
            await session.scalars(
                select(OrderStatusHistory).where(
                    OrderStatusHistory.order_id == order_id,
                    OrderStatusHistory.new_status == "refunded",
                )
            )
        ).one()
    assert moved.actor_user_id == refunder.id

    # Idempotent per reference; another reference is a conflict.
    again = await _refund(auth_client, refunder, payment.id, reference)
    assert again.status_code == 200 and again.json() == body
    assert len(await _audits(db_engine, payment.id)) == 1
    _error(await _refund(auth_client, refunder, payment.id, "OTHER-1"), 409, "CONFLICT")
    # A late or repeated callback never reopens it.
    late = await _callback(auth_client, payment.gateway_reference)
    assert late.json()["outcome"] == "failed"  # the order is no longer paid
    assert (await _payment(db_engine, payment.id)).status == "refunded"
    listed = await auth_client.get(
        PAYMENTS, params={"status": "refunded", "limit": 100}, headers=refunder.headers
    )
    assert str(payment.id) in {row["id"] for row in listed.json()["items"]}


async def test_an_unknown_gateway_amount_needs_the_amount_staff_paid(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    refunder: Account,
    db_engine: AsyncEngine,
) -> None:
    _variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    # 5 rial more than asked: not a whole toman, so the gateway figure is unknown.
    await _complete(auth_client, payment, amount_rial=payment.amount * 10 + 5)
    settled = await _callback(auth_client, payment.gateway_reference)
    assert settled.json()["outcome"] == "failed"
    assert (await _payment(db_engine, payment.id)).paid_amount is None
    order = await _order(db_engine, order_id)

    for amount, kind in ((None, "amount_required"), (order.grand_total + 1, "amount_too_large")):
        extra = {} if amount is None else {"amount": amount}
        _error(
            await _refund(auth_client, refunder, payment.id, "MANUAL-1", **extra),
            422,
            "BUSINESS_RULE_VIOLATION",
            kind,
        )
    for bad in (0, -5, "100", 1.5):
        response = await _refund(auth_client, refunder, payment.id, "MANUAL-1", amount=bad)
        _error(response, 400, "VALIDATION_ERROR")

    response = await _refund(auth_client, refunder, payment.id, "MANUAL-1", amount=95_000)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["refund_amount"], body["refund_amount_source"]) == (95_000, "admin_entered")
    [audit] = await _audits(db_engine, payment.id)
    diff = audit.metadata_["diff"]
    assert diff["refund_amount_source"]["after"] == "admin_entered"
    # The gateway figure is unknown (null), so the diff only carries the entered amount.
    assert diff.get("paid_amount", {}).get("after") is None
    assert diff["refund_amount"]["after"] == 95_000
    # The order was still payable (wrong amount on its live attempt): it is not refunded.
    assert (await _order(db_engine, order_id)).payment_status == "failed"


async def test_a_late_success_reopens_a_refunded_cancelled_order(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    refunder: Account,
    db_engine: AsyncEngine,
) -> None:
    _ready, order_id, first = await _late_paid(auth_client, catalog, buyer, db_engine)
    assert (
        await _refund(auth_client, refunder, first.id, f"R1-{uuid4().hex[:8]}")
    ).status_code == 200
    assert (await _order(db_engine, order_id)).payment_status == "refunded"

    second = await _another_paid_attempt(auth_client, db_engine, order_id, first.amount)

    # Money is owed again: the order shows it (D35), and refunding it settles the order.
    assert (await _payment(db_engine, second)).status == "refund_required"
    assert (await _order(db_engine, order_id)).payment_status == "refund_required"
    assert (
        await _refund(auth_client, refunder, second, f"R2-{uuid4().hex[:8]}")
    ).status_code == 200
    assert (await _order(db_engine, order_id)).payment_status == "refunded"


async def test_the_order_waits_until_every_owed_payment_is_refunded(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    refunder: Account,
    db_engine: AsyncEngine,
) -> None:
    _ready, order_id, first = await _late_paid(auth_client, catalog, buyer, db_engine)
    second = await _another_paid_attempt(auth_client, db_engine, order_id, first.amount)

    assert (
        await _refund(auth_client, refunder, first.id, f"A-{uuid4().hex[:8]}")
    ).status_code == 200
    assert (await _order(db_engine, order_id)).payment_status == "refund_required"
    assert (await _refund(auth_client, refunder, second, f"B-{uuid4().hex[:8]}")).status_code == 200
    assert (await _order(db_engine, order_id)).payment_status == "refunded"


async def test_a_duplicate_on_a_paid_order_leaves_the_order_paid(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    refunder: Account,
    db_engine: AsyncEngine,
) -> None:
    _variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    first = await _started(ready, order_id)
    await _complete(auth_client, first)
    assert (await _callback(auth_client, first.gateway_reference)).json()["outcome"] == "success"
    duplicate = await _another_paid_attempt(auth_client, db_engine, order_id, first.amount)
    assert (await _payment(db_engine, duplicate)).status == "refund_required"

    assert (
        await _refund(auth_client, refunder, duplicate, f"D-{uuid4().hex[:8]}")
    ).status_code == 200
    # Not cancelled: the order keeps its sale, before and after a further late duplicate.
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("confirmed", "paid")
    await _another_paid_attempt(auth_client, db_engine, order_id, first.amount)
    order = await _order(db_engine, order_id)
    assert (order.status, order.payment_status) == ("confirmed", "paid")


async def test_only_refund_required_payments_and_unique_references(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    refunder: Account,
    db_engine: AsyncEngine,
) -> None:
    _variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    pending = await _started(ready, order_id)
    _error(await _refund(auth_client, refunder, pending.id, "X-1"), 422, "INVALID_STATE_TRANSITION")
    _error(await _refund(auth_client, refunder, uuid4(), "X-1"), 404, "NOT_FOUND")

    _r1, _o1, one = await _late_paid(auth_client, catalog, buyer, db_engine)
    _r2, _o2, two = await _late_paid(auth_client, catalog, buyer, db_engine)
    shared = f"SHARED-{uuid4().hex[:8]}"
    assert (await _refund(auth_client, refunder, one.id, shared)).status_code == 200
    _error(await _refund(auth_client, refunder, two.id, shared), 409, "CONFLICT")
    assert (await _payment(db_engine, two.id)).status == "refund_required"
    for body in (
        {"refund_reference": ""},
        {"refund_reference": "   "},
        {"refund_reference": "A\u0000B"},
        {"refund_reference": "A\u0085B"},
        {"refund_reference": "A\u2028B"},
        {"refund_reference": "X" * 101},
        {"refund_reference": "OK", "status": "refunded"},
        {},
    ):
        response = await auth_client.post(
            f"{PAYMENTS}/{two.id}/refund", json=body, headers=refunder.headers
        )
        _error(response, 400, "VALIDATION_ERROR")


async def test_concurrent_refunds_write_once(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    refunder: Account,
    db_engine: AsyncEngine,
) -> None:
    _r1, _o1, one = await _late_paid(auth_client, catalog, buyer, db_engine)
    same = f"SAME-{uuid4().hex[:8]}"
    responses = await asyncio.gather(
        *(_refund(auth_client, refunder, one.id, same) for _ in range(3))
    )
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert len(await _audits(db_engine, one.id)) == 1

    _r2, _o2, two = await _late_paid(auth_client, catalog, buyer, db_engine)
    racing = await asyncio.gather(
        _refund(auth_client, refunder, two.id, f"P-{uuid4().hex[:8]}"),
        _refund(auth_client, refunder, two.id, f"Q-{uuid4().hex[:8]}"),
    )
    assert sorted(response.status_code for response in racing) == [200, 409]

    # Two payments racing for one reference: one gets it.
    _r3, _o3, three = await _late_paid(auth_client, catalog, buyer, db_engine)
    _r4, _o4, four = await _late_paid(auth_client, catalog, buyer, db_engine)
    contested = f"RACE-{uuid4().hex[:8]}"
    contending = await asyncio.gather(
        _refund(auth_client, refunder, three.id, contested),
        _refund(auth_client, refunder, four.id, contested),
    )
    assert sorted(response.status_code for response in contending) == [200, 409]


async def test_permissions(auth_client: AsyncClient, make_account: MakeAccount) -> None:
    url = f"{PAYMENTS}/{uuid4()}/refund"
    body = {"refund_reference": "X-1"}
    _error(await auth_client.post(url, json=body), 401, "UNAUTHORIZED")
    for role in ("support", "content_manager", "customer"):
        account = await make_account(role)
        _error(await auth_client.post(url, json=body, headers=account.headers), 403, "FORBIDDEN")


async def test_a_zero_gateway_amount_has_nothing_to_refund(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    refunder: Account,
    db_engine: AsyncEngine,
) -> None:
    _variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment, amount_rial=0)
    assert (await _callback(auth_client, payment.gateway_reference)).json()["outcome"] == "failed"
    assert (await _payment(db_engine, payment.id)).paid_amount == 0

    for extra in ({}, {"amount": 1}):
        _error(
            await _refund(auth_client, refunder, payment.id, "ZERO-1", **extra),
            422,
            "BUSINESS_RULE_VIOLATION",
            "nothing_to_refund",
        )
    assert (await _payment(db_engine, payment.id)).status == "refund_required"
