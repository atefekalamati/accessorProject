from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import (
    AuditLog,
    Category,
    CategoryFilter,
    OtpCode,
    Product,
    ProductAttribute,
    ProductStatus,
    ProductVariant,
    User,
    UserRole,
    VariantOption,
)
from app.db.seed import role_id

pytestmark = pytest.mark.integration

PUBLIC_URL = "/api/v1/categories"
ADMIN_URL = "/api/v1/admin/categories"
Headers = dict[str, str]


def _slug(prefix: str = "cat") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@pytest_asyncio.fixture
async def login(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    db_engine: AsyncEngine,
) -> AsyncIterator[Callable[..., Awaitable[Headers]]]:
    mobiles: list[str] = []

    async def _login(*roles: str) -> Headers:
        mobile = f"+989{uuid4().int % 1_000_000_000:09d}"
        mobiles.append(mobile)
        await issue_otp(mobile)
        response = await auth_client.post(
            "/api/v1/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
        )
        async with AsyncSession(db_engine) as session, session.begin():
            user_id = (await session.scalars(select(User.id).where(User.phone == mobile))).one()
            await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
            session.add_all(UserRole(user_id=user_id, role_id=role_id(name)) for name in roles)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    yield _login
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone.in_(mobiles)))


class Catalog:
    """Commits catalog rows for one test and removes them afterwards."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.categories: list[UUID] = []
        self.products: list[UUID] = []

    async def category(self, **overrides: Any) -> Category:
        values: dict[str, Any] = {"title": "Category", "slug": _slug(), **overrides}
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            category = Category(**values)
            session.add(category)
        self.categories.append(category.id)
        return category

    async def product(
        self,
        category: Category,
        *,
        options: list[dict[str, str]] | None = None,
        attributes: dict[str, str] | None = None,
        variant_active: bool = True,
        **overrides: Any,
    ) -> Product:
        values: dict[str, Any] = {
            "category_id": category.id,
            "title": "Product",
            "slug": _slug("prd"),
            "status": ProductStatus.PUBLISHED,
            "published_at": utc_now(),
            **overrides,
        }
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            product = Product(**values)
            session.add(product)
            await session.flush()
            for option_set in options or [{}]:
                variant = ProductVariant(
                    product_id=product.id,
                    sku=f"SKU-{uuid4().hex[:10].upper()}",
                    is_active=variant_active,
                    # An active variant needs a price (ADR-027).
                    base_price=100_000,
                )
                session.add(variant)
                await session.flush()
                session.add_all(
                    VariantOption(variant_id=variant.id, option_key=key, value=value)
                    for key, value in option_set.items()
                )
            session.add_all(
                ProductAttribute(product_id=product.id, attribute_key=key, attribute_value=value)
                for key, value in (attributes or {}).items()
            )
        self.products.append(product.id)
        return product

    async def filters(self, category: Category, *items: tuple[str, str]) -> None:
        async with AsyncSession(self.engine) as session, session.begin():
            session.add_all(
                CategoryFilter(
                    category_id=category.id,
                    attribute_key=key,
                    label=key.title(),
                    filter_type=filter_type,
                    display_order=order,
                )
                for order, (key, filter_type) in enumerate(items)
            )

    async def cleanup(self) -> None:
        async with AsyncSession(self.engine) as session, session.begin():
            variants = select(ProductVariant.id).where(ProductVariant.product_id.in_(self.products))
            await session.execute(
                delete(VariantOption).where(VariantOption.variant_id.in_(variants))
            )
            await session.execute(
                delete(ProductVariant).where(ProductVariant.product_id.in_(self.products))
            )
            await session.execute(
                delete(ProductAttribute).where(ProductAttribute.product_id.in_(self.products))
            )
            await session.execute(delete(Product).where(Product.id.in_(self.products)))
            await session.execute(
                delete(CategoryFilter).where(CategoryFilter.category_id.in_(self.categories))
            )
            for category_id in reversed(self.categories):
                await session.execute(delete(Category).where(Category.id == category_id))


@pytest_asyncio.fixture
async def catalog(db_engine: AsyncEngine) -> AsyncIterator[Catalog]:
    data = Catalog(db_engine)
    yield data
    await data.cleanup()


async def _filters(client: AsyncClient, category: Category) -> Response:
    return await client.get(f"{PUBLIC_URL}/{category.slug}/filters")


# --- model ---------------------------------------------------------------------------


async def test_filter_key_is_unique_per_category(catalog: Catalog) -> None:
    category = await catalog.category()
    await catalog.filters(category, ("color", "color"))

    with pytest.raises(IntegrityError):
        await catalog.filters(category, ("color", "checkbox"))


async def test_filter_type_is_checked(catalog: Catalog) -> None:
    category = await catalog.category()

    with pytest.raises(IntegrityError):
        await catalog.filters(category, ("color", "slider"))


# --- public --------------------------------------------------------------------------


async def test_filters_come_from_published_products_of_the_category(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()
    other = await catalog.category()
    await catalog.filters(
        category,
        ("color", "color"),
        ("material", "checkbox"),
        ("size", "select"),
        ("brand", "checkbox"),
        ("price", "range"),
    )
    await catalog.product(
        category,
        options=[{"color": "gold", "size": "M"}, {"color": "silver", "size": "M"}],
        attributes={"material": "steel"},
    )
    await catalog.product(category, options=[{"color": "gold"}], attributes={"material": "steel"})
    # None of these may contribute a value:
    await catalog.product(
        category,
        status=ProductStatus.DRAFT,
        published_at=None,
        options=[{"color": "red"}],
        attributes={"material": "wood"},
    )
    await catalog.product(category, deleted_at=utc_now(), options=[{"color": "blue"}])
    await catalog.product(category, options=[{"color": "green"}], variant_active=False)
    await catalog.product(other, options=[{"color": "black"}], attributes={"brand": "x"})

    response = await _filters(auth_client, category)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["key"] for item in items] == ["color", "material", "size"]
    assert items[0] == {
        "key": "color",
        "label": "Color",
        "type": "color",
        "values": [{"value": "gold", "count": 2}, {"value": "silver", "count": 1}],
    }
    assert items[1]["values"] == [{"value": "steel", "count": 2}]
    assert items[2]["values"] == [{"value": "M", "count": 1}]


async def test_inactive_filters_are_hidden(auth_client: AsyncClient, catalog: Catalog) -> None:
    category = await catalog.category()
    await catalog.filters(category, ("color", "color"))
    await catalog.product(category, options=[{"color": "gold"}])
    async with AsyncSession(catalog.engine) as session, session.begin():
        await session.execute(
            update(CategoryFilter)
            .where(CategoryFilter.category_id == category.id)
            .values(is_active=False)
        )

    response = await _filters(auth_client, category)

    assert response.json() == {"items": []}


@pytest.mark.parametrize("hidden", ["inactive", "deleted", "inactive_parent"])
async def test_filters_of_hidden_category_are_404(
    auth_client: AsyncClient, catalog: Catalog, hidden: str
) -> None:
    """SD rule: a soft-deleted or otherwise hidden category has no public filters."""
    parent = await catalog.category(is_active=hidden != "inactive_parent")
    category = await catalog.category(
        parent_id=parent.id,
        is_active=hidden != "inactive",
        deleted_at=utc_now() if hidden == "deleted" else None,
    )

    response = await _filters(auth_client, category)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_filters_reject_unknown_query_params(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    category = await catalog.category()

    response = await auth_client.get(f"{PUBLIC_URL}/{category.slug}/filters", params={"q": "x"})

    assert response.status_code == 400


# --- admin ---------------------------------------------------------------------------


def _item(key: str, filter_type: str, **extra: Any) -> dict[str, Any]:
    return {"attribute_key": key, "label": key.title(), "filter_type": filter_type, **extra}


async def _replace(
    client: AsyncClient, headers: Headers, category_id: UUID, filters: list[dict[str, Any]]
) -> Response:
    return await client.patch(
        f"{ADMIN_URL}/{category_id}/filters", json={"filters": filters}, headers=headers
    )


async def _audits(engine: AsyncEngine, category_id: UUID) -> list[AuditLog]:
    async with AsyncSession(engine) as session:
        statement = select(AuditLog).where(
            AuditLog.action == "category.filters_updated", AuditLog.entity_id == category_id
        )
        return list((await session.scalars(statement)).all())


async def test_admin_replaces_filter_set_with_audit(
    auth_client: AsyncClient, catalog: Catalog, login: Callable[..., Awaitable[Headers]]
) -> None:
    headers = await login("admin")
    category = await catalog.category()
    await catalog.filters(category, ("brand", "checkbox"))

    response = await _replace(
        auth_client,
        headers,
        category.id,
        [_item("size", "select", display_order=2), _item("color", "color", display_order=1)],
    )
    again = await _replace(
        auth_client,
        headers,
        category.id,
        [_item("color", "color", display_order=1), _item("size", "select", display_order=2)],
    )

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert [item["attribute_key"] for item in response.json()["items"]] == ["color", "size"]
    assert again.status_code == 200
    audits = await _audits(catalog.engine, category.id)
    assert len(audits) == 1
    diff = audits[0].metadata_["diff"]["filters"]
    assert [item["attribute_key"] for item in diff["before"]] == ["brand"]
    assert [item["attribute_key"] for item in diff["after"]] == ["color", "size"]


async def test_admin_can_clear_filters(
    auth_client: AsyncClient, catalog: Catalog, login: Callable[..., Awaitable[Headers]]
) -> None:
    headers = await login("admin")
    category = await catalog.category()
    await catalog.filters(category, ("brand", "checkbox"))

    response = await _replace(auth_client, headers, category.id, [])

    assert response.json() == {"items": []}


@pytest.mark.parametrize(
    "filters",
    [
        [_item("color", "color"), _item("color", "checkbox")],
        [_item("price", "checkbox")],
        [_item("material", "range")],
        [_item("material", "color")],
        [_item("color", "slider")],
        [_item(" ", "checkbox")],
        [{**_item("color", "color"), "id": str(uuid4())}],
        [_item(f"key{index}", "checkbox") for index in range(31)],
    ],
)
async def test_invalid_filter_set_is_400(
    auth_client: AsyncClient,
    catalog: Catalog,
    login: Callable[..., Awaitable[Headers]],
    filters: list[dict[str, Any]],
) -> None:
    headers = await login("admin")
    category = await catalog.category()

    response = await _replace(auth_client, headers, category.id, filters)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_unknown_or_deleted_category_is_404(
    auth_client: AsyncClient, catalog: Catalog, login: Callable[..., Awaitable[Headers]]
) -> None:
    headers = await login("admin")
    deleted = await catalog.category(deleted_at=utc_now())

    for category_id in (uuid4(), deleted.id):
        response = await _replace(auth_client, headers, category_id, [])
        assert response.status_code == 404


async def test_filters_need_authentication(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(f"{ADMIN_URL}/{uuid4()}/filters", json={})

    assert response.status_code == 401


@pytest.mark.parametrize("roles", [("customer",), ("support",), ("content_manager",)])
async def test_filters_need_catalog_manage(
    auth_client: AsyncClient,
    catalog: Catalog,
    login: Callable[..., Awaitable[Headers]],
    roles: tuple[str, ...],
) -> None:
    headers = await login(*roles)
    category = await catalog.category()

    response = await _replace(auth_client, headers, category.id, [_item("color", "color")])

    assert response.status_code == 403
