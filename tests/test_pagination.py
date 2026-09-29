from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.errors import BadRequestError, ErrorCode
from app.main import create_app
from app.shared.pagination import (
    ADMIN_MAX_LIMIT,
    MAX_PAGE,
    PUBLIC_DEFAULT_LIMIT,
    PUBLIC_MAX_LIMIT,
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    page_params,
    public_page_params,
    resolve_sort,
)

SORTS: dict[str, tuple[str, bool]] = {
    "newest": ("created_at", True),
    "price_asc": ("price", False),
    "price_desc": ("price", True),
}
ITEMS = list(range(1, 101))


def _build_app(settings: Settings) -> FastAPI:
    application = create_app(settings)

    @application.get(
        "/_test/public",
        dependencies=[Depends(allowed_query_params("page", "limit", "sort", "in_stock"))],
    )
    async def public_list(
        paging: Annotated[PageParams, Depends(public_page_params)],
        sort: str | None = None,
        in_stock: bool | None = None,
    ) -> Page[int]:
        column, desc = resolve_sort(sort, SORTS, default="newest")
        ordered = sorted(ITEMS, reverse=desc)
        window = ordered[paging.offset : paging.offset + paging.limit]
        return Page.build(window, total=len(ITEMS), params=paging)

    @application.get("/_test/admin")
    async def admin_list(
        paging: Annotated[PageParams, Depends(admin_page_params)],
    ) -> Page[int]:
        window = ITEMS[paging.offset : paging.offset + paging.limit]
        return Page.build(window, total=len(ITEMS), params=paging)

    return application


@pytest_asyncio.fixture
async def page_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=_build_app(settings))
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


def _assert_400(body: dict[str, Any], field: str) -> None:
    assert set(body) == {"error", "request_id"}
    assert body["error"]["code"] == ErrorCode.VALIDATION_ERROR
    assert field in [detail["field"] for detail in body["error"]["details"]]


# --- unit ------------------------------------------------------------------------------


def test_offset_is_derived_from_page_and_limit() -> None:
    assert PageParams(page=1, limit=24).offset == 0
    assert PageParams(page=3, limit=24).offset == 48


@pytest.mark.parametrize(("total", "pages"), [(0, 0), (1, 1), (24, 1), (25, 2), (100, 5)])
def test_page_build_computes_pages(total: int, pages: int) -> None:
    result = Page.build([1, 2], total=total, params=PageParams(page=1, limit=24))
    assert result.pages == pages
    assert result.items == [1, 2]
    assert (result.total, result.page, result.limit) == (total, 1, 24)


def test_page_params_rejects_default_above_cap() -> None:
    with pytest.raises(ValueError):
        page_params(default_limit=50, max_limit=48)


def test_resolve_sort_maps_key_and_falls_back_to_default() -> None:
    assert resolve_sort("price_asc", SORTS, default="newest") == ("price", False)
    assert resolve_sort(None, SORTS, default="newest") == ("created_at", True)
    assert resolve_sort("", SORTS, default="newest") == ("created_at", True)


@pytest.mark.parametrize("raw", ["created_at", "price", "-price", "PRICE_ASC", "newest;drop"])
def test_resolve_sort_rejects_keys_outside_allowlist(raw: str) -> None:
    with pytest.raises(BadRequestError) as info:
        resolve_sort(raw, SORTS, default="newest")
    assert info.value.status_code == 400
    assert info.value.details[0]["field"] == "query.sort"


def test_resolve_sort_rejects_default_outside_allowlist() -> None:
    with pytest.raises(ValueError):
        resolve_sort(None, SORTS, default="oldest")


# --- API -------------------------------------------------------------------------------


async def test_public_defaults(page_client: AsyncClient) -> None:
    response = await page_client.get("/_test/public")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "page", "limit", "pages"}
    assert body["limit"] == PUBLIC_DEFAULT_LIMIT
    assert body["page"] == 1
    assert body["total"] == 100
    assert body["items"][0] == 100  # default sort "newest" is descending


async def test_public_page_window_and_sort(page_client: AsyncClient) -> None:
    response = await page_client.get(
        "/_test/public", params={"page": 2, "limit": 10, "sort": "price_asc", "in_stock": "true"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == list(range(11, 21))
    assert body["pages"] == 10


async def test_public_limit_at_cap_is_allowed(page_client: AsyncClient) -> None:
    response = await page_client.get("/_test/public", params={"limit": PUBLIC_MAX_LIMIT})
    assert response.status_code == 200
    assert len(response.json()["items"]) == PUBLIC_MAX_LIMIT


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"limit": PUBLIC_MAX_LIMIT + 1}, "query.limit"),
        ({"limit": 0}, "query.limit"),
        ({"limit": "ten"}, "query.limit"),
        ({"page": 0}, "query.page"),
        ({"page": -1}, "query.page"),
        ({"page": MAX_PAGE + 1}, "query.page"),
        ({"sort": "price"}, "query.sort"),
        ({"sort": "-created_at"}, "query.sort"),
        ({"color": "red"}, "query.color"),
        ({"order_by": "price"}, "query.order_by"),
    ],
)
async def test_public_invalid_input_is_400(
    page_client: AsyncClient, params: dict[str, Any], field: str
) -> None:
    response = await page_client.get("/_test/public", params=params)
    assert response.status_code == 400
    _assert_400(response.json(), field)


async def test_unknown_params_are_all_reported(page_client: AsyncClient) -> None:
    response = await page_client.get("/_test/public", params={"b": "1", "a": "2"})
    assert response.status_code == 400
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert fields == ["query.a", "query.b"]


async def test_admin_cap_is_higher_than_public(page_client: AsyncClient) -> None:
    ok = await page_client.get("/_test/admin", params={"limit": ADMIN_MAX_LIMIT})
    assert ok.status_code == 200
    assert len(ok.json()["items"]) == ADMIN_MAX_LIMIT

    too_big = await page_client.get("/_test/admin", params={"limit": ADMIN_MAX_LIMIT + 1})
    assert too_big.status_code == 400
    _assert_400(too_big.json(), "query.limit")
