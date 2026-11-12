"""Customer cancel, expiry cancels the order, and the purchase flow end to end (ORD-06).

ADR-048 lock order on every path; ADR-050 cancel semantics.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Catalog, MakeAccount, delete_orders
from httpx import AsyncClient, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_cart_merge import _guest_cart, _login, _mobile
from test_checkout_validate import ADDRESS
from test_orders_create import (
    API,
    ORDERS,
    VALIDATE,
    Buyer,
    MakeBuyer,
    _count,
    _error,
    _orders_go_first,
    _with_code,
    buyer,
    codes,
    methods,
    shopper,
)

from app.core.time import utc_now
from app.db.models import (
    Address,
    AuditLog,
    Cart,
    DiscountRedemption,
    InventoryItem,
    InventoryReservation,
    Order,
    OrderStatusHistory,
    PaymentStatus,
    ProductVariant,
    StatusField,
    User,
)
from app.modules.inventory.jobs import sweep_expired_reservations
from app.modules.inventory.reservation import ReservationService
from app.modules.orders.cancel import order_advisory_lock
from app.modules.orders.state_service import OrderStateService

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

PAST = timedelta(minutes=20)


def _cancel_url(order_id: UUID | str) -> str:
    return f"{ORDERS}/{order_id}/cancel"


async def _placed(ready: Buyer, fingerprint: str | None = None) -> UUID:
    response = await ready.order(fingerprint=fingerprint)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _cancel(ready: Buyer, order_id: UUID) -> Response:
    return await ready.client.post(_cancel_url(order_id), headers=ready.account.headers)


async def _order(engine: AsyncEngine, order_id: UUID) -> Order:
    async with AsyncSession(engine) as session:
        order = await session.get(Order, order_id)
        assert order is not None
        return order


async def _reservation(engine: AsyncEngine, order_id: UUID) -> InventoryReservation:
    async with AsyncSession(engine) as session:
        return (
            await session.scalars(
                select(InventoryReservation).where(InventoryReservation.order_id == order_id)
            )
        ).one()


async def _redemption_status(engine: AsyncEngine, order_id: UUID) -> str | None:
    async with AsyncSession(engine) as session:
        return await session.scalar(
            select(DiscountRedemption.status).where(DiscountRedemption.order_id == order_id)
        )


async def _reserved(engine: AsyncEngine, variant: ProductVariant) -> int:
    async with AsyncSession(engine) as session:
        item = (
            await session.scalars(
                select(InventoryItem).where(InventoryItem.variant_id == variant.id)
            )
        ).one()
        return item.reserved_quantity


async def _cancel_history(engine: AsyncEngine, order_id: UUID) -> list[OrderStatusHistory]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(OrderStatusHistory).where(
                    OrderStatusHistory.order_id == order_id,
                    OrderStatusHistory.field == StatusField.ORDER,
                    OrderStatusHistory.new_status == "cancelled",
                )
            )
        )


async def _audit_count(engine: AsyncEngine, entity_id: UUID, action: str) -> int:
    return await _count(
        engine, AuditLog, AuditLog.entity_id == entity_id, AuditLog.action == action
    )


async def _expire_now(engine: AsyncEngine, order_id: UUID) -> None:
    """Move the order's reservation window into the past (the job has not run)."""
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == order_id)
            .values(
                created_at=utc_now() - PAST - timedelta(minutes=15),
                expires_at=utc_now() - PAST,
            )
        )


async def _move(engine: AsyncEngine, order_id: UUID, *moves: tuple[StatusField, str]) -> None:
    async with AsyncSession(engine) as session, session.begin():
        for field, status in moves:
            await OrderStateService(session).transition(
                order_id, field, status, actor_user_id=None, reason="test"
            )


# --- customer cancel ---------------------------------------------------------------------


async def test_cancel_frees_the_stock_and_the_code_use(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=100_000)
    ready = await buyer((variant, 2))
    code = await codes(value=10_000)
    order_id = await _placed(ready, await _with_code(auth_client, ready, code))
    assert await _reserved(db_engine, variant) == 2

    response = await _cancel(ready, order_id)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["id"], body["status"], body["payment_status"], body["cancel_reason"]) == (
        str(order_id),
        "cancelled",
        "unpaid",
        "customer",
    )
    assert body["order_number"].startswith("ORD-")
    assert (await _reservation(db_engine, order_id)).status == "released"
    assert await _reserved(db_engine, variant) == 0
    assert await _redemption_status(db_engine, order_id) == "released"
    [history] = await _cancel_history(db_engine, order_id)
    assert (history.actor_user_id, history.old_status) == (ready.account.id, "pending_payment")
    assert await _audit_count(db_engine, order_id, "order.status_changed") == 1
    assert await _audit_count(db_engine, order_id, "discount.redemption_released") == 1
    reservation_id = (await _reservation(db_engine, order_id)).id
    assert await _audit_count(db_engine, reservation_id, "reservation.released") == 1
    cart = await auth_client.get(f"{API}/cart", headers=ready.account.headers)
    assert len(cart.json()["items"]) == 1  # the cart is untouched


async def test_cancel_without_a_code_and_again_is_idempotent(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    order_id = await _placed(ready)

    first = await _cancel(ready, order_id)
    second = await _cancel(ready, order_id)

    assert first.status_code == second.status_code == 200, second.text
    assert first.json() == second.json()
    assert await _redemption_status(db_engine, order_id) is None
    assert len(await _cancel_history(db_engine, order_id)) == 1
    assert await _audit_count(db_engine, order_id, "order.status_changed") == 1
    assert await _audit_count(db_engine, order_id, "discount.redemption_released") == 0


async def test_cancel_errors(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    owner, other = await buyer((variant, 1)), await buyer((variant, 1))
    order_id = await _placed(owner)

    # Authentication comes before the path: a bad id without a token is 401.
    _error(await auth_client.post(_cancel_url("not-a-uuid")), 401, "UNAUTHORIZED")
    _error(await auth_client.post(_cancel_url(order_id)), 401, "UNAUTHORIZED")
    _error(await auth_client.post(f"{_cancel_url(order_id)}?force=1"), 401, "UNAUTHORIZED")
    _error(
        await auth_client.post(_cancel_url("not-a-uuid"), headers=owner.account.headers),
        400,
        "VALIDATION_ERROR",
    )
    _error(
        await auth_client.post(f"{_cancel_url(order_id)}?force=1", headers=owner.account.headers),
        400,
        "VALIDATION_ERROR",
    )
    for response in (await _cancel(other, order_id), await _cancel(owner, uuid4())):
        _error(response, 404, "NOT_FOUND")
        assert response.json()["request_id"]
        assert set(response.json()["error"]) == {"code", "message", "details"}
    assert (await _order(db_engine, order_id)).status == "pending_payment"


async def test_a_confirmed_order_cannot_be_cancelled(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    order_id = await _placed(ready)
    reservation_id = (await _reservation(db_engine, order_id)).id
    async with AsyncSession(db_engine) as session, session.begin():
        await ReservationService(session).commit(reservation_id)
    await _move(
        db_engine,
        order_id,
        (StatusField.PAYMENT, "pending"),
        (StatusField.PAYMENT, "paid"),
        (StatusField.ORDER, "confirmed"),
    )

    response = await _cancel(ready, order_id)

    # The state guard answers before the committed reservation is even looked at.
    body = _error(response, 422, "INVALID_STATE_TRANSITION")
    assert response.json()["request_id"]
    assert body["details"][0]["from"] == "confirmed"
    assert (await _order(db_engine, order_id)).status == "confirmed"
    assert (await _reservation(db_engine, order_id)).status == "committed"


async def test_payment_at_the_gateway_blocks_a_cancel_but_a_failed_one_does_not(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    order_id = await _placed(ready)
    await _move(db_engine, order_id, (StatusField.PAYMENT, PaymentStatus.PENDING))

    _error(await _cancel(ready, order_id), 409, "PAYMENT_IN_PROGRESS")
    assert (await _reservation(db_engine, order_id)).status == "active"

    await _move(db_engine, order_id, (StatusField.PAYMENT, PaymentStatus.FAILED))
    response = await _cancel(ready, order_id)
    assert response.status_code == 200, response.text
    assert (response.json()["payment_status"], response.json()["cancel_reason"]) == (
        "failed",
        "customer",
    )


async def test_cancel_after_the_reservation_expired_is_an_expiry(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    order_id = await _placed(ready, await _with_code(auth_client, ready, await codes(value=1_000)))
    await _expire_now(db_engine, order_id)

    response = await _cancel(ready, order_id)

    assert response.status_code == 200, response.text
    assert response.json()["cancel_reason"] == "expired"
    [history] = await _cancel_history(db_engine, order_id)
    assert history.actor_user_id is None  # the system expired it (D34)
    assert await _redemption_status(db_engine, order_id) == "released"
    assert await _reserved(db_engine, variant) == 0


async def test_cancel_after_lazy_frees_keeps_the_counters(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(3, 0, 0))
    ready = await buyer((variant, 2))
    order_id = await _placed(ready)
    await _expire_now(db_engine, order_id)
    admin = await make_account("admin")
    adjusted = await auth_client.patch(
        f"{API}/admin/inventory/{variant.id}",
        json={"adjustment_type": "increase", "quantity": 1, "reason": "restock"},
        headers=admin.headers,
    )
    assert adjusted.status_code == 200, adjusted.text  # frees the expired line lazily
    assert await _reserved(db_engine, variant) == 0

    response = await _cancel(ready, order_id)

    assert response.status_code == 200, response.text
    assert response.json()["cancel_reason"] == "expired"
    assert await _reserved(db_engine, variant) == 0
    reservation = await _reservation(db_engine, order_id)
    assert reservation.status == "released"
    async with AsyncSession(db_engine) as session:
        audit = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == reservation.id, AuditLog.action == "reservation.released"
                )
            )
        ).one()
    assert audit.metadata_["diff"]["expired"]["after"] is True


async def test_cancel_of_an_order_whose_reservation_already_expired(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    order_id = await _placed(ready)
    await _expire_now(db_engine, order_id)
    async with AsyncSession(db_engine) as session, session.begin():
        reservation_id = (await _reservation(db_engine, order_id)).id
        assert await ReservationService(session).expire(reservation_id)  # order left pending

    response = await _cancel(ready, order_id)

    assert (response.status_code, response.json()["cancel_reason"]) == (200, "expired")
    assert (await _reservation(db_engine, order_id)).status == "expired"


async def test_a_cancelled_order_frees_the_last_code_use_and_the_pending_slot(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    first, second = await buyer((variant, 1)), await buyer((variant, 1))
    last = await codes(value=1_000, usage_limit_total=1)
    order_id = await _placed(first, await _with_code(auth_client, first, last))
    refused = await auth_client.post(
        f"{API}/cart/discount", json={"code": last.code}, headers=second.account.headers
    )
    _error(refused, 422, "DISCOUNT_NOT_APPLICABLE")

    assert (await _cancel(first, order_id)).status_code == 200

    assert (
        await second.order(fingerprint=await _with_code(auth_client, second, last))
    ).status_code == 201
    # One live pending order per user: after the cancel, the first user may order again
    # (without the code, whose only use the second order now holds).
    await auth_client.delete(f"{API}/cart/discount", headers=first.account.headers)
    assert (await first.order()).status_code == 201


# --- the expiry job cancels the order (D34) ----------------------------------------------


async def test_the_sweep_cancels_the_order_of_an_expired_reservation(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    order_id = await _placed(ready, await _with_code(auth_client, ready, await codes(value=1_000)))
    await _expire_now(db_engine, order_id)

    result = await sweep_expired_reservations(db_engine)

    assert result.cancelled >= 1 and result.failed == 0
    order = await _order(db_engine, order_id)
    assert (order.status, order.cancel_reason) == ("cancelled", "expired")
    assert (await _reservation(db_engine, order_id)).status == "expired"
    assert await _redemption_status(db_engine, order_id) == "released"
    [history] = await _cancel_history(db_engine, order_id)
    assert history.actor_user_id is None
    async with AsyncSession(db_engine) as session:
        audit = (
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == order_id, AuditLog.action == "order.status_changed"
                )
            )
        ).one()
    assert audit.actor_user_id is None
    # The customer's later cancel answers the expiry.
    response = await _cancel(ready, order_id)
    assert (response.status_code, response.json()["cancel_reason"]) == (200, "expired")


@pytest.mark.parametrize("held", ["advisory", "row"])
async def test_the_sweep_skips_a_busy_order_and_closes_it_later(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine, held: str
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    order_id = await _placed(ready)
    await _expire_now(db_engine, order_id)

    async with AsyncSession(db_engine) as session, session.begin():
        if held == "advisory":
            await session.execute(order_advisory_lock(order_id))
        else:
            await session.execute(select(Order).where(Order.id == order_id).with_for_update())
        busy = await sweep_expired_reservations(db_engine)
        assert busy.skipped >= 1 and busy.failed == 0
        assert (await _reservation(db_engine, order_id)).status == "active"
        assert (await _order(db_engine, order_id)).status == "pending_payment"

    await sweep_expired_reservations(db_engine)
    assert (await _order(db_engine, order_id)).cancel_reason == "expired"
    assert (await _reservation(db_engine, order_id)).status == "expired"


async def test_the_sweep_cancels_a_pending_order_left_without_a_live_reservation(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 1))
    order_id = await _placed(ready)
    await _expire_now(db_engine, order_id)
    reservation_id = (await _reservation(db_engine, order_id)).id
    # What the pre-ORD-06 job did: close the reservation, leave the order pending.
    async with AsyncSession(db_engine) as session, session.begin():
        assert await ReservationService(session).expire(reservation_id)

    result = await sweep_expired_reservations(db_engine)

    assert result.cancelled >= 1
    assert (await _order(db_engine, order_id)).cancel_reason == "expired"


# --- concurrency (ADR-048) -----------------------------------------------------------------


async def test_two_cancels_cancel_once(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 2))
    order_id = await _placed(ready)

    responses = await asyncio.gather(_cancel(ready, order_id), _cancel(ready, order_id))

    assert [response.status_code for response in responses] == [200, 200]
    assert len(await _cancel_history(db_engine, order_id)) == 1
    assert await _audit_count(db_engine, order_id, "order.status_changed") == 1
    reservation_id = (await _reservation(db_engine, order_id)).id
    assert await _audit_count(db_engine, reservation_id, "reservation.released") == 1
    assert await _reserved(db_engine, variant) == 0


async def test_a_cancel_racing_the_sweep_cancels_once(
    auth_client: AsyncClient, catalog: Catalog, buyer: MakeBuyer, codes: Any, db_engine: AsyncEngine
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    ready = await buyer((variant, 2))
    order_id = await _placed(ready, await _with_code(auth_client, ready, await codes(value=1_000)))
    await _expire_now(db_engine, order_id)

    response, swept = await asyncio.gather(
        _cancel(ready, order_id), sweep_expired_reservations(db_engine)
    )

    assert response.status_code == 200, response.text
    assert swept.failed == 0
    assert len(await _cancel_history(db_engine, order_id)) == 1
    assert (await _order(db_engine, order_id)).cancel_reason == "expired"
    assert await _redemption_status(db_engine, order_id) == "released"
    assert await _reserved(db_engine, variant) == 0


async def test_a_cancel_racing_a_stock_adjustment_and_a_new_order(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(3, 0, 0))
    ready, rival = await buyer((variant, 2)), await buyer((variant, 1))
    order_id = await _placed(ready)
    fp = (await rival.quote())["fingerprint"]
    admin = await make_account("admin")

    cancelled, adjusted, placed = await asyncio.gather(
        _cancel(ready, order_id),
        auth_client.patch(
            f"{API}/admin/inventory/{variant.id}",
            json={"adjustment_type": "increase", "quantity": 1, "reason": "restock"},
            headers=admin.headers,
        ),
        rival.order(fingerprint=fp),
    )

    assert (cancelled.status_code, adjusted.status_code, placed.status_code) == (200, 200, 201)
    async with AsyncSession(db_engine) as session:
        item = (
            await session.scalars(
                select(InventoryItem).where(InventoryItem.variant_id == variant.id)
            )
        ).one()
    # 3 + 1 restocked; only the rival's unit is held after the cancel freed the other two.
    assert (item.total_quantity, item.reserved_quantity) == (4, 1)


# --- end to end: guest cart → OTP → validate → order → cancel ------------------------------


@pytest_asyncio.fixture
async def logged_in(
    catalog: Catalog, codes: Any, methods: Any, db_engine: AsyncEngine
) -> AsyncIterator[list[str]]:
    """Mobiles of users made by logging in; their orders, addresses and carts go first."""
    started = utc_now()
    mobiles: list[str] = []
    yield mobiles
    async with AsyncSession(db_engine) as session, session.begin():
        users = list(await session.scalars(select(User.id).where(User.phone.in_(mobiles))))
        orders = list(await session.scalars(select(Order.id).where(Order.user_id.in_(users))))
        await delete_orders(session, orders)
        await session.execute(delete(Address).where(Address.user_id.in_(users)))
        await session.execute(delete(Cart).where(Cart.user_id.in_(users)))
        await session.execute(
            delete(Cart).where(Cart.user_id.is_(None), Cart.created_at >= started)
        )
        await session.execute(delete(User).where(User.id.in_(users)))


async def test_guest_to_order_to_cancel_end_to_end(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[Any]],
    catalog: Catalog,
    codes: Any,
    methods: Any,
    db_engine: AsyncEngine,
    logged_in: list[str],
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(3, 0, 0), base_price=200_000)
    hidden = await catalog.variant(await catalog.product(), stock=(3, 0, 0))
    code = await codes(value=20_000, usage_limit_total=1)
    method = await methods(cost=30_000)
    await _guest_cart(auth_client, (variant, 2), (hidden, 1))
    mobile = _mobile()
    logged_in.append(mobile)
    login = await _login(auth_client, issue_otp, mobile)
    auth_client.cookies.clear()
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    address = await auth_client.post(f"{API}/addresses", json=ADDRESS, headers=headers)
    body = {"address_id": address.json()["id"], "shipping_method_id": str(method.id)}
    applied = await auth_client.post(
        f"{API}/cart/discount", json={"code": code.code}, headers=headers
    )
    assert applied.status_code == 200, applied.text

    # SD rule: a line whose product was deleted blocks checkout until it is removed.
    await catalog.set(ProductVariant, hidden.id, deleted_at=utc_now())
    _error(
        await auth_client.post(VALIDATE, json=body, headers=headers),
        422,
        "BUSINESS_RULE_VIOLATION",
        "line_unavailable",
    )
    cart = (await auth_client.get(f"{API}/cart", headers=headers)).json()
    hidden_line = next(item for item in cart["items"] if item["variant_id"] == str(hidden.id))
    removed = await auth_client.delete(f"{API}/cart/items/{hidden_line['id']}", headers=headers)
    assert removed.status_code == 204, removed.text

    quote = await auth_client.post(VALIDATE, json=body, headers=headers)
    assert quote.status_code == 200, quote.text
    key = {"Idempotency-Key": str(uuid4())}
    order_body = body | {"fingerprint": quote.json()["fingerprint"]}
    placed = await auth_client.post(ORDERS, json=order_body, headers=headers | key)
    replay = await auth_client.post(ORDERS, json=order_body, headers=headers | key)
    assert placed.status_code == replay.status_code == 201, placed.text
    assert placed.json()["id"] == replay.json()["id"]
    assert placed.json()["grand_total"] == quote.json()["grand_total"]
    order_id = UUID(placed.json()["id"])
    assert await _reserved(db_engine, variant) == 2
    assert await _redemption_status(db_engine, order_id) == "pending"

    cancelled = await auth_client.post(_cancel_url(order_id), headers=headers)

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["cancel_reason"] == "customer"
    assert await _reserved(db_engine, variant) == 0
    assert await _redemption_status(db_engine, order_id) == "released"
    # The code's only use is free again and the same cart can be ordered again.
    again = await auth_client.post(VALIDATE, json=body, headers=headers)
    assert again.status_code == 200, again.text
    second = await auth_client.post(
        ORDERS,
        json=body | {"fingerprint": again.json()["fingerprint"]},
        headers=headers | {"Idempotency-Key": str(uuid4())},
    )
    assert second.status_code == 201, second.text
