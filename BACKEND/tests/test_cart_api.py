"""Cart API error coverage and end-to-end flow (CART-05).

``COVERAGE`` maps every cart endpoint and every status in ``STATUSES`` to the test that
exercises it (``module::test``), or to ``n/a: <reason>``. Two guards keep it honest: the
map must match the real routes, and every named test must exist. Gaps found while building
the map are tested here.
"""

from __future__ import annotations

import ast
from collections.abc import Awaitable, Callable
from functools import cache
from pathlib import Path
from typing import Final
from uuid import uuid4

import pytest
from conftest import Catalog, MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OtpCode, ProductVariant, User, UserStatus
from app.modules.cart.tokens import CART_COOKIE_NAME

API = "/api/v1"
STATUSES: Final = (400, 401, 403, 404, 409, 422)
ITEMS = "test_cart_items"
VIEW = "test_cart_view"
DISCOUNT = "test_cart_discount"
SELF = "test_cart_api"
READ_ONLY = "n/a: read-only, no state to conflict with"
NO_RULE = "n/a: no business rule beyond the request"
NO_BODY = "n/a: no body, query or path input to validate"
EMPTY = "n/a: no cart is an empty cart (200), never 404"

COVERAGE: Final[dict[tuple[str, str], dict[int, str]]] = {
    ("GET", "/cart"): {
        400: f"{VIEW}::test_identity_and_ownership",
        401: f"{VIEW}::test_identity_and_ownership",
        403: f"{VIEW}::test_identity_and_ownership",
        404: EMPTY,
        409: READ_ONLY,
        422: READ_ONLY,
    },
    ("POST", "/cart/acknowledge-prices"): {
        400: NO_BODY,
        401: f"{VIEW}::test_identity_and_ownership",
        403: f"{VIEW}::test_identity_and_ownership",
        404: EMPTY,
        409: "n/a: moving baselines has no conflicting state",
        422: NO_RULE,
    },
    ("POST", "/cart/discount"): {
        400: f"{DISCOUNT}::test_request_errors",
        401: f"{DISCOUNT}::test_request_errors",
        403: f"{DISCOUNT}::test_request_errors",
        404: f"{DISCOUNT}::test_request_errors",
        409: "n/a: applying a code only writes the cart's own code",
        422: f"{DISCOUNT}::test_rejections_are_422_and_counted",
    },
    ("DELETE", "/cart/discount"): {
        400: NO_BODY,
        401: f"{DISCOUNT}::test_request_errors",
        403: f"{DISCOUNT}::test_request_errors",
        404: EMPTY,
        409: "n/a: removing the code never conflicts",
        422: "n/a: removing the code is always allowed",
    },
    ("POST", "/cart/items"): {
        400: f"{ITEMS}::test_invalid_bodies_are_400_and_amounts_are_ignored",
        401: f"{ITEMS}::test_bad_bearer_is_401_even_with_a_cart_cookie",
        403: f"{ITEMS}::test_blocked_user_is_403",
        404: f"{ITEMS}::test_hidden_variants_are_404_and_unsellable_ones_422",
        409: f"{ITEMS}::test_quantity_is_capped_by_effective_free_stock",
        422: f"{ITEMS}::test_line_limit",
    },
    ("PATCH", "/cart/items/{item_id}"): {
        400: f"{ITEMS}::test_invalid_bodies_are_400_and_amounts_are_ignored",
        401: f"{SELF}::test_line_writes_need_a_valid_identity",
        403: f"{SELF}::test_line_writes_need_a_valid_identity",
        404: f"{ITEMS}::test_lines_of_other_carts_are_404",
        409: f"{ITEMS}::test_quantity_is_capped_by_effective_free_stock",
        422: f"{ITEMS}::test_lines_of_unavailable_variants_can_shrink_and_go_but_not_grow",
    },
    ("DELETE", "/cart/items/{item_id}"): {
        400: f"{SELF}::test_malformed_line_id_is_400",
        401: f"{SELF}::test_line_writes_need_a_valid_identity",
        403: f"{SELF}::test_line_writes_need_a_valid_identity",
        404: f"{ITEMS}::test_lines_of_other_carts_are_404",
        409: "n/a: removing a line never conflicts",
        422: "n/a: removing a line is always allowed (ADR-040)",
    },
}


@cache
def _tests_of(module: str) -> frozenset[str]:
    tree = ast.parse((Path(__file__).parent / f"{module}.py").read_text(encoding="utf-8"))
    return frozenset(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    )


def test_coverage_map_matches_the_cart_routes(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    routes = {
        (method.upper(), path.removeprefix(API))
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(f"{API}/cart")
        for method in operations
    }
    assert routes == set(COVERAGE)


@pytest.mark.parametrize("endpoint", sorted(COVERAGE), ids=" ".join)
def test_every_status_is_tested_or_explained(endpoint: tuple[str, str]) -> None:
    cells = COVERAGE[endpoint]
    assert sorted(cells) == list(STATUSES)
    for status, cell in cells.items():
        if cell.startswith("n/a: "):
            continue
        module, _, test = cell.partition("::")
        assert test in _tests_of(module), f"{endpoint} {status}: {cell} does not exist"


# --- gaps ----------------------------------------------------------------------------


def _error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


@pytest.mark.integration
async def test_line_writes_need_a_valid_identity(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog
) -> None:
    blocked = await make_account("customer")
    await catalog.set(User, blocked.id, status=UserStatus.BLOCKED)
    url = f"{API}/cart/items/{uuid4()}"
    for headers, status, code in (
        ({"Authorization": "Bearer nope"}, 401, "UNAUTHORIZED"),
        (blocked.headers, 403, "FORBIDDEN"),
    ):
        _error(await auth_client.patch(url, json={"quantity": 1}, headers=headers), status, code)
        _error(await auth_client.delete(url, headers=headers), status, code)


@pytest.mark.integration
async def test_malformed_line_id_is_400(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    customer = await make_account("customer")
    response = await auth_client.delete(f"{API}/cart/items/not-a-uuid", headers=customer.headers)
    _error(response, 400, "VALIDATION_ERROR")


# --- end to end ----------------------------------------------------------------------


@pytest.mark.integration
async def test_guest_to_signed_in_cart_flow(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    catalog: Catalog,
) -> None:
    """Guest adds, sees prices, logs in (merge), sees a price change, accepts it."""
    product = await catalog.product()
    ring = await catalog.variant(product, stock=(5, 0, 0), base_price=12_000)
    chain = await catalog.variant(product, stock=(5, 0, 0), base_price=30_000)
    auth_client.cookies.clear()

    added = await auth_client.post(
        f"{API}/cart/items", json={"variant_id": str(ring.id), "quantity": 2}
    )
    assert added.status_code == 201, added.text
    auth_client.cookies.set(CART_COOKIE_NAME, added.cookies[CART_COOKIE_NAME])
    more = await auth_client.post(
        f"{API}/cart/items", json={"variant_id": str(chain.id), "quantity": 1}
    )
    assert more.status_code == 201
    guest_cart = (await auth_client.get(f"{API}/cart")).json()
    assert guest_cart["grand_total"] == 2 * 12_000 + 30_000

    await catalog.set(ProductVariant, ring.id, base_price=11_000, price_version=1)
    mobile = f"+989{uuid4().int % 1_000_000_000:09d}"
    await issue_otp(mobile)
    login = await auth_client.post(
        f"{API}/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    auth_client.cookies.clear()
    try:
        cart = (await auth_client.get(f"{API}/cart", headers=headers)).json()
        assert cart["grand_total"] == 2 * 11_000 + 30_000
        [changed] = [line for line in cart["items"] if line["price_changed"]]
        assert (changed["variant_id"], changed["previous_unit_price"]) == (str(ring.id), 12_000)

        accepted = (
            await auth_client.post(f"{API}/cart/acknowledge-prices", headers=headers)
        ).json()
        assert accepted["has_changes"] is False
        assert accepted["grand_total"] == cart["grand_total"]
    finally:
        async with AsyncSession(catalog.engine) as session, session.begin():
            await session.execute(delete(User).where(User.phone == mobile))
