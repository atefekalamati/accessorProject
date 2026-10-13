"""Guest cart → user cart at login (CART-04, D30, ADR-040)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from http.cookies import SimpleCookie
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Catalog, MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import (
    Cart,
    CartItem,
    CartStatus,
    InventoryItem,
    OtpCode,
    ProductVariant,
    User,
)
from app.db.models.cart import MAX_CART_LINES
from app.modules.cart.merge import CartMerger
from app.modules.cart.tokens import CART_COOKIE_NAME, hash_cart_token

pytestmark = pytest.mark.integration

ITEMS = "/api/v1/cart/items"
CART = "/api/v1/cart"
VERIFY = "/api/v1/auth/verify-otp"


@pytest_asyncio.fixture
async def cleanup(db_engine: AsyncEngine) -> AsyncIterator[list[str]]:
    """Users created by logging in, and guest carts made by this test."""
    started = utc_now()
    mobiles: list[str] = []
    yield mobiles
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            delete(Cart).where(Cart.user_id.is_(None), Cart.created_at >= started)
        )
        await session.execute(delete(User).where(User.phone.in_(mobiles)))


def _cookies(response: Response) -> dict[str, Any]:
    jar: dict[str, Any] = {}
    for header in response.headers.get_list("set-cookie"):
        cookie: SimpleCookie = SimpleCookie()
        cookie.load(header)
        jar.update(cookie)
    return jar


async def _guest_cart(client: AsyncClient, *lines: tuple[ProductVariant, int]) -> str:
    client.cookies.clear()
    token: str | None = None
    for variant, quantity in lines:
        response = await client.post(
            ITEMS, json={"variant_id": str(variant.id), "quantity": quantity}
        )
        assert response.status_code == 201, response.text
        token = response.cookies.get(CART_COOKIE_NAME, token)
        client.cookies.set(CART_COOKIE_NAME, token or "")
    assert token is not None
    return token


async def _login(
    client: AsyncClient, issue_otp: Callable[..., Awaitable[OtpCode]], mobile: str
) -> Response:
    await issue_otp(mobile)
    response = await client.post(VERIFY, json={"mobile": mobile, "code": "123456"})
    assert response.status_code == 200, response.text
    return response


def _mobile() -> str:
    return f"+989{uuid4().int % 1_000_000_000:09d}"


async def _user_lines(engine: AsyncEngine, mobile: str) -> dict[UUID, CartItem]:
    async with AsyncSession(engine) as session:
        statement = (
            select(CartItem)
            .join(Cart, Cart.id == CartItem.cart_id)
            .join(User, User.id == Cart.user_id)
            .where(User.phone == mobile, Cart.status == CartStatus.ACTIVE)
        )
        return {line.variant_id: line for line in await session.scalars(statement)}


async def _guest_status(engine: AsyncEngine, token: str) -> str:
    async with AsyncSession(engine) as session:
        statement = select(Cart.status).where(Cart.token_hash == hash_cart_token(token))
        return (await session.scalars(statement)).one()


async def test_login_moves_the_guest_cart_and_clears_its_cookie(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    catalog: Catalog,
    db_engine: AsyncEngine,
    cleanup: list[str],
) -> None:
    product = await catalog.product()
    first = await catalog.variant(product, stock=(5, 0, 0), base_price=4_000)
    second = await catalog.variant(product, stock=(5, 0, 0))
    token = await _guest_cart(auth_client, (first, 2), (second, 1))
    await catalog.set(ProductVariant, first.id, base_price=4_400)  # the guest saw 4 000
    mobile = _mobile()
    cleanup.append(mobile)

    response = await _login(auth_client, issue_otp, mobile)

    cookies = _cookies(response)
    assert cookies[CART_COOKIE_NAME].value == "" and int(cookies[CART_COOKIE_NAME]["max-age"]) == 0
    assert cookies[CART_COOKIE_NAME]["path"] == "/api/v1"
    assert "refresh_token" in cookies  # the login itself is unchanged
    lines = await _user_lines(db_engine, mobile)
    assert {variant_id: line.quantity for variant_id, line in lines.items()} == {
        first.id: 2,
        second.id: 1,
    }
    assert await _guest_status(db_engine, token) == CartStatus.MERGED
    # The moved line keeps the price the guest saw, so the change is still flagged.
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    auth_client.cookies.clear()
    cart = (await auth_client.get(CART, headers=headers)).json()
    [moved] = [item for item in cart["items"] if item["variant_id"] == str(first.id)]
    assert (moved["price_changed"], moved["previous_unit_price"]) == (True, 4_000)


async def test_lines_combine_up_to_free_stock_and_unsellable_ones_drop(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    catalog: Catalog,
    db_engine: AsyncEngine,
    cleanup: list[str],
) -> None:
    product = await catalog.product()
    shared = await catalog.variant(product, stock=(3, 0, 0))
    hidden = await catalog.variant(product, stock=(5, 0, 0))
    sold_out = await catalog.variant(product, stock=(2, 0, 0))
    mobile = _mobile()
    cleanup.append(mobile)
    # The user already holds 2 of `shared`.
    access = (await _login(auth_client, issue_otp, mobile)).json()["access_token"]
    auth_client.cookies.clear()
    added = await auth_client.post(
        ITEMS,
        json={"variant_id": str(shared.id), "quantity": 2},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert added.status_code == 201
    await _guest_cart(auth_client, (shared, 2), (hidden, 1), (sold_out, 2))
    await catalog.set(ProductVariant, hidden.id, deleted_at=utc_now())
    async with AsyncSession(db_engine) as session, session.begin():
        item = (
            await session.scalars(
                select(InventoryItem).where(InventoryItem.variant_id == sold_out.id)
            )
        ).one()
        item.total_quantity = 0

    await _login(auth_client, issue_otp, mobile)

    lines = await _user_lines(db_engine, mobile)
    assert {variant_id: line.quantity for variant_id, line in lines.items()} == {shared.id: 3}


async def test_merge_never_lowers_the_users_line(
    catalog: Catalog, db_engine: AsyncEngine, make_account: MakeAccount, cleanup: list[str]
) -> None:
    """Free stock below what the user already has: the line keeps its quantity."""
    account = await make_account("customer")
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    now = utc_now()
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        user_cart = Cart(user_id=account.id)
        guest_cart = Cart(token_hash=hash_cart_token("g" * 43), expires_at=now + timedelta(days=1))
        session.add_all([user_cart, guest_cart])
        await session.flush()
        for cart, quantity in ((user_cart, 4), (guest_cart, 3)):
            session.add(
                CartItem(
                    cart_id=cart.id,
                    product_id=variant.product_id,
                    variant_id=variant.id,
                    quantity=quantity,
                    seen_unit_price=100_000,
                    seen_price_version=0,
                )
            )
    await catalog.set(ProductVariant, variant.id, base_price=100_000)
    async with AsyncSession(db_engine) as session, session.begin():
        item = (
            await session.scalars(
                select(InventoryItem).where(InventoryItem.variant_id == variant.id)
            )
        ).one()
        item.total_quantity = 2

    async with AsyncSession(db_engine) as session:
        result = await CartMerger(session).merge(account.id, "g" * 43)

    assert (result.merged, result.combined) == (True, 1)
    async with AsyncSession(db_engine) as session:
        stored = await session.scalar(
            select(CartItem.quantity).where(CartItem.cart_id == user_cart.id)
        )
    assert stored == 4


async def test_merge_is_idempotent_under_concurrency(
    catalog: Catalog, db_engine: AsyncEngine, make_account: MakeAccount, cleanup: list[str]
) -> None:
    account = await make_account("customer")
    variant = await catalog.variant(await catalog.product(), stock=(9, 0, 0))
    token = "c" * 43
    async with AsyncSession(db_engine) as session, session.begin():
        guest = Cart(token_hash=hash_cart_token(token), expires_at=utc_now() + timedelta(days=1))
        session.add(guest)
        await session.flush()
        session.add(
            CartItem(
                cart_id=guest.id,
                product_id=variant.product_id,
                variant_id=variant.id,
                quantity=3,
                seen_unit_price=100_000,
                seen_price_version=0,
            )
        )

    async def merge() -> bool:
        async with AsyncSession(db_engine) as session:
            return (await CartMerger(session).merge(account.id, token)).merged

    results = await asyncio.gather(*(merge() for _ in range(4)))

    assert sorted(results) == [False, False, False, True]
    async with AsyncSession(db_engine) as session:
        lines = list(
            await session.scalars(
                select(CartItem.quantity)
                .join(Cart, Cart.id == CartItem.cart_id)
                .where(Cart.user_id == account.id)
            )
        )
    assert lines == [3]


async def test_line_cap_drops_new_lines(
    catalog: Catalog, db_engine: AsyncEngine, make_account: MakeAccount, cleanup: list[str]
) -> None:
    account = await make_account("customer")
    product = await catalog.product()
    variants = [await catalog.variant(product, stock=(5, 0, 0)) for _ in range(MAX_CART_LINES + 1)]
    token = "d" * 43
    async with AsyncSession(db_engine) as session, session.begin():
        user_cart = Cart(user_id=account.id)
        guest = Cart(token_hash=hash_cart_token(token), expires_at=utc_now() + timedelta(days=1))
        session.add_all([user_cart, guest])
        await session.flush()
        lines = [(user_cart, variant) for variant in variants[:MAX_CART_LINES]]
        lines.append((guest, variants[-1]))
        session.add_all(
            CartItem(
                cart_id=cart.id,
                product_id=product.id,
                variant_id=variant.id,
                quantity=1,
                seen_unit_price=100_000,
                seen_price_version=0,
            )
            for cart, variant in lines
        )

    async with AsyncSession(db_engine) as session:
        result = await CartMerger(session).merge(account.id, token)

    assert (result.moved, result.dropped) == (0, 1)


@pytest.mark.parametrize("cookie", ["not-a-token", "e" * 43])
async def test_bad_or_unknown_cookie_never_blocks_login(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    cleanup: list[str],
    cookie: str,
) -> None:
    mobile = _mobile()
    cleanup.append(mobile)
    auth_client.cookies.clear()
    auth_client.cookies.set(CART_COOKIE_NAME, cookie)

    response = await _login(auth_client, issue_otp, mobile)

    assert int(_cookies(response)[CART_COOKIE_NAME]["max-age"]) == 0


async def test_no_cookie_means_no_cart_cookie(
    auth_client: AsyncClient, issue_otp: Callable[..., Awaitable[OtpCode]], cleanup: list[str]
) -> None:
    mobile = _mobile()
    cleanup.append(mobile)
    auth_client.cookies.clear()

    response = await _login(auth_client, issue_otp, mobile)

    assert CART_COOKIE_NAME not in _cookies(response)


async def test_a_failed_merge_keeps_the_login_and_the_cookie(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    catalog: Catalog,
    cleanup: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variant = await catalog.variant(await catalog.product(), stock=(5, 0, 0))
    await _guest_cart(auth_client, (variant, 1))
    mobile = _mobile()
    cleanup.append(mobile)

    async def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(CartMerger, "merge", broken)
    response = await _login(auth_client, issue_otp, mobile)

    assert response.json()["access_token"]
    assert CART_COOKIE_NAME not in _cookies(response)
