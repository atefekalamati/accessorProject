"""Content: the public/admin split end to end (CNT-07).

A content manager builds the store front through the admin API; a guest then reads it
without logging in and sees only published, public data, never an internal field.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from conftest import INTERNAL_FIELDS, Catalog, MakeAccount, MakeMedia, nested_keys
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import Banner, ContactMessage, FaqItem, HomeSection, StaticPage

pytestmark = pytest.mark.integration

API = "/api/v1"
# Admin-only fields of content rows: none may reach a public response. (``published_at``
# stays: it is part of the public product card since CAT-07.)
ADMIN_FIELDS = INTERNAL_FIELDS | {
    "display_order",
    "target_id",
    "target_type",
    "image_media_id",
    "mobile_image_media_id",
    "source_category_id",
    "product_source",
    "product_limit",
    "is_published",
    "starts_at",
    "ends_at",
    "internal_note",
    "handled_by",
    "ip",
    "created_at",
}


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(
    db_engine: AsyncEngine, catalog: Catalog, make_media: MakeMedia
) -> AsyncIterator[None]:
    """Torn down before ``make_media`` and ``catalog`` (their rows are referenced)."""
    started = utc_now()
    yield
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(Banner))
        await session.execute(delete(HomeSection))
        await session.execute(delete(ContactMessage))
        for model in (StaticPage, FaqItem):
            await session.execute(delete(model).where(model.created_at >= started))


async def _post(client: AsyncClient, path: str, headers: dict[str, str], body: Any) -> Any:
    response = await client.post(f"{API}{path}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_guest_sees_the_store_front_built_by_the_content_manager(
    auth_client: AsyncClient,
    make_account: MakeAccount,
    make_media: MakeMedia,
    catalog: Catalog,
) -> None:
    editor = await make_account("content_manager")
    headers = editor.headers
    category = await catalog.category()
    in_stock = await catalog.product(category=category.id)
    await catalog.variant(in_stock, stock=(5, 0, 0))
    sold_out = await catalog.product(category=category.id)
    await catalog.variant(sold_out, stock=(0, 0, 0))
    image = await make_media()
    tag = uuid4().hex[:8]

    page = await _post(
        auth_client,
        "/admin/pages",
        headers,
        {"slug": f"about-{tag}", "title": "About", "body": "# Us", "status": "published"},
    )
    draft = await _post(
        auth_client, "/admin/pages", headers, {"slug": f"draft-{tag}", "title": "D", "body": "x"}
    )
    await _post(
        auth_client,
        "/admin/faq",
        headers,
        {"group_title": f"Ship {tag}", "question": "When?", "answer": "Soon", "is_published": True},
    )
    await _post(
        auth_client,
        "/admin/faq",
        headers,
        {"group_title": f"Hidden {tag}", "question": "Q", "answer": "A"},
    )
    await _post(
        auth_client,
        "/admin/banners",
        headers,
        {
            "title": "Sale",
            "image_media_id": str(image.id),
            "target_type": "page",
            "target_id": page["id"],
        },
    )
    base = uuid4().int % 100_000 * 10
    sections: list[dict[str, Any]] = [
        {"type": "hero", "title": "Hero"},
        {
            "type": "category_grid",
            "title": "Shop by category",
            "items": [{"category_id": str(category.id)}],
        },
        {
            "type": "product_carousel",
            "title": "Picked",
            "product_source": "manual",
            "target_type": "category",
            "target_id": str(category.id),
            "items": [{"product_id": str(sold_out.id)}, {"product_id": str(in_stock.id)}],
        },
        {"type": "benefits", "title": "Why us", "items": [{"title_override": "Free returns"}]},
        {"type": "editorial", "title": "Style", "items": [{"body": "*Layer* your rings"}]},
    ]
    for index, section in enumerate(sections):
        await _post(
            auth_client, "/admin/home/sections", headers, section | {"display_order": base + index}
        )

    home = await auth_client.get(f"{API}/home")
    shown_page = await auth_client.get(f"{API}/pages/{page['slug']}")
    hidden_page = await auth_client.get(f"{API}/pages/{draft['slug']}")
    faq = await auth_client.get(f"{API}/faq")

    assert home.status_code == shown_page.status_code == faq.status_code == 200
    assert hidden_page.status_code == 404
    body = home.json()
    assert [section["type"] for section in body["sections"]] == [
        "hero",
        "category_grid",
        "product_carousel",
        "benefits",
        "editorial",
    ]
    [banner] = body["sections"][0]["items"]
    assert banner["target"] == {"type": "page", "slug": page["slug"]}
    carousel = body["sections"][2]
    assert carousel["target"] == {"type": "category", "slug": category.slug}
    sold, available = (item["product"] for item in carousel["items"])
    assert (sold["id"], sold["availability"], sold["quick_add_variant_id"]) == (
        str(sold_out.id),
        "out_of_stock",
        None,
    )
    assert available["quick_add_variant_id"] is not None
    groups = {group["title"] for group in faq.json()["groups"]}
    assert f"Ship {tag}" in groups and f"Hidden {tag}" not in groups
    for public in (body, shown_page.json(), faq.json()):
        assert not nested_keys(public) & ADMIN_FIELDS


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/home", None),
        ("GET", "/faq", None),
        ("GET", "/pages/no-such-page", None),
        (
            "POST",
            "/contact",
            {"name": "A", "mobile": "09120000000", "subject": "S", "message": "M"},
        ),
    ],
)
async def test_public_content_needs_no_login(
    auth_client: AsyncClient, method: str, path: str, body: Any
) -> None:
    response = await auth_client.request(method, f"{API}{path}", json=body)

    assert response.status_code in (200, 201, 404), response.text


async def test_the_contact_form_returns_no_data_and_the_admin_list_needs_a_permission(
    auth_client: AsyncClient, make_account: MakeAccount
) -> None:
    body = {"name": "A", "mobile": "09120000001", "subject": "S", "message": "M"}
    editor = await make_account("content_manager")

    sent = await auth_client.post(f"{API}/contact", json=body)

    assert sent.status_code == 201 and sent.content == b""
    listed = await auth_client.get(f"{API}/admin/contact-messages", headers=editor.headers)
    assert listed.status_code == 403
