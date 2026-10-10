from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import Category

pytestmark = pytest.mark.integration

CATEGORIES_URL = "/api/v1/categories"
MakeCategory = Callable[..., Awaitable[Category]]


def _slug(prefix: str = "cat") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@pytest_asyncio.fixture
async def make_category(db_engine: AsyncEngine) -> AsyncIterator[MakeCategory]:
    """Commit categories for the API under test; delete them (children first) afterwards."""
    created: list[UUID] = []

    async def _make(**overrides: Any) -> Category:
        values: dict[str, Any] = {"title": "Category", "slug": _slug(), **overrides}
        async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
            category = Category(**values)
            session.add(category)
        created.append(category.id)
        return category

    yield _make
    async with AsyncSession(db_engine) as session, session.begin():
        for category_id in reversed(created):
            await session.execute(delete(Category).where(Category.id == category_id))


def _find(nodes: list[dict[str, Any]], slug: str) -> dict[str, Any] | None:
    for node in nodes:
        if node["slug"] == slug:
            return node
        found = _find(node["children"], slug)
        if found is not None:
            return found
    return None


async def _tree(client: AsyncClient) -> list[dict[str, Any]]:
    response = await client.get(CATEGORIES_URL)
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_guest_gets_tree_ordered_by_display_order(
    auth_client: AsyncClient, make_category: MakeCategory
) -> None:
    root = await make_category(title="Jewelry")
    second = await make_category(parent_id=root.id, display_order=2)
    first = await make_category(parent_id=root.id, display_order=1)
    grandchild = await make_category(parent_id=first.id)

    node = _find(await _tree(auth_client), root.slug)

    assert node is not None
    assert [child["slug"] for child in node["children"]] == [first.slug, second.slug]
    assert node["children"][0]["children"][0]["slug"] == grandchild.slug
    assert set(node) == {"id", "title", "slug", "icon_key", "image_url", "children"}


async def test_tree_hides_inactive_deleted_and_their_descendants(
    auth_client: AsyncClient, make_category: MakeCategory
) -> None:
    root = await make_category()
    inactive = await make_category(parent_id=root.id, is_active=False)
    under_inactive = await make_category(parent_id=inactive.id)
    deleted = await make_category(parent_id=root.id, deleted_at=utc_now())
    under_deleted = await make_category(parent_id=deleted.id)
    inactive_root = await make_category(is_active=False)
    under_inactive_root = await make_category(parent_id=inactive_root.id)
    visible = await make_category(parent_id=root.id)

    tree = await _tree(auth_client)

    root_node = _find(tree, root.slug)
    assert root_node is not None
    assert [child["slug"] for child in root_node["children"]] == [visible.slug]
    for hidden in (inactive, under_inactive, deleted, under_deleted, inactive_root):
        assert _find(tree, hidden.slug) is None
    assert _find(tree, under_inactive_root.slug) is None


async def test_detail_returns_breadcrumb_and_visible_children(
    auth_client: AsyncClient, make_category: MakeCategory
) -> None:
    root = await make_category(title="Accessories")
    category = await make_category(
        parent_id=root.id,
        title="Hair",
        description="Hair accessories",
        icon_key="hair",
        image_url="https://cdn.example.com/hair.webp",
        seo_title="Hair accessories",
        seo_description="All hair accessories",
    )
    child_b = await make_category(parent_id=category.id, display_order=5)
    child_a = await make_category(parent_id=category.id, display_order=1)
    await make_category(parent_id=category.id, is_active=False)

    response = await auth_client.get(f"{CATEGORIES_URL}/{category.slug}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(category.id)
    assert body["description"] == "Hair accessories"
    assert body["image_url"] == "https://cdn.example.com/hair.webp"
    assert body["seo_title"] == "Hair accessories"
    assert [item["slug"] for item in body["breadcrumb"]] == [root.slug, category.slug]
    assert [child["slug"] for child in body["children"]] == [child_a.slug, child_b.slug]
    assert "is_active" not in body and "deleted_at" not in body


@pytest.mark.parametrize("hidden", ["inactive", "deleted", "inactive_parent", "deleted_parent"])
async def test_detail_of_hidden_category_is_404(
    auth_client: AsyncClient, make_category: MakeCategory, hidden: str
) -> None:
    """SD rule: a soft-deleted category (or one under a hidden ancestor) is 404 NOT_FOUND."""
    overrides: dict[str, dict[str, Any]] = {
        "inactive": {"is_active": False},
        "deleted": {"deleted_at": utc_now()},
    }
    parent_overrides = overrides.get(hidden.removesuffix("_parent"), {}) if "_" in hidden else {}
    own_overrides = {} if "_" in hidden else overrides[hidden]
    parent = await make_category(**parent_overrides)
    category = await make_category(parent_id=parent.id, **own_overrides)

    response = await auth_client.get(f"{CATEGORIES_URL}/{category.slug}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("slug", ["missing-category-slug", "UPPER", "ab", "bad_slug!"])
async def test_detail_of_unknown_or_malformed_slug_is_404(
    auth_client: AsyncClient, slug: str
) -> None:
    response = await auth_client.get(f"{CATEGORIES_URL}/{slug}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_unknown_query_parameter_is_400(auth_client: AsyncClient) -> None:
    response = await auth_client.get(CATEGORIES_URL, params={"parent": "x"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
