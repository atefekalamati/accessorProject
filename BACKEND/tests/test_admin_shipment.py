"""Staff move the shipment and cancel unpaid orders (ADM-02, ADR-047, ADR-050)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import Account, Catalog, MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_cancel import _placed, _redemption_status, _reservation
from test_orders_create import (
    API,
    ORDERS,
    Buyer,
    MakeBuyer,
    _error,
    _orders_go_first,
    _with_code,
    buyer,
    codes,
    methods,
    shopper,
)
from test_payments_callback import _callback, _complete, _order_ready, _started

from app.db.models import AuditLog, Order, OrderStatusHistory, Payment, Shipment

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

ADMIN_ORDERS = f"{API}/admin/orders"


async def _paid(auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer) -> tuple[Buyer, UUID]:
    _variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)
    settled = await _callback(auth_client, payment.gateway_reference)
    assert settled.json()["outcome"] == "success", settled.text
    return ready, order_id


async def _ship(
    client: AsyncClient, staff: Account, order_id: UUID, status: str, **body: Any
) -> Response:
    return await client.patch(
        f"{ADMIN_ORDERS}/{order_id}/shipment",
        json={"status": status} | body,
        headers=staff.headers,
    )


async def _history(engine: AsyncEngine, order_id: UUID) -> list[OrderStatusHistory]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(OrderStatusHistory)
                .where(OrderStatusHistory.order_id == order_id)
                .order_by(OrderStatusHistory.created_at, OrderStatusHistory.id)
            )
        )


async def test_ship_and_deliver_completes_the_order(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    ready, order_id = await _paid(auth_client, catalog, buyer)

    preparing = await _ship(auth_client, admin, order_id, "preparing")
    assert preparing.status_code == 200, preparing.text
    assert preparing.headers["cache-control"] == "no-store"
    assert preparing.json()["shipment"] == {
        "tracking_code": None,
        "shipped_at": None,
        "delivered_at": None,
    }
    _error(await _ship(auth_client, admin, order_id, "shipped"), 400, "VALIDATION_ERROR")
    shipped = await _ship(auth_client, admin, order_id, "shipped", tracking_code="  IR123  ")
    assert shipped.status_code == 200, shipped.text
    assert shipped.json()["shipment"]["tracking_code"] == "IR123"
    delivered = await _ship(auth_client, admin, order_id, "delivered")

    assert delivered.status_code == 200, delivered.text
    body = delivered.json()
    assert (body["status"], body["shipment_status"]) == ("completed", "delivered")
    assert body["shipment"]["delivered_at"] >= body["shipment"]["shipped_at"]
    moves = [
        (row.field, row.new_status, row.actor_user_id)
        for row in await _history(db_engine, order_id)
        if row.actor_user_id == admin.id
    ]
    assert moves == [
        ("shipment", "preparing", admin.id),
        ("shipment", "shipped", admin.id),
        ("shipment", "delivered", admin.id),
        ("order", "completed", admin.id),
    ]
    async with AsyncSession(db_engine) as session:
        audits = list(
            await session.scalars(
                select(AuditLog.action).where(
                    AuditLog.entity_id == order_id, AuditLog.action == "shipment.updated"
                )
            )
        )
    assert len(audits) == 3
    # The customer sees the shipment too.
    mine = await auth_client.get(f"{ORDERS}/{body['order_number']}", headers=ready.account.headers)
    assert mine.json()["shipment"]["tracking_code"] == "IR123"


async def test_invalid_moves_are_422_and_change_nothing(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    _variant, ready = await _order_ready(catalog, buyer)
    unpaid = await _placed(ready)
    _error(await _ship(auth_client, admin, unpaid, "preparing"), 422, "INVALID_STATE_TRANSITION")

    _ready, paid = await _paid(auth_client, catalog, buyer)
    _error(
        await _ship(auth_client, admin, paid, "shipped", tracking_code="X1"),
        422,
        "INVALID_STATE_TRANSITION",
    )
    assert (await _ship(auth_client, admin, paid, "preparing")).status_code == 200
    _error(await _ship(auth_client, admin, paid, "preparing"), 422, "INVALID_STATE_TRANSITION")
    _error(await _ship(auth_client, admin, paid, "delivered"), 422, "INVALID_STATE_TRANSITION")
    for body in (
        {"status": "lost"},
        {"status": "preparing", "tracking_code": "X1"},
        {"status": "shipped", "tracking_code": "   "},
        {"status": "shipped", "tracking_code": "X" * 65},
        {"status": "shipped", "tracking_code": "A\u0000B"},
        {"status": "shipped", "tracking_code": "A\nB"},
        {"status": "preparing", "note": "x"},
    ):
        response = await auth_client.patch(
            f"{ADMIN_ORDERS}/{paid}/shipment", json=body, headers=admin.headers
        )
        _error(response, 400, "VALIDATION_ERROR")
    _error(await _ship(auth_client, admin, uuid4(), "preparing"), 404, "NOT_FOUND")


async def test_two_concurrent_moves_apply_once(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    _ready, order_id = await _paid(auth_client, catalog, buyer)
    assert (await _ship(auth_client, admin, order_id, "preparing")).status_code == 200

    responses = await asyncio.gather(
        *(_ship(auth_client, admin, order_id, "shipped", tracking_code=f"T{n}") for n in range(2))
    )

    assert sorted(response.status_code for response in responses) == [200, 422]
    [winner] = [response for response in responses if response.status_code == 200]
    async with AsyncSession(db_engine) as session:
        stored = await session.scalar(select(Shipment).where(Shipment.order_id == order_id))
        audits = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == order_id, AuditLog.action == "shipment.updated"
                )
            )
        )
    assert stored is not None
    assert stored.tracking_code == winner.json()["shipment"]["tracking_code"]
    shipped = [a for a in audits if a.metadata_["diff"]["status"]["after"] == "shipped"]
    assert len(shipped) == 1
    rows = [row for row in await _history(db_engine, order_id) if row.new_status == "shipped"]
    assert len(rows) == 1


async def test_staff_cancel_frees_stock_and_code_with_the_admin_reason(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    codes: Any,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    _variant, ready = await _order_ready(catalog, buyer, quantity=2)
    order_id = await _placed(ready, await _with_code(auth_client, ready, await codes(value=1_000)))
    url = f"{ADMIN_ORDERS}/{order_id}/cancel"

    response = await auth_client.post(url, headers=admin.headers)
    again = await auth_client.post(url, headers=admin.headers)

    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["cancel_reason"]) == ("cancelled", "admin")
    assert again.status_code == 200 and again.json() == response.json()
    assert (await _reservation(db_engine, order_id)).status == "released"
    assert await _redemption_status(db_engine, order_id) == "released"
    [cancel] = [row for row in await _history(db_engine, order_id) if row.new_status == "cancelled"]
    assert (cancel.actor_user_id, cancel.reason) == (admin.id, "cancelled by staff")


async def test_staff_cancel_refuses_paid_and_paying_orders(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, make_account: MakeAccount
) -> None:
    admin = await make_account("admin")
    _ready, paid = await _paid(auth_client, catalog, buyer)
    _error(
        await auth_client.post(f"{ADMIN_ORDERS}/{paid}/cancel", headers=admin.headers),
        422,
        "INVALID_STATE_TRANSITION",
    )
    _variant, ready = await _order_ready(catalog, buyer)
    paying = await _placed(ready)
    await _started(ready, paying)
    _error(
        await auth_client.post(f"{ADMIN_ORDERS}/{paying}/cancel", headers=admin.headers),
        409,
        "PAYMENT_IN_PROGRESS",
    )
    _error(
        await auth_client.post(f"{ADMIN_ORDERS}/{uuid4()}/cancel", headers=admin.headers),
        404,
        "NOT_FOUND",
    )


async def test_staff_cancel_racing_the_customer_cancel_applies_once(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    _variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)

    staff, customer = await asyncio.gather(
        auth_client.post(f"{ADMIN_ORDERS}/{order_id}/cancel", headers=admin.headers),
        auth_client.post(f"{ORDERS}/{order_id}/cancel", headers=ready.account.headers),
    )

    assert (staff.status_code, customer.status_code) == (200, 200)
    assert staff.json()["cancel_reason"] == customer.json()["cancel_reason"]
    cancels = [row for row in await _history(db_engine, order_id) if row.new_status == "cancelled"]
    assert len(cancels) == 1


async def _fail_closed(engine: AsyncEngine, order_id: UUID, payment_id: UUID) -> None:
    """The attempt was closed as failed here, while the gateway took the money (a lost
    callback, PAY-04): a later verify reports PAID on a failed payment."""
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            update(Payment)
            .where(Payment.id == payment_id)
            .values(status="failed", failure_reason="request_lost")
        )
        await session.execute(
            update(Order).where(Order.id == order_id).values(payment_status="failed")
        )


async def test_staff_cancel_racing_a_late_success_ends_one_way(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
) -> None:
    admin = await make_account("admin")
    _variant, ready = await _order_ready(catalog, buyer)
    order_id = await _placed(ready)
    payment = await _started(ready, order_id)
    await _complete(auth_client, payment)
    await _fail_closed(db_engine, order_id, payment.id)

    cancel, settled = await asyncio.gather(
        auth_client.post(f"{ADMIN_ORDERS}/{order_id}/cancel", headers=admin.headers),
        _callback(auth_client, payment.gateway_reference),
    )

    assert settled.status_code == 200, settled.text
    async with AsyncSession(db_engine) as session:
        order = await session.get(Order, order_id)
        stored = await session.get(Payment, payment.id)
    assert order is not None and stored is not None
    outcome = (cancel.status_code, order.status, order.payment_status, stored.status)
    # Either the cancel won and the late money must go back, or the payment won and the
    # cancel was refused; never a cancelled order that kept the money as paid.
    assert outcome in {
        (200, "cancelled", "refund_required", "refund_required"),
        (422, "confirmed", "paid", "paid"),
    }, outcome


async def test_permissions(auth_client: AsyncClient, make_account: MakeAccount) -> None:
    support = await make_account("support")
    editor = await make_account("content_manager")
    order_id = uuid4()
    for method, url in (
        ("PATCH", f"{ADMIN_ORDERS}/{order_id}/shipment"),
        ("POST", f"{ADMIN_ORDERS}/{order_id}/cancel"),
    ):
        body = {"status": "preparing"} if method == "PATCH" else None
        _error(await auth_client.request(method, url, json=body), 401, "UNAUTHORIZED")
        for account in (support, editor):
            response = await auth_client.request(method, url, json=body, headers=account.headers)
            _error(response, 403, "FORBIDDEN")
