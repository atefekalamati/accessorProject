"""Account deletion endpoints and the deletion OTP purpose (ACC-06, PRD «پروفایل» ✓)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from conftest import Catalog, MakeAccount
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_orders_create import MakeBuyer, _error, _orders_go_first, buyer, codes, methods, shopper
from test_returns import _order

from app.db.models import AuditLog, OtpCode, User

pytestmark = pytest.mark.integration

__all__ = ["_orders_go_first", "buyer", "codes", "methods", "shopper"]  # shared fixtures

API = "/api/v1"
REQUEST = f"{API}/users/me/deletion/request-otp"
DELETE = f"{API}/users/me/deletion"
CODE = "123456"  # mock OTP code outside production


async def _codes(engine: AsyncEngine, mobile: str) -> list[OtpCode]:
    async with AsyncSession(engine) as session:
        return list(
            await session.scalars(
                select(OtpCode).where(OtpCode.mobile == mobile).order_by(OtpCode.created_at)
            )
        )


async def _age(engine: AsyncEngine, user_id: Any) -> None:
    """Move the sign-in code out of the resend cooldown (shared by both purposes)."""
    mobile = await _phone(engine, user_id)
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(
            update(OtpCode)
            .where(OtpCode.mobile == mobile)
            .values(created_at=OtpCode.created_at - timedelta(minutes=2))
        )


async def _phone(engine: AsyncEngine, user_id: Any) -> str | None:
    async with AsyncSession(engine) as session:
        return await session.scalar(select(User.phone).where(User.id == user_id))


async def test_delete_with_the_deletion_code(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    account = await make_account("customer")
    mobile = await _phone(db_engine, account.id)
    assert mobile is not None
    refresh = auth_client.cookies.get("refresh_token")
    assert refresh

    await _age(db_engine, account.id)
    sent = await auth_client.post(REQUEST, headers=account.headers)
    assert sent.status_code == 200, sent.text
    assert sent.headers["cache-control"] == "no-store"
    latest = (await _codes(db_engine, mobile))[-1]
    assert latest.purpose == "account_delete"

    deleted = await auth_client.post(DELETE, json={"code": CODE}, headers=account.headers)

    assert deleted.status_code == 204, deleted.text
    assert deleted.headers["cache-control"] == "no-store"
    cleared = deleted.headers["set-cookie"]
    assert "refresh_token=" in cleared and "Max-Age=0" in cleared
    for attribute in ("Path=/api/v1/auth", "Secure", "HttpOnly", "SameSite=strict"):
        assert attribute in cleared, attribute
    assert await _phone(db_engine, account.id) is None
    me = await auth_client.get(f"{API}/auth/me", headers=account.headers)
    assert me.status_code == 401
    old = await auth_client.post(f"{API}/auth/refresh", cookies={"refresh_token": refresh})
    assert old.status_code == 401


async def test_a_login_code_never_deletes_and_back(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine, issue_otp: Any
) -> None:
    account = await make_account("customer")
    mobile = await _phone(db_engine, account.id)
    assert mobile is not None

    await _age(db_engine, account.id)
    await issue_otp(mobile)  # a login code
    refused = await auth_client.post(DELETE, json={"code": CODE}, headers=account.headers)
    _error(refused, 401, "OTP_INVALID")
    assert await _phone(db_engine, account.id) == mobile

    await _age(db_engine, account.id)
    assert (await auth_client.post(REQUEST, headers=account.headers)).status_code == 200
    # The deletion code did not replace the login code, and cannot sign in.
    login = await auth_client.post(f"{API}/auth/verify-otp", json={"mobile": mobile, "code": CODE})
    assert login.status_code == 200  # the earlier login code is still valid
    codes = await _codes(db_engine, mobile)
    open_delete = [c for c in codes if c.purpose == "account_delete" and c.consumed_at is None]
    assert len(open_delete) == 1
    second = await auth_client.post(f"{API}/auth/verify-otp", json={"mobile": mobile, "code": CODE})
    _error(second, 401, "OTP_INVALID")  # only a deletion code is left
    assert await _phone(db_engine, account.id) == mobile


async def test_wrong_and_expired_codes(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    account = await make_account("customer")
    mobile = await _phone(db_engine, account.id)
    assert mobile is not None
    await _age(db_engine, account.id)
    assert (await auth_client.post(REQUEST, headers=account.headers)).status_code == 200

    wrong = await auth_client.post(DELETE, json={"code": "000000"}, headers=account.headers)
    _error(wrong, 401, "OTP_INVALID")
    assert (await _codes(db_engine, mobile))[-1].attempt_count == 1  # survives the 401
    for body in ({}, {"code": "12345"}, {"code": CODE, "mobile": mobile}):
        _error(
            await auth_client.post(DELETE, json=body, headers=account.headers),
            400,
            "VALIDATION_ERROR",
        )

    async with AsyncSession(db_engine) as session, session.begin():
        latest = await session.get(OtpCode, (await _codes(db_engine, mobile))[-1].id)
        assert latest is not None
        latest.expires_at = latest.created_at - timedelta(seconds=1)
    expired = await auth_client.post(DELETE, json={"code": CODE}, headers=account.headers)
    _error(expired, 401, "OTP_INVALID")
    assert await _phone(db_engine, account.id) == mobile


async def test_refusals_send_no_code_and_consume_none(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    buyer: MakeBuyer,
    db_engine: AsyncEngine,
) -> None:
    staff = await make_account("support")
    staff_mobile = await _phone(db_engine, staff.id)
    assert staff_mobile is not None
    before = len(await _codes(db_engine, staff_mobile))
    _error(await auth_client.post(REQUEST, headers=staff.headers), 422, "STAFF_ACCOUNT")
    assert len(await _codes(db_engine, staff_mobile)) == before  # no SMS for a refusal

    # A code obtained before the order was placed is not consumed by the refusal.
    pending = await _order(catalog, buyer, db_engine, deliver=False)
    mobile = await _phone(db_engine, pending.ready.account.id)
    assert mobile is not None
    _error(
        await auth_client.post(REQUEST, headers=pending.headers), 409, "ACCOUNT_HAS_ACTIVE_ORDERS"
    )
    refused = await auth_client.post(DELETE, json={"code": CODE}, headers=pending.headers)
    _error(refused, 409, "ACCOUNT_HAS_ACTIVE_ORDERS")
    assert await _phone(db_engine, pending.ready.account.id) == mobile


async def test_auth_and_rate_limit(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    for url, body in ((REQUEST, None), (DELETE, {"code": CODE})):
        _error(await auth_client.post(url, json=body), 401, "UNAUTHORIZED")
    account = await make_account("customer")
    await _age(db_engine, account.id)
    assert (await auth_client.post(REQUEST, headers=account.headers)).status_code == 200
    again = await auth_client.post(REQUEST, headers=account.headers)
    _error(again, 429, "OTP_RATE_LIMITED")  # same resend cooldown as login codes
    assert "retry-after" in again.headers


async def test_exhausted_attempts_and_a_double_submit(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine, settings: Any
) -> None:
    account = await make_account("customer")
    await _age(db_engine, account.id)
    assert (await auth_client.post(REQUEST, headers=account.headers)).status_code == 200
    for _ in range(settings.otp_max_attempts):
        wrong = await auth_client.post(DELETE, json={"code": "000000"}, headers=account.headers)
        _error(wrong, 401, "OTP_INVALID")
    exhausted = await auth_client.post(DELETE, json={"code": CODE}, headers=account.headers)
    _error(exhausted, 401, "OTP_INVALID")  # even the right code: ask for a new one
    assert await _phone(db_engine, account.id) is not None

    await _age(db_engine, account.id)
    assert (await auth_client.post(REQUEST, headers=account.headers)).status_code == 200
    both = await asyncio.gather(
        *(auth_client.post(DELETE, json={"code": CODE}, headers=account.headers) for _ in range(2))
    )
    statuses = sorted(response.status_code for response in both)
    assert statuses in ([204, 401], [204, 404]), [r.text for r in both]
    async with AsyncSession(db_engine) as session:
        audits = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == account.id, AuditLog.action == "user.deleted"
                )
            )
        )
    assert len(audits) == 1
