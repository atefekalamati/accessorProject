"""Cart line writes: guest cookie and user carts, free stock, no reservation (CART-02)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from http.cookies import SimpleCookie
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Catalog, MakeAccount, nested_keys, new_order
from httpx import AsyncClient, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import (
    Cart,
    CartItem,
    CartStatus,
    InventoryItem,
    InventoryReservation,
    Product,
    ProductStatus,
    ProductVariant,
    User,
    UserStatus,
    Warehouse,
    WarehouseStatus,
)
from app.db.models.cart import MAX_CART_LINES
from app.modules.cart.tokens import CART_COOKIE_NAME, GUEST_CART_TTL, hash_cart_token
from app.modules.inventory.reservation import ReservationService, ReserveLine

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("order_factory")]

URL = "/api/v1/cart/items"
PAST = timedelta(minutes=20)


def _error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    return body


def _token(response: Response) -> str:
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[CART_COOKIE_NAME].value


@pytest_asyncio.fixture
async def guest_cleanup(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """Guest carts have no user to cascade from; remove the ones this test made."""
    started = utc_now()
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            delete(Cart).where(Cart.user_id.is_(None), Cart.created_at >= started)
        )


async def _guest_client(client: AsyncClient, token: str | None) -> None:
    client.cookies.clear()
    if token is not None:
        client.cookies.set(CART_COOKIE_NAME, token)


async def _lines(engine: AsyncEngine, cart_id: UUID) -> dict[UUID, int]:
    async with AsyncSession(engine) as session:
        rows = await session.execute(
            select(CartItem.variant_id, CartItem.quantity).where(CartItem.cart_id == cart_id)
        )
        return {variant_id: quantity for variant_id, quantity in rows}


async def _guest_cart(engine: AsyncEngine, token: str) -> Cart:
    async with AsyncSession(engine) as session:
        statement = select(Cart).where(Cart.token_hash == hash_cart_token(token))
        return (await session.scalars(statement)).one()


async def _item_row(engine: AsyncEngine, variant_id: UUID) -> InventoryItem:
    async with AsyncSession(engine) as session:
        statement = select(InventoryItem).where(InventoryItem.variant_id == variant_id)
        return (await session.scalars(statement)).one()


async def _stocked(catalog: Catalog, total: int, **fields: Any) -> ProductVariant:
    return await catalog.variant(await catalog.product(), stock=(total, 0, 0), **fields)


# --- guest ---------------------------------------------------------------------------


async def test_guest_add_creates_a_cart_cookie_and_reserves_nothing(
    auth_client: AsyncClient, catalog: Catalog, db_engine: AsyncEngine, guest_cleanup: None
) -> None:
    variant = await _stocked(catalog, 5)

    first = await auth_client.post(URL, json={"variant_id": str(variant.id), "quantity": 2})

    assert first.status_code == 201, first.text
    assert first.headers["cache-control"] == "no-store"
    body = first.json()
    assert (body["variant_id"], body["product_id"], body["quantity"]) == (
        str(variant.id),
        str(variant.product_id),
        2,
    )
    token = _token(first)
    assert token not in first.text  # the token travels in the cookie only
    cart = await _guest_cart(db_engine, token)
    assert cart.user_id is None and cart.expires_at is not None

    await _guest_client(auth_client, token)
    again = await auth_client.post(URL, json={"variant_id": str(variant.id), "quantity": 3})

    assert again.status_code == 201, again.text
    assert again.json()["id"] == body["id"]
    assert _token(again) == token  # an existing guest cart gets its cookie renewed
    assert await _lines(db_engine, cart.id) == {variant.id: 5}
    async with AsyncSession(db_engine) as session:
        item = (
            await session.scalars(
                select(InventoryItem).where(InventoryItem.variant_id == variant.id)
            )
        ).one()
    assert (item.total_quantity, item.reserved_quantity) == (5, 0)
    async with AsyncSession(db_engine) as session:
        mine = await session.scalar(
            select(func.count())
            .select_from(InventoryReservation)
            .where(InventoryReservation.cart_id == cart.id)
        )
    assert mine == 0


async def test_unknown_or_malformed_cookie_starts_a_new_cart(
    auth_client: AsyncClient, catalog: Catalog, guest_cleanup: None
) -> None:
    variant = await _stocked(catalog, 5)
    for token in ("not-a-token", "A" * 43):
        await _guest_client(auth_client, token)
        response = await auth_client.post(URL, json={"variant_id": str(variant.id), "quantity": 1})
        assert response.status_code == 201, response.text
        assert _token(response) != token


@pytest.mark.parametrize("closed", ["expired", "merged"])
async def test_closed_guest_cart_is_not_reused(
    auth_client: AsyncClient,
    catalog: Catalog,
    db_engine: AsyncEngine,
    guest_cleanup: None,
    closed: str,
) -> None:
    variant = await _stocked(catalog, 5)
    await _guest_client(auth_client, None)
    created = await auth_client.post(URL, json={"variant_id": str(variant.id), "quantity": 1})
    token = _token(created)
    cart = await _guest_cart(db_engine, token)
    if closed == "expired":
        await catalog.set(Cart, cart.id, expires_at=utc_now() - timedelta(seconds=1))
    else:
        await catalog.set(Cart, cart.id, status=CartStatus.MERGED)

    await _guest_client(auth_client, token)
    _error(await auth_client.delete(f"{URL}/{created.json()['id']}"), 404, "NOT_FOUND")
    response = await auth_client.post(URL, json={"variant_id": str(variant.id), "quantity": 1})

    assert response.status_code == 201, response.text
    assert _token(response) != token
    assert await _lines(db_engine, cart.id) == {variant.id: 1}  # the old cart is untouched


async def test_guest_patch_or_delete_without_a_cart_is_404_and_sets_no_cookie(
    auth_client: AsyncClient, guest_cleanup: None
) -> None:
    await _guest_client(auth_client, None)
    for response in (
        await auth_client.patch(f"{URL}/{uuid4()}", json={"quantity": 1}),
        await auth_client.delete(f"{URL}/{uuid4()}"),
    ):
        _error(response, 404, "NOT_FOUND")
        assert "set-cookie" not in response.headers


async def test_cross_site_form_post_creates_no_cart(
    auth_client: AsyncClient, catalog: Catalog, db_engine: AsyncEngine, guest_cleanup: None
) -> None:
    """A cross-site form can only send simple content types; they never reach the cart."""
    variant = await _stocked(catalog, 5)
    started = utc_now()
    await _guest_client(auth_client, None)

    response = await auth_client.post(
        URL,
        content=f'{{"variant_id": "{variant.id}", "quantity": 1}}',
        headers={"Content-Type": "text/plain"},
    )

    _error(response, 400, "VALIDATION_ERROR")
    assert "set-cookie" not in response.headers
    async with AsyncSession(db_engine) as session:
        created = await session.scalar(
            select(func.count()).select_from(Cart).where(Cart.created_at >= started)
        )
    assert created == 0


async def test_writes_slide_the_guest_expiry(
    auth_client: AsyncClient, catalog: Catalog, db_engine: AsyncEngine, guest_cleanup: None
) -> None:
    variant = await _stocked(catalog, 5)
    await _guest_client(auth_client, None)
    created = await auth_client.post(URL, json={"variant_id": str(variant.id), "quantity": 1})
    token = _token(created)
    cart = await _guest_cart(db_engine, token)
    soon = utc_now() + timedelta(days=1)
    await catalog.set(Cart, cart.id, expires_at=soon)

    await _guest_client(auth_client, token)
    response = await auth_client.patch(f"{URL}/{created.json()['id']}", json={"quantity": 2})

    assert response.status_code == 200, response.text
    assert _token(response) == token
    renewed = await _guest_cart(db_engine, token)
    assert renewed.expires_at is not None
    assert renewed.expires_at > utc_now() + GUEST_CART_TTL - timedelta(minutes=1)
    await catalog.set(Cart, cart.id, expires_at=soon)
    removed = await auth_client.delete(f"{URL}/{created.json()['id']}")
    assert removed.status_code == 204 and _token(removed) == token
    renewed = await _guest_cart(db_engine, token)
    assert renewed.expires_at is not None and renewed.expires_at > soon


# --- user ----------------------------------------------------------------------------


async def test_user_cart_ignores_the_guest_cookie(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    db_engine: AsyncEngine,
    guest_cleanup: None,
) -> None:
    variant = await _stocked(catalog, 5)
    customer = await make_account("customer")
    await _guest_client(auth_client, None)
    guest_token = _token(
        await auth_client.post(URL, json={"variant_id": str(variant.id), "quantity": 1})
    )

    await _guest_client(auth_client, guest_token)
    response = await auth_client.post(
        URL, json={"variant_id": str(variant.id), "quantity": 2}, headers=customer.headers
    )

    assert response.status_code == 201, response.text
    assert "set-cookie" not in response.headers
    async with AsyncSession(db_engine) as session:
        cart = (await session.scalars(select(Cart).where(Cart.user_id == customer.id))).one()
    assert await _lines(db_engine, cart.id) == {variant.id: 2}
    assert await _lines(db_engine, (await _guest_cart(db_engine, guest_token)).id) == {
        variant.id: 1
    }


async def test_bad_bearer_is_401_even_with_a_cart_cookie(
    auth_client: AsyncClient, catalog: Catalog, guest_cleanup: None
) -> None:
    variant = await _stocked(catalog, 5)
    await _guest_client(auth_client, None)
    token = _token(await auth_client.post(URL, json={"variant_id": str(variant.id), "quantity": 1}))
    await _guest_client(auth_client, token)
    body = {"variant_id": str(variant.id), "quantity": 1}

    for header in ("Bearer nope", "Basic abc", "Bearer "):
        response = await auth_client.post(URL, json=body, headers={"Authorization": header})
        _error(response, 401, "UNAUTHORIZED")


async def test_blocked_user_is_403(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    variant = await _stocked(catalog, 5)
    customer = await make_account("customer")
    await catalog.set(User, customer.id, status=UserStatus.BLOCKED)

    response = await auth_client.post(
        URL, json={"variant_id": str(variant.id), "quantity": 1}, headers=customer.headers
    )

    _error(response, 403, "FORBIDDEN")


async def test_user_without_a_cart_gets_404_and_no_cart(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    customer = await make_account("customer")
    headers = customer.headers
    for response in (
        await auth_client.patch(f"{URL}/{uuid4()}", json={"quantity": 1}, headers=headers),
        await auth_client.delete(f"{URL}/{uuid4()}", headers=headers),
    ):
        _error(response, 404, "NOT_FOUND")
    async with AsyncSession(db_engine) as session:
        carts = await session.scalar(
            select(func.count()).select_from(Cart).where(Cart.user_id == customer.id)
        )
    assert carts == 0


# --- stock and sellability -----------------------------------------------------------


async def test_quantity_is_capped_by_effective_free_stock(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    db_engine: AsyncEngine,
) -> None:
    customer = await make_account("customer")
    variant = await _stocked(catalog, 5)
    # A live hold takes 2 units; an expired, unswept one holds nothing (ADR-036).
    for quantity, now in ((2, None), (3, utc_now() - PAST)):
        async with AsyncSession(db_engine) as session, session.begin():
            await ReservationService(session).reserve(
                order_id=await new_order(),
                lines=[ReserveLine(variant.id, quantity)],
                user_id=None,
                now=now,
            )
    headers = customer.headers

    ok = await auth_client.post(
        URL, json={"variant_id": str(variant.id), "quantity": 3}, headers=headers
    )
    over = await auth_client.post(
        URL, json={"variant_id": str(variant.id), "quantity": 1}, headers=headers
    )

    assert ok.status_code == 201, ok.text
    body = _error(over, 409, "INSUFFICIENT_STOCK")
    # No stock numbers leak (ADR-029).
    assert not nested_keys(body) & {"available", "free", "total", "stock", "max_quantity"}
    assert all(
        not isinstance(value, int) for detail in body["details"] for value in detail.values()
    )
    assert not any(character.isdigit() for character in body["message"])
    _error(
        await auth_client.patch(f"{URL}/{ok.json()['id']}", json={"quantity": 4}, headers=headers),
        409,
        "INSUFFICIENT_STOCK",
    )
    # Lowering a line never needs stock, even when other buyers took the rest.
    async with AsyncSession(db_engine) as session, session.begin():
        await ReservationService(session).reserve(
            order_id=await new_order(), lines=[ReserveLine(variant.id, 2)], user_id=None
        )
    lowered = await auth_client.patch(
        f"{URL}/{ok.json()['id']}", json={"quantity": 1}, headers=headers
    )
    assert lowered.status_code == 200, lowered.text
    assert lowered.json()["quantity"] == 1


async def test_inactive_warehouse_stock_does_not_count(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    customer = await make_account("customer")
    product = await catalog.product()
    variant = await catalog.variant(product)
    warehouse = Warehouse(name="Closed", status=WarehouseStatus.INACTIVE, is_default=False)
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        session.add(warehouse)
        await session.flush()
        session.add(
            InventoryItem(
                warehouse_id=warehouse.id,
                product_id=product.id,
                variant_id=variant.id,
                total_quantity=10,
            )
        )
    try:
        response = await auth_client.post(
            URL, json={"variant_id": str(variant.id), "quantity": 1}, headers=customer.headers
        )
        _error(response, 409, "INSUFFICIENT_STOCK")
    finally:
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(
                delete(InventoryItem).where(InventoryItem.warehouse_id == warehouse.id)
            )
            await session.execute(delete(Warehouse).where(Warehouse.id == warehouse.id))


async def test_hidden_variants_are_404_and_unsellable_ones_422(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    draft = await catalog.product(status=ProductStatus.DRAFT)
    deleted_product = await catalog.product()
    live = await catalog.product()
    hidden = [
        await catalog.variant(draft, stock=(5, 0, 0)),
        await catalog.variant(deleted_product, stock=(5, 0, 0)),
        await catalog.variant(live, stock=(5, 0, 0), is_active=False),
        await catalog.variant(live, stock=(5, 0, 0), base_price=None, is_active=False),
        await catalog.variant(live, stock=(5, 0, 0)),
    ]
    await catalog.set(Product, deleted_product.id, deleted_at=utc_now())
    await catalog.set(ProductVariant, hidden[-1].id, deleted_at=utc_now())
    not_for_sale = await catalog.variant(live, stock=(5, 0, 0), is_purchasable=False)

    for variant_id in [*(variant.id for variant in hidden), uuid4()]:
        response = await auth_client.post(
            URL, json={"variant_id": str(variant_id), "quantity": 1}, headers=customer.headers
        )
        _error(response, 404, "NOT_FOUND")
    response = await auth_client.post(
        URL, json={"variant_id": str(not_for_sale.id), "quantity": 1}, headers=customer.headers
    )
    _error(response, 422, "BUSINESS_RULE_VIOLATION")


async def test_line_limit(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    customer = await make_account("customer")
    product = await catalog.product()
    variants = [await catalog.variant(product, stock=(1, 0, 0)) for _ in range(MAX_CART_LINES + 1)]
    for variant in variants[:MAX_CART_LINES]:
        response = await auth_client.post(
            URL, json={"variant_id": str(variant.id), "quantity": 1}, headers=customer.headers
        )
        assert response.status_code == 201, response.text

    response = await auth_client.post(
        URL, json={"variant_id": str(variants[-1].id), "quantity": 1}, headers=customer.headers
    )
    _error(response, 422, "BUSINESS_RULE_VIOLATION")

    # A variant already in the full cart still merges (no new line).
    stocked = variants[0]
    await catalog.set(InventoryItem, (await _item_row(db_engine, stocked.id)).id, total_quantity=2)
    merged = await auth_client.post(
        URL, json={"variant_id": str(stocked.id), "quantity": 1}, headers=customer.headers
    )
    assert merged.status_code == 201 and merged.json()["quantity"] == 2


# --- validation, ownership, concurrency ----------------------------------------------


async def test_invalid_bodies_are_400_and_amounts_are_ignored(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    variant = await _stocked(catalog, 5)
    vid = str(variant.id)
    for body in (
        {"variant_id": vid},
        {"quantity": 1},
        {"variant_id": "x", "quantity": 1},
        {"variant_id": vid, "quantity": 0},
        {"variant_id": vid, "quantity": 1.0},
        {"variant_id": vid, "quantity": "1"},
        {"variant_id": vid, "quantity": True},
        {"variant_id": vid, "quantity": 1_000_001},
        {"variant_id": vid, "quantity": 1, "colour": "red"},
    ):
        response = await auth_client.post(URL, json=body, headers=customer.headers)
        _error(response, 400, "VALIDATION_ERROR")

    response = await auth_client.post(
        URL,
        json={"variant_id": vid, "quantity": 1, "price": 1, "unit_price": 1, "total": 1},
        headers=customer.headers,
    )
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"id", "variant_id", "product_id", "quantity"}
    _error(
        await auth_client.patch(
            f"{URL}/{response.json()['id']}", json={"quantity": 0}, headers=customer.headers
        ),
        400,
        "VALIDATION_ERROR",
    )
    _error(
        await auth_client.patch(
            f"{URL}/not-a-uuid", json={"quantity": 1}, headers=customer.headers
        ),
        400,
        "VALIDATION_ERROR",
    )


async def test_lines_of_other_carts_are_404(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, guest_cleanup: None
) -> None:
    variant = await _stocked(catalog, 5)
    owner, other = await make_account("customer"), await make_account("customer")
    body = {"variant_id": str(variant.id), "quantity": 1}
    mine = (await auth_client.post(URL, json=body, headers=owner.headers)).json()["id"]
    await _guest_client(auth_client, None)
    guest_line = await auth_client.post(URL, json=body)
    guest_token = _token(guest_line)

    for headers in (other.headers, {}):
        await _guest_client(auth_client, None)
        _error(
            await auth_client.patch(f"{URL}/{mine}", json={"quantity": 2}, headers=headers),
            404,
            "NOT_FOUND",
        )
        _error(await auth_client.delete(f"{URL}/{mine}", headers=headers), 404, "NOT_FOUND")
    # Another guest, and the user, cannot touch the guest's line either.
    await _guest_client(auth_client, None)
    other_guest = _token(await auth_client.post(URL, json=body))
    await _guest_client(auth_client, other_guest)
    _error(await auth_client.delete(f"{URL}/{guest_line.json()['id']}"), 404, "NOT_FOUND")
    await _guest_client(auth_client, guest_token)
    _error(
        await auth_client.delete(f"{URL}/{guest_line.json()['id']}", headers=owner.headers),
        404,
        "NOT_FOUND",
    )

    removed = await auth_client.delete(f"{URL}/{guest_line.json()['id']}")
    assert removed.status_code == 204
    assert removed.headers["cache-control"] == "no-store"
    _error(await auth_client.delete(f"{URL}/{guest_line.json()['id']}"), 404, "NOT_FOUND")


async def test_concurrent_adds_never_exceed_free_stock(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    customer = await make_account("customer")
    variant = await _stocked(catalog, 3)

    responses = await asyncio.gather(
        *(
            auth_client.post(
                URL, json={"variant_id": str(variant.id), "quantity": 1}, headers=customer.headers
            )
            for _ in range(5)
        )
    )

    assert sorted(response.status_code for response in responses) == [201, 201, 201, 409, 409]
    async with AsyncSession(db_engine) as session:
        cart = (await session.scalars(select(Cart).where(Cart.user_id == customer.id))).one()
    assert await _lines(db_engine, cart.id) == {variant.id: 3}


async def test_lines_of_unavailable_variants_can_shrink_and_go_but_not_grow(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    variant = await _stocked(catalog, 5)
    line = await auth_client.post(
        URL, json={"variant_id": str(variant.id), "quantity": 3}, headers=customer.headers
    )
    await catalog.set(ProductVariant, variant.id, deleted_at=utc_now())
    url = f"{URL}/{line.json()['id']}"

    grow = await auth_client.patch(url, json={"quantity": 4}, headers=customer.headers)
    shrink = await auth_client.patch(url, json={"quantity": 1}, headers=customer.headers)
    removed = await auth_client.delete(url, headers=customer.headers)

    body = _error(grow, 422, "BUSINESS_RULE_VIOLATION")
    assert body["details"][0]["type"] == "variant_unavailable"
    assert shrink.status_code == 200 and shrink.json()["quantity"] == 1
    assert removed.status_code == 204


async def test_growing_a_line_of_a_variant_no_longer_for_sale_is_422(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    customer = await make_account("customer")
    variant = await _stocked(catalog, 5)
    line = await auth_client.post(
        URL, json={"variant_id": str(variant.id), "quantity": 1}, headers=customer.headers
    )
    await catalog.set(ProductVariant, variant.id, is_purchasable=False)

    response = await auth_client.patch(
        f"{URL}/{line.json()['id']}", json={"quantity": 2}, headers=customer.headers
    )

    body = _error(response, 422, "BUSINESS_RULE_VIOLATION")
    assert body["details"][0]["type"] == "not_purchasable"


async def test_failed_guest_add_sets_no_cookie_and_leaves_no_cart(
    auth_client: AsyncClient, catalog: Catalog, db_engine: AsyncEngine, guest_cleanup: None
) -> None:
    variant = await _stocked(catalog, 1)
    started = utc_now()
    for body, status, code in (
        ({"variant_id": str(uuid4()), "quantity": 1}, 404, "NOT_FOUND"),
        ({"variant_id": str(variant.id), "quantity": 2}, 409, "INSUFFICIENT_STOCK"),
    ):
        await _guest_client(auth_client, None)
        response = await auth_client.post(URL, json=body)
        _error(response, status, code)
        assert "set-cookie" not in response.headers
    async with AsyncSession(db_engine) as session:
        created = await session.scalar(
            select(func.count()).select_from(Cart).where(Cart.created_at >= started)
        )
    assert created == 0
