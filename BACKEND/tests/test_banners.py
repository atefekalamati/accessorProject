"""Banners: admin CRUD, links and media checks, schedule, home output, audit (CNT-03)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from conftest import MEDIA_BASE_URL, Catalog, MakeAccount, MakeMedia
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import AuditLog, Banner, HomeSection, Media, Product, StaticPage

pytestmark = pytest.mark.integration

URL = "/api/v1/admin/banners"
HOME = "/api/v1/home"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(
    db_engine: AsyncEngine, catalog: Catalog, make_media: MakeMedia
) -> AsyncIterator[None]:
    """Torn down before ``make_media`` and ``catalog``: banners hold their media (RESTRICT)."""
    started = utc_now()
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(Banner))
        await session.execute(delete(HomeSection))
        await session.execute(delete(StaticPage).where(StaticPage.created_at >= started))


def _error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


async def _create(
    client: AsyncClient, headers: dict[str, str], image: Media, **fields: Any
) -> dict[str, Any]:
    body = {"title": "Summer sale", "image_media_id": str(image.id)} | fields
    response = await client.post(URL, json=body, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _hero(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session, session.begin():
        session.add(HomeSection(type="hero", title="Hero", display_order=0))


async def _hero_items(client: AsyncClient) -> list[dict[str, Any]]:
    sections = (await client.get(HOME)).json()["sections"]
    heroes = [section for section in sections if section["type"] == "hero"]
    return [] if not heroes else heroes[0]["items"]


async def test_create_shows_server_built_urls_and_audits(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_media: MakeMedia,
    db_engine: AsyncEngine,
) -> None:
    editor = await make_account("content_manager")
    desktop, mobile = await make_media(), await make_media()
    forged = str(uuid4())

    banner = await _create(
        auth_client,
        editor.headers,
        desktop,
        mobile_image_media_id=str(mobile.id),
        subtitle="Up to 30%",
        id=forged,
        image_url="https://evil.example.com/x.png",
    )

    assert banner["id"] != forged
    assert banner["image_url"] == f"{MEDIA_BASE_URL}/{desktop.storage_key}"
    assert banner["mobile_image_url"] == f"{MEDIA_BASE_URL}/{mobile.storage_key}"
    async with AsyncSession(db_engine) as session:
        [audit] = await session.scalars(select(AuditLog).where(AuditLog.entity_id == banner["id"]))
    assert audit.action == "banner.created"


async def test_hero_section_shows_banners_in_their_window_and_order(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_media: MakeMedia,
    db_engine: AsyncEngine,
) -> None:
    editor = await make_account("content_manager")
    image = await make_media()
    now = utc_now()
    second = await _create(auth_client, editor.headers, image, title="Second", display_order=2)
    first = await _create(auth_client, editor.headers, image, title="First", display_order=1)
    await _create(
        auth_client,
        editor.headers,
        image,
        title="Before",
        starts_at=(now + timedelta(hours=1)).isoformat(),
    )
    await _create(
        auth_client,
        editor.headers,
        image,
        title="After",
        ends_at=(now - timedelta(seconds=1)).isoformat(),
    )
    await _create(auth_client, editor.headers, image, title="Off", is_active=False)
    await _hero(db_engine)

    items = await _hero_items(auth_client)

    assert [item["title"] for item in items] == [first["title"], second["title"]]
    assert items[0]["image_url"] == f"{MEDIA_BASE_URL}/{image.storage_key}"
    assert items[0]["target"] is None


async def test_banners_show_by_default_when_no_section_is_active(
    auth_client: AsyncClient, make_account: MakeAccount, make_media: MakeMedia
) -> None:
    editor = await make_account("content_manager")
    await _create(auth_client, editor.headers, await make_media())

    sections = (await auth_client.get(HOME)).json()["sections"]

    assert sections[0]["type"] == "hero"
    assert sections[0]["id"] is None


async def test_a_banner_whose_target_stopped_being_public_is_hidden(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_media: MakeMedia,
    catalog: Catalog,
    db_engine: AsyncEngine,
) -> None:
    editor = await make_account("content_manager")
    image = await make_media()
    product = await catalog.product()
    await catalog.variant(product, stock=(5, 0, 0))
    linked = await _create(
        auth_client, editor.headers, image, target_type="product", target_id=str(product.id)
    )
    await _hero(db_engine)
    assert (await _hero_items(auth_client))[0]["target"] == {
        "type": "product",
        "slug": product.slug,
    }

    await catalog.set(Product, product.id, deleted_at=utc_now())

    assert await _hero_items(auth_client) == []
    assert linked["target_type"] == "product"


@pytest.mark.parametrize(
    "fields",
    [
        {"title": " "},
        {"link": "https://evil.example.com"},
        {"target_type": "url", "target_id": str(uuid4())},
        {"target_type": "page"},
        {"target_id": str(uuid4())},
        {"starts_at": "2030-01-02T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
        {"starts_at": "2030-01-01T00:00:00"},
        {"display_order": -1},
        {"image_media_id": None},
    ],
)
async def test_invalid_banner_is_400(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_media: MakeMedia,
    fields: dict[str, Any],
) -> None:
    editor = await make_account("content_manager")
    body = {"title": "Sale", "image_media_id": str((await make_media()).id)} | fields

    _error(await auth_client.post(URL, json=body, headers=editor.headers), 400, "VALIDATION_ERROR")


async def test_links_and_media_are_checked_when_saved(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_media: MakeMedia,
    catalog: Catalog,
    db_engine: AsyncEngine,
) -> None:
    editor = await make_account("content_manager")
    image = await make_media()
    hidden = await catalog.category(active=False)
    product_image = await catalog.image(await catalog.product())
    page = StaticPage(slug=f"pg-{uuid4().hex[:8]}", title="About", body="Hi", status="draft")
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        session.add(page)

    cases: list[tuple[dict[str, Any], int]] = [
        ({"image_media_id": str(uuid4())}, 404),
        ({"mobile_image_media_id": str(uuid4())}, 404),
        ({"image_media_id": str(product_image.media_id)}, 422),
        ({"target_type": "category", "target_id": str(hidden.id)}, 422),
        ({"target_type": "page", "target_id": str(page.id)}, 422),
        ({"target_type": "product", "target_id": str(uuid4())}, 404),
    ]
    for fields, status in cases:
        body = {"title": "Sale", "image_media_id": str(image.id)} | fields
        response = await auth_client.post(URL, json=body, headers=editor.headers)
        assert response.status_code == status, (fields, response.text)

    banner = await _create(auth_client, editor.headers, image)
    _error(
        await auth_client.patch(
            f"{URL}/{banner['id']}",
            json={"target_type": "page", "target_id": str(page.id)},
            headers=editor.headers,
        ),
        422,
        "BUSINESS_RULE_VIOLATION",
    )


async def test_update_and_delete_are_audited(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_media: MakeMedia,
    db_engine: AsyncEngine,
) -> None:
    editor = await make_account("admin")
    banner = await _create(auth_client, editor.headers, await make_media())
    url = f"{URL}/{banner['id']}"

    same = await auth_client.patch(url, json={"title": "Summer sale"}, headers=editor.headers)
    assert same.status_code == 200, same.text
    changed = await auth_client.patch(url, json={"subtitle": "Now"}, headers=editor.headers)
    assert changed.json()["subtitle"] == "Now"
    cleared = await auth_client.patch(url, json={"subtitle": None}, headers=editor.headers)
    assert cleared.json()["subtitle"] is None
    _error(
        await auth_client.patch(url, json={"title": None}, headers=editor.headers),
        400,
        "VALIDATION_ERROR",
    )
    assert (await auth_client.delete(url, headers=editor.headers)).status_code == 204
    _error(await auth_client.delete(url, headers=editor.headers), 404, "NOT_FOUND")

    async with AsyncSession(db_engine) as session:
        actions = list(
            await session.scalars(
                select(AuditLog.action)
                .where(AuditLog.entity_id == banner["id"])
                .order_by(AuditLog.created_at, AuditLog.id)
            )
        )
    assert actions == ["banner.created", "banner.updated", "banner.updated", "banner.deleted"]
    listed = await auth_client.get(URL, params={"limit": 100}, headers=editor.headers)
    assert banner["id"] not in {item["id"] for item in listed.json()["items"]}


@pytest.mark.parametrize("role", ["customer", "support"])
async def test_other_roles_are_403(
    auth_client: AsyncClient, make_account: MakeAccount, role: str
) -> None:
    account = await make_account(role)

    _error(await auth_client.get(URL, headers=account.headers), 403, "FORBIDDEN")


async def test_anonymous_is_401(auth_client: AsyncClient) -> None:
    _error(await auth_client.get(URL), 401, "UNAUTHORIZED")
