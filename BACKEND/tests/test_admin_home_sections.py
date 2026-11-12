"""Admin home sections: CRUD, shape rules, links, SD rule, order conflict, audit (CNT-02)."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from conftest import Catalog, MakeAccount, MakeMedia
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import AuditLog, HomeSection, Product, ProductStatus, StaticPage

pytestmark = pytest.mark.integration

URL = "/api/v1/admin/home/sections"
HOME = "/api/v1/home"
_ORDERS = itertools.count(uuid4().int % 100_000 * 10)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(db_engine: AsyncEngine, catalog: Catalog) -> AsyncIterator[None]:
    """Torn down before ``catalog``: items hold its products and categories (RESTRICT)."""
    started = utc_now()
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(HomeSection))
        await session.execute(delete(StaticPage).where(StaticPage.created_at >= started))


def _error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def _benefits(**fields: Any) -> dict[str, Any]:
    return {
        "type": "benefits",
        "title": "Why us",
        "display_order": next(_ORDERS),
        "items": [{"title_override": "Fast", "body": "**Two** days", "icon_key": "truck"}],
    } | fields


async def _create(client: AsyncClient, headers: dict[str, str], **fields: Any) -> dict[str, Any]:
    response = await client.post(URL, json=_benefits(**fields), headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _published(catalog: Catalog, **fields: Any) -> Product:
    product = await catalog.product(**fields)
    await catalog.variant(product, stock=(5, 0, 0))
    return product


async def _actions(engine: AsyncEngine, section_id: str) -> list[AuditLog]:
    async with AsyncSession(engine) as session:
        statement = (
            select(AuditLog)
            .where(AuditLog.entity_id == section_id)
            .order_by(AuditLog.created_at, AuditLog.id)
        )
        return list(await session.scalars(statement))


async def test_create_carousel_and_see_it_on_the_home_page(
    auth_client: AsyncClient, make_account: MakeAccount, catalog: Catalog, db_engine: AsyncEngine
) -> None:
    editor = await make_account("content_manager")
    first, second = await _published(catalog), await _published(catalog)
    forged = str(uuid4())

    created = await _create(
        auth_client,
        editor.headers,
        type="product_carousel",
        product_source="manual",
        items=[{"product_id": str(second.id)}, {"product_id": str(first.id)}],
        id=forged,
        created_by=forged,
    )

    assert created["id"] != forged
    assert [item["product_id"] for item in created["items"]] == [str(second.id), str(first.id)]
    home = (await auth_client.get(HOME)).json()
    [section] = home["sections"]
    assert [item["product"]["id"] for item in section["items"]] == [str(second.id), str(first.id)]
    [audit] = await _actions(db_engine, created["id"])
    assert audit.action == "home_section.created"
    assert audit.actor_user_id == editor.id


async def test_display_order_conflict_is_409_until_the_section_is_deleted(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    editor = await make_account("content_manager")
    section = await _create(auth_client, editor.headers)
    other = await _create(auth_client, editor.headers)
    taken = section["display_order"]

    _error(
        await auth_client.post(URL, json=_benefits(display_order=taken), headers=editor.headers),
        409,
        "CONFLICT",
    )
    _error(
        await auth_client.patch(
            f"{URL}/{other['id']}", json={"display_order": taken}, headers=editor.headers
        ),
        409,
        "CONFLICT",
    )
    deleted = await auth_client.delete(f"{URL}/{section['id']}", headers=editor.headers)
    assert deleted.status_code == 204
    await _create(auth_client, editor.headers, display_order=taken)


async def test_concurrent_creates_with_one_order_give_one_409(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    editor = await make_account("content_manager")
    order = next(_ORDERS)

    responses = await asyncio.gather(
        *(
            auth_client.post(URL, json=_benefits(display_order=order), headers=editor.headers)
            for _ in range(3)
        )
    )

    assert sorted(response.status_code for response in responses) == [201, 409, 409]


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "  "},
        {"type": "collection"},
        {"target_type": "url", "target_id": str(uuid4())},
        {"link": "https://evil.example.com"},
        {"target_url": "https://evil.example.com"},
        {"target_type": "product"},
        {"target_id": str(uuid4())},
        {"starts_at": "2030-01-02T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
        {"starts_at": "2030-01-01T00:00:00"},
        {"display_order": -1},
        {"items": [{"title_override": "x", "body": "<script>x</script>"}]},
        {"items": [{"icon_key": "only-an-icon"}]},
        {"items": [{"title_override": "x", "product_id": str(uuid4())}]},
        {"type": "hero"},
        {"type": "product_carousel"},
        {"product_source": "newest"},
        {"type": "category_grid", "items": [{"title_override": "x"}]},
        {
            "type": "product_carousel",
            "product_source": "category",
            "items": [],
        },
        {
            "type": "product_carousel",
            "product_source": "manual",
            "product_limit": 1,
            "items": [{"product_id": str(uuid4())}, {"product_id": str(uuid4())}],
        },
        {"product_limit": 21},
    ],
)
async def test_invalid_section_is_400(
    auth_client: AsyncClient, make_account: MakeAccount, fields: dict[str, Any]
) -> None:
    editor = await make_account("content_manager")

    response = await auth_client.post(URL, json=_benefits(**fields), headers=editor.headers)

    _error(response, 400, "VALIDATION_ERROR")


async def test_links_and_references_are_checked_when_saved(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    catalog: Catalog,
    db_engine: AsyncEngine,
    make_media: MakeMedia,
) -> None:
    editor = await make_account("content_manager")
    draft = await catalog.product(status=ProductStatus.DRAFT)
    deleted = await _published(catalog)
    await catalog.set(Product, deleted.id, deleted_at=utc_now())
    hidden = await catalog.category(active=False)
    page = StaticPage(slug=f"pg-{uuid4().hex[:8]}", title="About", body="Hi", status="draft")
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        session.add(page)
    product_image = await catalog.image(await _published(catalog))

    cases: list[tuple[dict[str, Any], int]] = [
        ({"target_type": "product", "target_id": str(uuid4())}, 404),
        ({"target_type": "product", "target_id": str(deleted.id)}, 404),
        ({"target_type": "product", "target_id": str(draft.id)}, 422),
        ({"target_type": "category", "target_id": str(hidden.id)}, 422),
        ({"target_type": "page", "target_id": str(page.id)}, 422),
        ({"target_type": "page", "target_id": str(uuid4())}, 404),
        (
            {
                "type": "product_carousel",
                "product_source": "manual",
                "items": [{"product_id": str(draft.id)}],
            },
            422,
        ),
        (
            {
                "type": "product_carousel",
                "product_source": "manual",
                "items": [{"product_id": str(deleted.id)}],
            },
            404,
        ),
        ({"type": "category_grid", "items": [{"category_id": str(hidden.id)}]}, 422),
        (
            {
                "type": "product_carousel",
                "product_source": "category",
                "source_category_id": str(uuid4()),
                "items": [],
            },
            404,
        ),
        ({"items": [{"title_override": "x", "image_media_id": str(uuid4())}]}, 404),
        (
            {"items": [{"title_override": "x", "image_media_id": str(product_image.media_id)}]},
            422,
        ),
    ]
    for fields, status in cases:
        response = await auth_client.post(URL, json=_benefits(**fields), headers=editor.headers)
        assert response.status_code == status, (fields, response.text)

    await catalog.set(StaticPage, page.id, status="published", published_at=utc_now())
    created = await _create(auth_client, editor.headers, target_type="page", target_id=str(page.id))
    assert created["target_type"] == "page"
    # Valid media and a category grid with a visible category are accepted.
    visible = await catalog.category()
    image = await make_media()
    await _create(
        auth_client,
        editor.headers,
        type="category_grid",
        items=[{"category_id": str(visible.id), "image_media_id": str(image.id)}],
    )


async def test_patch_replaces_items_and_audits_only_the_change(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    editor = await make_account("admin")
    section = await _create(auth_client, editor.headers)
    url = f"{URL}/{section['id']}"

    same = await auth_client.patch(url, json={"title": "Why us"}, headers=editor.headers)
    assert same.status_code == 200, same.text
    changed = await auth_client.patch(
        url,
        json={"items": [{"title_override": "Returns"}, {"body": "Secure *pay*"}]},
        headers=editor.headers,
    )

    assert changed.status_code == 200, changed.text
    assert [item["title_override"] for item in changed.json()["items"]] == ["Returns", None]
    audits = await _actions(db_engine, section["id"])
    assert [audit.action for audit in audits] == ["home_section.created", "home_section.updated"]
    assert set(audits[-1].metadata_["diff"]) == {"items"}


async def test_patch_checks_the_whole_section(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    editor = await make_account("content_manager")
    section = await _create(auth_client, editor.headers)
    url = f"{URL}/{section['id']}"

    # Benefit items cannot stay in a category grid.
    _error(
        await auth_client.patch(url, json={"type": "category_grid"}, headers=editor.headers),
        400,
        "VALIDATION_ERROR",
    )
    for body in ({}, {"title": None}, {"items": None}, {"slug": "x"}):
        _error(
            await auth_client.patch(url, json=body, headers=editor.headers), 400, "VALIDATION_ERROR"
        )
    window = {"starts_at": "2030-01-01T00:00:00Z"}
    assert (await auth_client.patch(url, json=window, headers=editor.headers)).status_code == 200
    _error(
        await auth_client.patch(
            url, json={"ends_at": "2029-01-01T00:00:00Z"}, headers=editor.headers
        ),
        400,
        "VALIDATION_ERROR",
    )


async def test_admin_changes_reach_the_home_page(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    editor = await make_account("content_manager")
    late = await _create(auth_client, editor.headers, title="Late")
    early = await _create(auth_client, editor.headers, title="Early")
    await auth_client.patch(
        f"{URL}/{early['id']}",
        json={"display_order": late["display_order"] + 1},
        headers=editor.headers,
    )

    titles = [section["title"] for section in (await auth_client.get(HOME)).json()["sections"]]
    assert titles == ["Late", "Early"]

    await auth_client.patch(
        f"{URL}/{late['id']}", json={"is_active": False}, headers=editor.headers
    )
    await auth_client.delete(f"{URL}/{early['id']}", headers=editor.headers)
    sections = (await auth_client.get(HOME)).json()["sections"]
    assert all(section["id"] is None for section in sections)


async def test_deleted_section_is_gone_for_the_admin(
    auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
) -> None:
    editor = await make_account("content_manager")
    section = await _create(auth_client, editor.headers)
    url = f"{URL}/{section['id']}"

    assert (await auth_client.delete(url, headers=editor.headers)).status_code == 204

    _error(await auth_client.delete(url, headers=editor.headers), 404, "NOT_FOUND")
    _error(
        await auth_client.patch(url, json={"title": "x"}, headers=editor.headers), 404, "NOT_FOUND"
    )
    listed = await auth_client.get(URL, params={"limit": 100}, headers=editor.headers)
    assert section["id"] not in {item["id"] for item in listed.json()["items"]}
    assert (await _actions(db_engine, section["id"]))[-1].action == "home_section.deleted"


async def test_list_is_in_display_order_with_items(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    editor = await make_account("content_manager")
    second = await _create(auth_client, editor.headers, display_order=next(_ORDERS) + 5)
    first = await _create(auth_client, editor.headers, display_order=second["display_order"] - 1)

    response = await auth_client.get(URL, headers=editor.headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    items = response.json()["items"]
    assert [item["id"] for item in items] == [first["id"], second["id"]]
    assert items[0]["items"][0]["icon_key"] == "truck"


@pytest.mark.parametrize("role", ["customer", "support"])
async def test_other_roles_are_403(
    auth_client: AsyncClient, make_account: MakeAccount, role: str
) -> None:
    account = await make_account(role)

    _error(await auth_client.post(URL, json=_benefits(), headers=account.headers), 403, "FORBIDDEN")


async def test_anonymous_is_401(auth_client: AsyncClient) -> None:
    _error(await auth_client.get(URL), 401, "UNAUTHORIZED")
