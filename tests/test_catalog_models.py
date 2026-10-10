from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Category

pytestmark = pytest.mark.integration


def _slug(prefix: str = "cat") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _category(**overrides: object) -> Category:
    values: dict[str, object] = {"title": "Necklaces", "slug": _slug()}
    return Category(**{**values, **overrides})


async def _columns(db_engine: AsyncEngine, table: str) -> set[str]:
    async with db_engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: {
                column["name"] for column in inspect(sync_connection).get_columns(table)
            }
        )


async def test_category_defaults(db_session: AsyncSession) -> None:
    category = _category()
    db_session.add(category)
    await db_session.flush()
    await db_session.refresh(category)

    assert category.is_active is True
    assert category.display_order == 0
    assert category.parent_id is None
    assert category.deleted_at is None


async def test_category_tree_parent_and_children(db_session: AsyncSession) -> None:
    parent = _category(title="Jewelry")
    db_session.add(parent)
    await db_session.flush()
    children = [_category(parent_id=parent.id, display_order=order) for order in (2, 1)]
    db_session.add_all(children)
    await db_session.flush()

    ordered = (
        await db_session.scalars(
            select(Category.display_order)
            .where(Category.parent_id == parent.id)
            .order_by(Category.display_order)
        )
    ).all()
    assert ordered == [1, 2]


async def test_category_parent_must_exist(db_session: AsyncSession) -> None:
    db_session.add(_category(parent_id=uuid4()))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_category_cannot_be_its_own_parent(db_session: AsyncSession) -> None:
    category = _category()
    db_session.add(category)
    await db_session.flush()

    category.parent_id = category.id
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_category_with_children_cannot_be_hard_deleted(db_session: AsyncSession) -> None:
    parent = _category()
    db_session.add(parent)
    await db_session.flush()
    db_session.add(_category(parent_id=parent.id))
    await db_session.flush()

    await db_session.delete(parent)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_category_slug_unique_among_non_deleted(db_session: AsyncSession) -> None:
    slug = _slug()
    db_session.add(_category(slug=slug))
    await db_session.flush()

    db_session.add(_category(slug=slug))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_soft_deleted_category_frees_its_slug(db_session: AsyncSession) -> None:
    slug = _slug()
    old = _category(slug=slug)
    db_session.add(old)
    await db_session.flush()
    old.soft_delete()
    await db_session.flush()

    new = _category(slug=slug)
    db_session.add(new)
    await db_session.flush()

    assert new.id != old.id


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "   "},
        {"slug": "ab"},
        {"slug": "Necklaces"},
        {"slug": "gold necklace"},
        {"slug": "a" * 121},
        {"display_order": -1},
    ],
    ids=["blank-title", "short-slug", "uppercase-slug", "space-in-slug", "long-slug", "neg-order"],
)
async def test_category_constraints(db_session: AsyncSession, overrides: dict[str, object]) -> None:
    db_session.add(_category(**overrides))

    # CHECK violations raise IntegrityError; the String(120) overflow raises DataError.
    with pytest.raises(DBAPIError):
        await db_session.flush()


async def test_categories_table_columns(db_engine: AsyncEngine) -> None:
    assert await _columns(db_engine, "categories") == {
        "id",
        "parent_id",
        "title",
        "slug",
        "description",
        "icon_key",
        "image_url",
        "display_order",
        "is_active",
        "seo_title",
        "seo_description",
        "created_at",
        "updated_at",
        "deleted_at",
    }
