"""POST/DELETE /cart/discount and the code in GET /cart (DSC-03, D31, D34, ADR-043)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Catalog, MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings, get_app_settings
from app.core.time import utc_now
from app.db.models import (
    Cart,
    DiscountAttempt,
    DiscountCode,
    DiscountRedemption,
    OtpCode,
    ProductVariant,
    User,
    UserStatus,
)
from app.modules.cart.tokens import CART_COOKIE_NAME

pytestmark = pytest.mark.integration

API = "/api/v1"
CART = f"{API}/cart"
ITEMS = f"{CART}/items"
CODE = f"{CART}/discount"


def _error(response: Response, status: int, code: str, kind: str | None = None) -> None:
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code
    if kind is not None:
        assert body["details"][0]["type"] == kind


@pytest_asyncio.fixture(autouse=True)
async def _clean_attempts(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """Every request comes from one client IP; start each test with no failed attempts."""
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(DiscountAttempt))
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(DiscountAttempt))
        started = utc_now() - timedelta(hours=1)
        await session.execute(
            delete(Cart).where(Cart.user_id.is_(None), Cart.created_at >= started)
        )


@pytest_asyncio.fixture
async def codes(db_engine: AsyncEngine) -> AsyncIterator[Callable[..., Awaitable[DiscountCode]]]:
    ids: list[UUID] = []

    async def make(**values: Any) -> DiscountCode:
        base: dict[str, Any] = {
            "code": f"C{uuid4().hex[:10].upper()}",
            "type": "percent",
            "value": 1_000,
        }
        code = DiscountCode(**(base | values))
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            session.add(code)
        ids.append(code.id)
        return code

    yield make
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            delete(DiscountRedemption).where(DiscountRedemption.discount_code_id.in_(ids))
        )
        await session.execute(delete(DiscountCode).where(DiscountCode.id.in_(ids)))


@pytest.fixture
def limits(auth_client: AsyncClient, settings: Settings) -> Iterator[Callable[..., None]]:
    app = auth_client._transport.app  # type: ignore[attr-defined]

    def set_limits(**values: int) -> None:
        updated = settings.model_copy(update=values)
        app.dependency_overrides[get_app_settings] = lambda: updated

    yield set_limits
    app.dependency_overrides.pop(get_app_settings, None)


async def _redeem(engine: AsyncEngine, code: DiscountCode, phone: str = "+989120000000") -> None:
    async with AsyncSession(engine) as session, session.begin():
        session.add(
            DiscountRedemption(
                discount_code_id=code.id,
                order_id=uuid4(),
                phone=phone,
                code=code.code,
                amount=1,
            )
        )


async def _user_cart(
    client: AsyncClient, headers: dict[str, str], variant: ProductVariant, quantity: int = 1
) -> None:
    response = await client.post(
        ITEMS, json={"variant_id": str(variant.id), "quantity": quantity}, headers=headers
    )
    assert response.status_code == 201, response.text


async def _guest_cart(client: AsyncClient, variant: ProductVariant) -> str:
    client.cookies.clear()
    response = await client.post(ITEMS, json={"variant_id": str(variant.id), "quantity": 1})
    assert response.status_code == 201, response.text
    token = response.cookies[CART_COOKIE_NAME]
    client.cookies.set(CART_COOKIE_NAME, token)
    return token


async def _attempts(engine: AsyncEngine) -> int:
    async with AsyncSession(engine) as session:
        return int(await session.scalar(select(func.count()).select_from(DiscountAttempt)) or 0)


# --- applying ------------------------------------------------------------------------


async def test_apply_prices_the_code_and_is_idempotent(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, codes: Any
) -> None:
    customer = await make_account("customer")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=50_000)
    await _user_cart(auth_client, customer.headers, variant, 2)
    code = await codes(value=1_000, max_amount=8_000)

    first = await auth_client.post(
        CODE, json={"code": f"  {code.code.lower()} "}, headers=customer.headers
    )
    again = await auth_client.post(CODE, json={"code": code.code}, headers=customer.headers)

    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    body = first.json()
    assert body["discount"] == {"code": code.code, "applied": True, "reason": None}
    assert (body["discount_code_amount"], body["grand_total"]) == (8_000, 92_000)
    assert again.status_code == 200 and again.json() == {
        **body,
        "calculated_at": again.json()["calculated_at"],
    }
    cart = (await auth_client.get(CART, headers=customer.headers)).json()
    assert cart["discount"]["applied"] is True and cart["has_changes"] is False


@pytest.mark.parametrize(
    ("code_values", "kind"),
    [
        ({"is_active": False}, "invalid"),
        ({"starts_at": "future"}, "invalid"),
        ({"ends_at": "past", "starts_at": "long_ago"}, "expired"),
        ({"min_order_amount": 60_000}, "below_minimum"),
        ({"usage_limit_total": 1}, "exhausted"),
    ],
)
async def test_rejections_are_422_and_counted(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    codes: Any,
    db_engine: AsyncEngine,
    code_values: dict[str, Any],
    kind: str,
) -> None:
    customer = await make_account("customer")
    now = utc_now()
    moments = {"future": now + timedelta(days=1), "past": now - timedelta(days=1)}
    moments["long_ago"] = now - timedelta(days=9)
    values = {key: moments.get(value, value) for key, value in code_values.items()}
    # A sale puts the cart below the minimum: the basis is after product discounts.
    variant = await catalog.variant(
        await catalog.product(), stock=(5, 0, 0), base_price=70_000, sale_price=50_000
    )
    await _user_cart(auth_client, customer.headers, variant)
    code = await codes(**values)
    if kind == "exhausted":
        await _redeem(db_engine, code)

    response = await auth_client.post(CODE, json={"code": code.code}, headers=customer.headers)

    _error(response, 422, "DISCOUNT_NOT_APPLICABLE", kind)
    assert not any(character.isdigit() for character in response.json()["error"]["message"])
    assert await _attempts(db_engine) == 1


@pytest.mark.parametrize("raw", ["NO-SUCH-CODE", "!!", "ıı-code", " "])
async def test_unknown_or_malformed_codes_look_the_same(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    db_engine: AsyncEngine,
    raw: str,
) -> None:
    customer = await make_account("customer")
    await _user_cart(
        auth_client,
        customer.headers,
        await catalog.variant(await catalog.product(), stock=(5, 0, 0)),
    )

    response = await auth_client.post(CODE, json={"code": raw}, headers=customer.headers)

    _error(response, 422, "DISCOUNT_NOT_APPLICABLE", "invalid")
    assert await _attempts(db_engine) == 1


async def test_failed_apply_keeps_the_earlier_code(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, codes: Any
) -> None:
    customer = await make_account("customer")
    await _user_cart(
        auth_client,
        customer.headers,
        await catalog.variant(await catalog.product(), stock=(5, 0, 0)),
    )
    good = await codes()
    await auth_client.post(CODE, json={"code": good.code}, headers=customer.headers)

    failed = await auth_client.post(CODE, json={"code": "NOPE-123"}, headers=customer.headers)

    assert failed.status_code == 422
    cart = (await auth_client.get(CART, headers=customer.headers)).json()
    assert cart["discount"]["code"] == good.code


async def test_small_percent_can_apply_for_zero_and_unavailable_lines_give_no_eligible(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, codes: Any
) -> None:
    customer, other = await make_account("customer"), await make_account("customer")
    cheap = await catalog.variant(await catalog.product(), stock=(5, 0, 0), base_price=100)
    await _user_cart(auth_client, customer.headers, cheap)
    tiny = await codes(value=1)  # 0.01% of 100 Toman rounds to 0

    applied = await auth_client.post(CODE, json={"code": tiny.code}, headers=customer.headers)

    assert applied.status_code == 200, applied.text
    assert applied.json()["discount"]["applied"] is True
    assert applied.json()["discount_code_amount"] == 0

    hidden = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    await _user_cart(auth_client, other.headers, hidden)
    await catalog.set(ProductVariant, hidden.id, deleted_at=utc_now())
    response = await auth_client.post(CODE, json={"code": tiny.code}, headers=other.headers)
    _error(response, 422, "DISCOUNT_NOT_APPLICABLE", "no_eligible_lines")


async def test_request_errors(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer, blocked = await make_account("customer"), await make_account("customer")
    await catalog.set(User, blocked.id, status=UserStatus.BLOCKED)
    for body in ({}, {"code": ""}, {"code": "x" * 65}, {"code": "ABC", "amount": 5}):
        response = await auth_client.post(CODE, json=body, headers=customer.headers)
        _error(response, 400, "VALIDATION_ERROR")
    # No cart yet: nothing to apply the code to.
    _error(
        await auth_client.post(CODE, json={"code": "ABCD"}, headers=customer.headers),
        404,
        "NOT_FOUND",
    )
    for headers, status, code in (
        ({"Authorization": "Bearer nope"}, 401, "UNAUTHORIZED"),
        (blocked.headers, 403, "FORBIDDEN"),
    ):
        _error(await auth_client.post(CODE, json={"code": "ABCD"}, headers=headers), status, code)
        _error(await auth_client.delete(CODE, headers=headers), status, code)


# --- rate limit ----------------------------------------------------------------------


async def test_owner_cap_gives_429_and_success_never_resets_it(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    codes: Any,
    db_engine: AsyncEngine,
    limits: Callable[..., None],
) -> None:
    limits(discount_max_failed_per_owner=3)
    customer = await make_account("customer")
    await _user_cart(
        auth_client,
        customer.headers,
        await catalog.variant(await catalog.product(), stock=(5, 0, 0)),
    )
    good = await codes()

    for attempt in range(3):
        if attempt == 1:
            # A success in between does not reset the count.
            ok = await auth_client.post(CODE, json={"code": good.code}, headers=customer.headers)
            assert ok.status_code == 200
        response = await auth_client.post(CODE, json={"code": "WRONG-1"}, headers=customer.headers)
        assert response.status_code == 422
    blocked = await auth_client.post(CODE, json={"code": good.code}, headers=customer.headers)

    _error(blocked, 429, "RATE_LIMITED", "too_many_attempts_owner")
    assert 1 <= int(blocked.headers["retry-after"]) <= 900
    # A 429 evaluates and records nothing.
    assert await _attempts(db_engine) == 3


async def test_retry_after_counts_from_the_attempt_that_frees_a_slot(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    db_engine: AsyncEngine,
    limits: Callable[..., None],
) -> None:
    limits(discount_max_failed_per_owner=2)
    customer = await make_account("customer")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    await _user_cart(auth_client, customer.headers, variant)
    now = utc_now()
    async with AsyncSession(db_engine) as session, session.begin():
        # Three in the window (over the cap of 2): the 2nd oldest frees the slot.
        for minutes in (14, 10, 1):
            session.add(
                DiscountAttempt(user_id=customer.id, created_at=now - timedelta(minutes=minutes))
            )

    blocked = await auth_client.post(CODE, json={"code": "ANY-CODE"}, headers=customer.headers)

    _error(blocked, 429, "RATE_LIMITED", "too_many_attempts_owner")
    # 15-minute window, freed when the 10-minute-old attempt leaves it: about 5 minutes.
    assert 280 <= int(blocked.headers["retry-after"]) <= 301


async def test_global_cap_counts_every_owner(
    auth_client: AsyncClient,
    catalog: Catalog,
    db_engine: AsyncEngine,
    limits: Callable[..., None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    limits(
        discount_max_failed_global=2,
        discount_max_failed_per_owner=100,
        discount_max_failed_per_ip=100,
    )
    variant = await catalog.variant(await catalog.product(), stock=(9, 0, 0))
    for _ in range(2):
        await _guest_cart(auth_client, variant)
        assert (await auth_client.post(CODE, json={"code": "WRONG-4"})).status_code == 422
    await _guest_cart(auth_client, variant)

    with caplog.at_level("WARNING"):
        response = await auth_client.post(CODE, json={"code": "WRONG-4"})

    _error(response, 429, "RATE_LIMITED", "too_many_attempts_global")
    assert "discount.global_attempt_cap_reached" in caplog.text
    assert await _attempts(db_engine) == 2


async def test_ip_cap_spans_carts_and_is_exact_under_concurrency(
    auth_client: AsyncClient,
    catalog: Catalog,
    db_engine: AsyncEngine,
    limits: Callable[..., None],
) -> None:
    limits(discount_max_failed_per_ip=3, discount_max_failed_per_owner=100)
    variant = await catalog.variant(await catalog.product(), stock=(50, 0, 0))
    tokens = [await _guest_cart(auth_client, variant) for _ in range(7)]
    auth_client.cookies.clear()
    # One client per guest cart (the same app and client IP).
    clients = [
        AsyncClient(
            transport=auth_client._transport,
            base_url=str(auth_client.base_url),
            cookies={CART_COOKIE_NAME: token},
        )
        for token in tokens
    ]
    try:
        # Two failures from two carts first: one below the cap.
        for client in clients[:2]:
            response = await client.post(CODE, json={"code": "WRONG-2"})
            assert response.status_code == 422

        results = await asyncio.gather(
            *(client.post(CODE, json={"code": "WRONG-2"}) for client in clients[2:])
        )
    finally:
        for client in clients:
            await client.aclose()

    assert sorted(response.status_code for response in results) == [422, 429, 429, 429, 429]
    assert await _attempts(db_engine) == 3


async def test_old_attempts_are_purged_and_no_longer_count(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    db_engine: AsyncEngine,
    limits: Callable[..., None],
) -> None:
    limits(discount_max_failed_per_owner=2)
    customer = await make_account("customer")
    await _user_cart(
        auth_client,
        customer.headers,
        await catalog.variant(await catalog.product(), stock=(5, 0, 0)),
    )
    async with AsyncSession(db_engine) as session, session.begin():
        old = utc_now() - timedelta(hours=1)
        session.add_all(DiscountAttempt(user_id=customer.id, created_at=old) for _ in range(5))

    response = await auth_client.post(CODE, json={"code": "WRONG-3"}, headers=customer.headers)

    assert response.status_code == 422
    assert await _attempts(db_engine) == 1


# --- reading, removing, merging ------------------------------------------------------


async def test_reads_recheck_an_applied_code(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, codes: Any
) -> None:
    customer = await make_account("customer")
    await _user_cart(
        auth_client,
        customer.headers,
        await catalog.variant(await catalog.product(), stock=(5, 0, 0)),
    )
    code = await codes()
    await auth_client.post(CODE, json={"code": code.code}, headers=customer.headers)

    await catalog.set(DiscountCode, code.id, ends_at=utc_now(), starts_at=utc_now() - timedelta(1))
    expired = (await auth_client.get(CART, headers=customer.headers)).json()
    await catalog.set(DiscountCode, code.id, ends_at=None, starts_at=None, deleted_at=utc_now())
    deleted = (await auth_client.get(CART, headers=customer.headers)).json()

    assert expired["discount"] == {"code": code.code, "applied": False, "reason": "expired"}
    assert expired["discount_code_amount"] == 0 and expired["has_changes"] is True
    assert deleted["discount"]["reason"] == "invalid"


async def test_remove_is_idempotent_and_needs_no_cart(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, codes: Any
) -> None:
    customer = await make_account("customer")
    auth_client.cookies.clear()
    empty = await auth_client.delete(CODE)
    assert empty.status_code == 200 and empty.json()["items"] == []
    assert "set-cookie" not in empty.headers and empty.headers["cache-control"] == "no-store"

    await _user_cart(
        auth_client,
        customer.headers,
        await catalog.variant(await catalog.product(), stock=(5, 0, 0)),
    )
    code = await codes()
    await auth_client.post(CODE, json={"code": code.code}, headers=customer.headers)
    for _ in range(2):
        removed = await auth_client.delete(CODE, headers=customer.headers)
        assert removed.status_code == 200 and removed.json()["discount"] is None


async def test_login_merges_the_code_and_checks_the_per_user_limit(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    catalog: Catalog,
    codes: Any,
    db_engine: AsyncEngine,
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    code = await codes(usage_limit_per_user=1)
    mobile = f"+989{uuid4().int % 1_000_000_000:09d}"
    await _redeem(db_engine, code, phone=mobile)
    await _guest_cart(auth_client, variant)
    # A guest has no verified mobile: the per-user limit is not checked yet.
    applied = await auth_client.post(CODE, json={"code": code.code})
    assert applied.status_code == 200 and applied.json()["discount"]["applied"] is True

    await issue_otp(mobile)
    login = await auth_client.post(
        f"{API}/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    auth_client.cookies.clear()
    try:
        cart = (await auth_client.get(CART, headers=headers)).json()
        assert cart["discount"] == {"code": code.code, "applied": False, "reason": "user_exhausted"}
    finally:
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(User).where(User.phone == mobile))


async def test_merge_keeps_the_users_own_code(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    catalog: Catalog,
    codes: Any,
    db_engine: AsyncEngine,
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(9, 0, 0))
    user_code, guest_code = await codes(), await codes()
    mobile = f"+989{uuid4().int % 1_000_000_000:09d}"
    await issue_otp(mobile)
    auth_client.cookies.clear()
    first = await auth_client.post(
        f"{API}/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
    )
    headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    try:
        await _user_cart(auth_client, headers, variant)
        assert (
            await auth_client.post(CODE, json={"code": user_code.code}, headers=headers)
        ).status_code == 200
        await _guest_cart(auth_client, variant)
        assert (await auth_client.post(CODE, json={"code": guest_code.code})).status_code == 200
        await issue_otp(mobile)
        second = await auth_client.post(
            f"{API}/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
        )
        assert second.status_code == 200, second.text
        auth_client.cookies.clear()
        cart = (await auth_client.get(CART, headers=headers)).json()
        assert cart["discount"]["code"] == user_code.code
    finally:
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(User).where(User.phone == mobile))


async def test_signed_in_user_over_the_per_user_limit_gets_422(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    codes: Any,
    db_engine: AsyncEngine,
) -> None:
    customer = await make_account("customer")
    await _user_cart(
        auth_client,
        customer.headers,
        await catalog.variant(await catalog.product(), stock=(5, 0, 0)),
    )
    code = await codes(usage_limit_per_user=1)
    async with AsyncSession(db_engine) as session:
        phone = await session.scalar(select(User.phone).where(User.id == customer.id))
    assert phone is not None
    await _redeem(db_engine, code, phone=phone)

    response = await auth_client.post(CODE, json={"code": code.code}, headers=customer.headers)

    _error(response, 422, "DISCOUNT_NOT_APPLICABLE", "user_exhausted")
