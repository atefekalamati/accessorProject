"""Cart and CartItem schema, guest token helpers and user-cart creation (CART-01)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from http.cookies import SimpleCookie
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from conftest import Catalog, MakeAccount
from fastapi import Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import Cart, CartItem, CartStatus
from app.modules.cart.repository import CartRepository
from app.modules.cart.tokens import (
    CART_COOKIE_NAME,
    GUEST_CART_TTL,
    clear_cart_cookie,
    generate_cart_token,
    hash_cart_token,
    parse_cart_token,
    set_cart_cookie,
)
from app.shared.inventory import MAX_STOCK_QUANTITY

# --- token helpers (no database) -----------------------------------------------------


def test_tokens_are_random_and_only_their_hash_is_stored() -> None:
    first, second = generate_cart_token(), generate_cart_token()

    assert first != second
    assert parse_cart_token(first) == first
    digest = hash_cart_token(first)
    assert len(digest) == 64 and first not in digest
    assert hash_cart_token(first) == digest


@pytest.mark.parametrize(
    "raw", [None, "", "short", "x" * 44, "a" * 42 + "!", "' OR 1=1 --" + "a" * 32]
)
def test_malformed_cookie_values_are_ignored(raw: str | None) -> None:
    assert parse_cart_token(raw) is None


def _cookie(response: Response) -> Any:
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[CART_COOKIE_NAME]


def test_cookie_attributes() -> None:
    """D30: HttpOnly, Secure, SameSite=Lax, Path=/api/v1, 30 days."""
    response = Response()
    set_cart_cookie(response, "t" * 43)

    morsel = _cookie(response)
    assert morsel.value == "t" * 43
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"].lower() == "lax"
    assert morsel["path"] == "/api/v1"
    assert int(morsel["max-age"]) == int(GUEST_CART_TTL.total_seconds())

    cleared = Response()
    clear_cart_cookie(cleared)
    gone = _cookie(cleared)
    assert gone.value == "" and int(gone["max-age"]) == 0 and gone["path"] == "/api/v1"


# --- schema (integration) ------------------------------------------------------------


@pytest_asyncio.fixture
async def guest_carts(db_engine: AsyncEngine) -> AsyncIterator[list[UUID]]:
    ids: list[UUID] = []
    yield ids
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(Cart).where(Cart.id.in_(ids)))


async def _insert(engine: AsyncEngine, row: Any) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(row)


def _guest(**values: Any) -> Cart:
    defaults: dict[str, Any] = {
        "token_hash": hash_cart_token(generate_cart_token()),
        "expires_at": utc_now() + GUEST_CART_TTL,
    }
    return Cart(**(defaults | values))


@pytest.mark.integration
@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"token_hash": None, "expires_at": None}, "ck_carts_one_owner"),
        ({"token_hash": "A" * 64}, "ck_carts_token_hash_format"),
        ({"token_hash": "raw-token"}, "ck_carts_token_hash_format"),
        ({"expires_at": None}, "ck_carts_guest_expires"),
        ({"status": "converted"}, "ck_carts_valid_status"),
    ],
)
async def test_cart_checks(db_engine: AsyncEngine, values: dict[str, Any], constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await _insert(db_engine, _guest(**values))


@pytest.mark.integration
async def test_user_cart_has_no_token_or_expiry(
    db_engine: AsyncEngine, make_account: MakeAccount
) -> None:
    account = await make_account("customer")
    with pytest.raises(IntegrityError, match="ck_carts_one_owner"):
        await _insert(db_engine, _guest(user_id=account.id))
    with pytest.raises(IntegrityError, match="ck_carts_guest_expires"):
        await _insert(db_engine, Cart(user_id=account.id, expires_at=utc_now()))


@pytest.mark.integration
async def test_one_active_cart_per_user(db_engine: AsyncEngine, make_account: MakeAccount) -> None:
    account = await make_account("customer")
    await _insert(db_engine, Cart(user_id=account.id))
    # A closed cart does not count.
    await _insert(db_engine, Cart(user_id=account.id, status=CartStatus.MERGED))

    with pytest.raises(IntegrityError, match="uq_carts_active_user"):
        await _insert(db_engine, Cart(user_id=account.id))


@pytest.mark.integration
async def test_cart_item_checks(
    db_engine: AsyncEngine, catalog: Catalog, guest_carts: list[UUID]
) -> None:
    product = await catalog.product()
    variant = await catalog.variant(product)
    other = await catalog.variant(await catalog.product())
    cart = _guest()
    await _insert(db_engine, cart)
    guest_carts.append(cart.id)

    def line(**values: Any) -> CartItem:
        base = {"cart_id": cart.id, "product_id": product.id, "variant_id": variant.id}
        defaults = {"quantity": 1, "seen_unit_price": 100_000, "seen_price_version": 0}
        return CartItem(**(base | defaults | values))

    for quantity in (0, MAX_STOCK_QUANTITY + 1):
        with pytest.raises(IntegrityError, match="ck_cart_items_quantity_range"):
            await _insert(db_engine, line(quantity=quantity))
    with pytest.raises(IntegrityError, match="fk_cart_items_variant_id_product_variants"):
        await _insert(db_engine, line(variant_id=other.id))  # variant of another product
    await _insert(db_engine, line())
    with pytest.raises(IntegrityError, match="uq_cart_items_cart_id"):
        await _insert(db_engine, line(quantity=2))

    # Deleting the cart deletes its lines.
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(Cart).where(Cart.id == cart.id))
    async with AsyncSession(db_engine) as session:
        left = await session.scalar(
            select(func.count()).select_from(CartItem).where(CartItem.cart_id == cart.id)
        )
    assert left == 0


@pytest.mark.integration
async def test_concurrent_first_writes_create_one_user_cart(
    db_engine: AsyncEngine, make_account: MakeAccount
) -> None:
    account = await make_account("customer")

    async def lock() -> UUID:
        async with AsyncSession(db_engine) as session, session.begin():
            return (await CartRepository(session).lock_user_cart(account.id)).id

    ids = await asyncio.gather(*(lock() for _ in range(5)))

    assert len(set(ids)) == 1


@pytest.mark.integration
async def test_guest_cart_lookup_ignores_expired_and_closed_carts(
    db_engine: AsyncEngine, guest_carts: list[UUID]
) -> None:
    now = utc_now()
    live, old, merged = (generate_cart_token() for _ in range(3))
    async with AsyncSession(db_engine) as session, session.begin():
        repository = CartRepository(session)
        for token in (live, old, merged):
            guest_carts.append((await repository.create_guest_cart(hash_cart_token(token), now)).id)
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            update(Cart)
            .where(Cart.token_hash == hash_cart_token(merged))
            .values(status=CartStatus.MERGED)
        )

    async with AsyncSession(db_engine) as session:
        repository = CartRepository(session)
        assert await repository.find_guest_cart(hash_cart_token(live), now) is not None
        later = now + GUEST_CART_TTL + timedelta(seconds=1)
        assert await repository.find_guest_cart(hash_cart_token(old), later) is None
        assert await repository.find_guest_cart(hash_cart_token(merged), now) is None


@pytest.mark.integration
async def test_user_cart_upsert_survives_generic_plans(
    db_engine: AsyncEngine, make_account: MakeAccount
) -> None:
    """asyncpg switches to a generic plan after five runs of one statement; the
    ON CONFLICT predicate must still match the partial index (literal, not a parameter)."""
    account = await make_account("customer")
    # One connection for the whole loop: asyncpg caches prepared statements per connection.
    async with db_engine.connect() as connection, AsyncSession(bind=connection) as session:
        ids = set()
        for _ in range(8):
            async with session.begin():
                ids.add((await CartRepository(session).lock_user_cart(account.id)).id)
    assert len(ids) == 1
