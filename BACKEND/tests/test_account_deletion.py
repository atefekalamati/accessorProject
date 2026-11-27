"""Account deletion: preconditions and anonymization (ACC-05, D37, PRD «پروفایل» ✓)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from conftest import Catalog, MakeAccount
from httpx import AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_admin_cancel_paid import _paid, _staff_cancel
from test_orders_create import (
    ORDERS,
    MakeBuyer,
    _orders_go_first,
    buyer,
    codes,
    methods,
    shopper,
)
from test_returns import Delivered, _order

from app.core.errors import AppError
from app.db.models import (
    Address,
    AuditLog,
    Cart,
    ContactMessage,
    IdempotencyKey,
    OrderAddress,
    OtpCode,
    User,
    UserRole,
    UserSession,
)
from app.db.models.orders import Order
from app.db.seed import role_id
from app.modules.auth.deletion import AccountDeletionService

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures


async def _delete(engine: AsyncEngine, user_id: UUID) -> AppError | None:
    try:
        async with AsyncSession(engine) as session, session.begin():
            service = AccountDeletionService(session)
            user = await service.lock_deletable(user_id)
            await service.anonymize_locked(user, None)
    except AppError as error:
        return error
    return None


async def _user(engine: AsyncEngine, user_id: UUID) -> User:
    async with AsyncSession(engine) as session:
        found = await session.get(User, user_id)
    assert found is not None
    return found


async def _count(engine: AsyncEngine, model: Any, *where: Any) -> int:
    async with AsyncSession(engine) as session:
        return int(await session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def test_deletion_removes_the_identity_and_keeps_the_orders(
    auth_client: AsyncClient,
    catalog: Catalog,
    buyer: MakeBuyer,
    make_account: MakeAccount,
    db_engine: AsyncEngine,
    issue_otp: Any,
) -> None:
    delivered: Delivered = await _order(catalog, buyer, db_engine)
    user_id = delivered.ready.account.id
    old = await _user(db_engine, user_id)
    mobile = old.phone
    assert mobile is not None
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(first_name="Sara", last_name="Ahmadi", email="sara@example.com")
        )
        session.add(
            ContactMessage(
                user_id=user_id,
                name="Sara",
                phone=mobile,
                email="sara@example.com",
                subject="Hi",
                message="Where is my parcel?",
            )
        )
    async with AsyncSession(db_engine) as session:
        before = await session.get(Order, delivered.order_id)
        assert before is not None
        grand_total, province = before.grand_total, None
        snapshot = await session.get(OrderAddress, delivered.order_id)
        assert snapshot is not None
        province, city = snapshot.province, snapshot.city
    admin = await make_account("admin")
    today = {"from": "2026-01-01", "to": "2026-12-31"}

    async def sales() -> Any:
        report = await auth_client.get(
            "/api/v1/admin/reports/sales", params=today, headers=admin.headers
        )
        assert report.status_code == 200, report.text
        return report.json()

    sales_before = await sales()
    await issue_otp(mobile)
    stored = IdempotencyKey.user_id == user_id
    assert await _count(db_engine, IdempotencyKey, stored) >= 1  # the placed order's reply

    assert await _delete(db_engine, user_id) is None

    user = await _user(db_engine, user_id)
    assert (user.phone, user.first_name, user.last_name, user.email) == (None, None, None, None)
    assert user.deleted_at is not None and user.mobile_verified_at is None
    async with AsyncSession(db_engine) as session:
        order = await session.get(Order, delivered.order_id)
        address = await session.get(OrderAddress, delivered.order_id)
        message = await session.scalar(
            select(ContactMessage).where(ContactMessage.user_id == user_id)
        )
        [audit] = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == user_id, AuditLog.action == "user.deleted"
                )
            )
        )
    assert order is not None and (order.phone, order.grand_total) == (None, grand_total)
    assert address is not None
    assert (address.recipient_name, address.phone, address.postal_code, address.address_line) == (
        None,
        None,
        None,
        None,
    )
    assert (address.plaque, address.unit, address.source_address_id) == (None, None, None)
    assert (address.province, address.city) == (province, city)  # kept for accounting
    assert message is not None
    assert (message.name, message.phone, message.email) == (None, None, None)
    assert message.message == "Where is my parcel?"
    assert mobile not in str(audit.metadata_) and "Sara" not in str(audit.metadata_)
    assert await _count(db_engine, Address, Address.user_id == user_id) == 0
    assert await _count(db_engine, Cart, Cart.user_id == user_id) == 0
    assert await _count(db_engine, IdempotencyKey, IdempotencyKey.user_id == user_id) == 0
    assert await _count(db_engine, OtpCode, OtpCode.mobile == mobile) == 0
    assert (
        await _count(
            db_engine, UserSession, UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
        )
        == 0
    )

    # The old access token is dead, the mobile registers a fresh account.
    me = await auth_client.get("/api/v1/auth/me", headers=delivered.headers)
    assert me.status_code == 401
    await issue_otp(mobile)
    fresh = await auth_client.post(
        "/api/v1/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
    )
    assert fresh.status_code == 200, fresh.text
    headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    again = await auth_client.get("/api/v1/auth/me", headers=headers)
    assert again.json()["id"] != str(user_id)
    hidden = await auth_client.get(f"{ORDERS}/{delivered.number}", headers=headers)
    assert hidden.status_code == 404

    # Staff views render the anonymized rows; the figures do not move.
    detail = await auth_client.get(
        f"/api/v1/admin/orders/{delivered.order_id}", headers=admin.headers
    )
    assert detail.status_code == 200, detail.text
    assert (detail.json()["phone"], detail.json()["address"]["recipient_name"]) == (None, None)
    listed = await auth_client.get(
        "/api/v1/admin/orders", params={"limit": 100}, headers=admin.headers
    )
    row = next(o for o in listed.json()["items"] if o["id"] == str(delivered.order_id))
    assert row["phone"] is None
    messages = await auth_client.get(
        "/api/v1/admin/contact-messages", params={"limit": 100}, headers=admin.headers
    )
    assert messages.status_code == 200, messages.text
    assert any(m["name"] is None and m["mobile"] is None for m in messages.json()["items"])
    assert await sales() == sales_before
    assert await _delete(db_engine, user_id) is not None  # twice: the account is gone (404)
    async with AsyncSession(db_engine) as session, session.begin():
        # Other tests count contact messages: leave none behind.
        await session.execute(delete(ContactMessage).where(ContactMessage.user_id == user_id))


async def test_open_business_blocks_deletion(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    pending = await _order(catalog, buyer, db_engine, deliver=False)
    error = await _delete(db_engine, pending.ready.account.id)
    assert error is not None and (error.status_code, error.code) == (
        409,
        "ACCOUNT_HAS_ACTIVE_ORDERS",
    )

    confirmed = await _order(catalog, buyer, db_engine, deliver=False)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(Order)
            .where(Order.id == confirmed.order_id)
            .values(status="confirmed", payment_status="paid")
        )
    error = await _delete(db_engine, confirmed.ready.account.id)
    assert error is not None and error.code == "ACCOUNT_HAS_ACTIVE_ORDERS"

    returning = await _order(catalog, buyer, db_engine)
    assert (await returning.create()).status_code == 201
    error = await _delete(db_engine, returning.ready.account.id)
    assert error is not None and error.code == "ACCOUNT_HAS_ACTIVE_ORDERS"

    for kept in (pending, confirmed, returning):
        user = await _user(db_engine, kept.ready.account.id)
        assert user.deleted_at is None and user.phone is not None


async def test_a_staff_account_is_not_deleted(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    delivered = await _order(catalog, buyer, db_engine)
    user_id = delivered.ready.account.id
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(UserRole(user_id=user_id, role_id=role_id("support")))

    error = await _delete(db_engine, user_id)

    assert error is not None and (error.status_code, error.code) == (422, "STAFF_ACCOUNT")
    assert (await _user(db_engine, user_id)).deleted_at is None


async def test_money_still_owed_blocks_deletion(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    paid = await _paid(auth_client, catalog, buyer)
    staff = await make_account("admin")
    assert (await _staff_cancel(auth_client, staff, paid.order_id)).status_code == 200

    # The order is cancelled, but its payment is refund_required: not deletable yet.
    error = await _delete(db_engine, paid.ready.account.id)

    assert error is not None and error.code == "ACCOUNT_HAS_ACTIVE_ORDERS"


async def test_a_blocked_account_is_not_deleted(
    catalog: Catalog, buyer: MakeBuyer, db_engine: AsyncEngine
) -> None:
    delivered = await _order(catalog, buyer, db_engine)
    user_id = delivered.ready.account.id
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(update(User).where(User.id == user_id).values(status="blocked"))

    error = await _delete(db_engine, user_id)

    assert error is not None and (error.status_code, error.code) == (403, "FORBIDDEN")
    assert (await _user(db_engine, user_id)).phone is not None
