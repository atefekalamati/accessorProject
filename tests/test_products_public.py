from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, event, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import (
    Category,
    InventoryItem,
    Media,
    Product,
    ProductAttribute,
    ProductMedia,
    ProductStatus,
    ProductVariant,
    VariantOption,
)
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID

pytestmark = pytest.mark.integration

URL = "/api/v1/products"
MakeMedia = Callable[[], Awaitable[Media]]
INTERNAL_FIELDS = {
    "created_by",
    "updated_by",
    "deleted_at",
    "low_stock_threshold",
    "total",
    "reserved",
    "free",
    "total_quantity",
    "reserved_quantity",
    "price_version",
    "tax_enabled",
    "is_active",
    "is_purchasable",
    "status",
}


def _slug(prefix: str = "prd") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@dataclass
class Catalog:
    """Builds catalog rows directly in the database and removes them afterwards."""

    engine: AsyncEngine
    make_media: MakeMedia
    categories: list[UUID] = field(default_factory=list)

    async def category(self, *, parent: UUID | None = None, active: bool = True) -> Category:
        category = Category(title="Rings", slug=_slug("cat"), parent_id=parent, is_active=active)
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(category)
        self.categories.append(category.id)
        return category

    async def product(
        self, *, category: UUID | None = None, status: str = ProductStatus.PUBLISHED
    ) -> Product:
        category = category or (await self.category()).id
        product = Product(
            category_id=category,
            title="Silver ring",
            slug=_slug(),
            description="Handmade",
            status=status,
            published_at=utc_now() if status == ProductStatus.PUBLISHED else None,
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(product)
            await session.flush()
            session.add(
                ProductAttribute(
                    product_id=product.id, attribute_key="material", attribute_value="silver"
                )
            )
        return product

    async def variant(
        self,
        product: Product,
        *,
        options: dict[str, str] | None = None,
        stock: tuple[int, int, int] | None = None,
        **fields: Any,
    ) -> ProductVariant:
        values: dict[str, Any] = {"base_price": 100_000, "is_active": True} | fields
        variant = ProductVariant(
            product_id=product.id, sku=f"SKU-{uuid4().hex[:10].upper()}", **values
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(variant)
            await session.flush()
            session.add_all(
                VariantOption(variant_id=variant.id, option_key=key, value=value)
                for key, value in (options or {}).items()
            )
            if stock is not None:
                total, reserved, threshold = stock
                session.add(
                    InventoryItem(
                        warehouse_id=DEFAULT_WAREHOUSE_ID,
                        product_id=product.id,
                        variant_id=variant.id,
                        total_quantity=total,
                        reserved_quantity=reserved,
                        low_stock_threshold=threshold,
                    )
                )
        return variant

    async def image(
        self,
        product: Product,
        *,
        is_main: bool = False,
        variant: ProductVariant | None = None,
        order: int = 0,
    ) -> ProductMedia:
        media = await self.make_media()
        item = ProductMedia(
            product_id=product.id,
            media_id=media.id,
            variant_id=None if variant is None else variant.id,
            is_main=is_main,
            display_order=order,
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(item)
        return item

    async def set(self, model: Any, row_id: UUID, **values: Any) -> None:
        async with AsyncSession(self.engine) as session, session.begin():
            await session.execute(update(model).where(model.id == row_id).values(**values))


@pytest_asyncio.fixture
async def catalog(db_engine: AsyncEngine, make_media: MakeMedia) -> AsyncIterator[Catalog]:
    built = Catalog(db_engine, make_media)
    yield built
    ids = built.categories
    async with AsyncSession(db_engine) as session, session.begin():
        products = select(Product.id).where(Product.category_id.in_(ids))
        variants = select(ProductVariant.id).where(ProductVariant.product_id.in_(products))
        await session.execute(delete(ProductMedia).where(ProductMedia.product_id.in_(products)))
        await session.execute(delete(InventoryItem).where(InventoryItem.product_id.in_(products)))
        await session.execute(delete(VariantOption).where(VariantOption.variant_id.in_(variants)))
        await session.execute(delete(ProductVariant).where(ProductVariant.product_id.in_(products)))
        await session.execute(
            delete(ProductAttribute).where(ProductAttribute.product_id.in_(products))
        )
        await session.execute(delete(Product).where(Product.category_id.in_(ids)))
        await session.execute(update(Category).where(Category.id.in_(ids)).values(parent_id=None))
        await session.execute(delete(Category).where(Category.id.in_(ids)))


@contextmanager
def _count_queries(client: AsyncClient) -> Iterator[list[str]]:
    engine = client._transport.app.state.db_engine.sync_engine  # type: ignore[attr-defined]
    statements: list[str] = []

    def record(*args: Any) -> None:
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        nested = set().union(*(_keys(item) for item in value.values())) if value else set()
        return set(value) | nested
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value)) if value else set()
    return set()


# --- contract ------------------------------------------------------------------------


async def test_published_product_contract(auth_client: AsyncClient, catalog: Catalog) -> None:
    root = await catalog.category()
    main = await catalog.category(parent=root.id)
    product = await catalog.product(category=main.id)
    now = utc_now()
    on_sale = await catalog.variant(
        product,
        options={"color": "Gold", "size": "M"},
        base_price=30_000,
        sale_price=20_000,
        sale_start_at=now - timedelta(days=1),
        sale_end_at=now + timedelta(days=1),
        stock=(10, 0, 3),
        display_order=1,
    )
    low = await catalog.variant(
        product, options={"color": "Silver", "size": "M"}, stock=(5, 3, 2), display_order=2
    )
    main_image = await catalog.image(product, is_main=True, order=5)
    gallery = await catalog.image(product, order=1, variant=low)

    response = await auth_client.get(f"{URL}/{product.slug}")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "id",
        "slug",
        "title",
        "description",
        "published_at",
        "breadcrumb",
        "attributes",
        "options",
        "variants",
        "default_variant_id",
        "price_range",
        "tax_included",
        "availability",
        "media",
    }
    assert not _keys(body) & INTERNAL_FIELDS
    assert [item["id"] for item in body["breadcrumb"]] == [str(root.id), str(main.id)]
    assert body["attributes"] == [{"key": "material", "value": "silver"}]
    assert body["options"] == {"color": ["Gold", "Silver"], "size": ["M"]}
    first, second = body["variants"]
    assert first["id"] == str(on_sale.id)
    assert first["price"] == {
        "base_price": 30_000,
        "sale_price": 20_000,
        "final_price": 20_000,
        "discount_amount": 10_000,
        "discount_percent": 33,
    }
    assert (first["availability"], first["purchasable"]) == ("in_stock", True)
    assert (second["availability"], second["purchasable"]) == ("low_stock", True)
    assert second["price"]["sale_price"] is None
    assert body["default_variant_id"] == str(on_sale.id)
    assert body["price_range"] == {"min": 20_000, "max": 100_000}
    assert body["tax_included"] is False
    assert body["availability"] == "in_stock"
    assert [item["id"] for item in body["media"]] == [str(main_image.id), str(gallery.id)]
    assert body["media"][0]["url"].startswith("https://cdn.example.com/media/")
    assert body["media"][1]["variant_id"] == str(low.id)


async def test_hidden_products_get_the_same_404(auth_client: AsyncClient, catalog: Catalog) -> None:
    draft = await catalog.product(status=ProductStatus.DRAFT)
    archived = await catalog.product(status=ProductStatus.ARCHIVED)
    deleted = await catalog.product()
    await catalog.variant(deleted)
    await catalog.set(Product, deleted.id, deleted_at=utc_now())

    bodies = []
    for slug in (draft.slug, archived.slug, deleted.slug, _slug()):
        response = await auth_client.get(f"{URL}/{slug}")
        assert response.status_code == 404
        body = response.json()
        body.pop("request_id")
        bodies.append(body)

    assert all(body == bodies[0] for body in bodies)
    assert bodies[0]["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("slug", ["ab", "Bad-Slug", "x" * 121, "bad_slug"])
async def test_invalid_slug_is_400(auth_client: AsyncClient, slug: str) -> None:
    response = await auth_client.get(f"{URL}/{slug}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_unknown_query_parameter_is_400(auth_client: AsyncClient) -> None:
    response = await auth_client.get(f"{URL}/{_slug()}", params={"debug": "1"})

    assert response.status_code == 400


# --- variants, media, prices and stock -----------------------------------------------


async def test_hidden_variants_and_their_images_are_left_out(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    product = await catalog.product()
    shown = await catalog.variant(product, options={"size": "S"}, stock=(1, 0, 0))
    inactive = await catalog.variant(product, options={"size": "M"}, is_active=False)
    deleted = await catalog.variant(product, options={"size": "L"})
    await catalog.set(ProductVariant, deleted.id, deleted_at=utc_now())
    await catalog.image(product, is_main=True)
    await catalog.image(product, variant=inactive)
    await catalog.image(product, variant=deleted)

    body = (await auth_client.get(f"{URL}/{product.slug}")).json()

    assert [item["id"] for item in body["variants"]] == [str(shown.id)]
    assert body["options"] == {"size": ["S"]}
    assert len(body["media"]) == 1
    assert body["media"][0]["variant_id"] is None


async def test_sale_outside_its_window_has_no_effect(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    product = await catalog.product()
    now = utc_now()
    await catalog.variant(
        product,
        base_price=50_000,
        sale_price=40_000,
        sale_start_at=now - timedelta(days=2),
        sale_end_at=now - timedelta(days=1),
    )

    price = (await auth_client.get(f"{URL}/{product.slug}")).json()["variants"][0]["price"]

    assert price == {
        "base_price": 50_000,
        "sale_price": None,
        "final_price": 50_000,
        "discount_amount": 0,
        "discount_percent": 0,
    }


async def test_purchasable_and_availability_rules(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    product = await catalog.product()
    not_for_sale = await catalog.variant(
        product, options={"size": "S"}, is_purchasable=False, stock=(5, 0, 0), display_order=1
    )
    no_item = await catalog.variant(product, options={"size": "M"}, display_order=2)
    sold_out = await catalog.variant(
        product, options={"size": "L"}, stock=(3, 3, 0), display_order=3
    )
    low = await catalog.variant(product, options={"size": "XL"}, stock=(2, 0, 2), display_order=4)

    body = (await auth_client.get(f"{URL}/{product.slug}")).json()

    variants = {item["id"]: item for item in body["variants"]}
    assert (
        variants[str(not_for_sale.id)]["availability"],
        variants[str(not_for_sale.id)]["purchasable"],
    ) == ("in_stock", False)
    assert (
        variants[str(no_item.id)]["availability"],
        variants[str(no_item.id)]["purchasable"],
    ) == ("out_of_stock", False)
    assert (
        variants[str(sold_out.id)]["availability"],
        variants[str(sold_out.id)]["purchasable"],
    ) == ("out_of_stock", False)
    assert (variants[str(low.id)]["availability"], variants[str(low.id)]["purchasable"]) == (
        "low_stock",
        True,
    )
    # The first purchasable variant, not the first one.
    assert body["default_variant_id"] == str(low.id)
    assert body["availability"] == "in_stock"


async def test_sold_out_product_is_shown_with_first_variant_as_default(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    product = await catalog.product()
    first = await catalog.variant(product, options={"size": "S"}, display_order=1)
    await catalog.variant(product, options={"size": "M"}, stock=(1, 1, 0), display_order=2)

    body = (await auth_client.get(f"{URL}/{product.slug}")).json()

    assert body["availability"] == "out_of_stock"
    assert body["default_variant_id"] == str(first.id)
    assert not any(item["purchasable"] for item in body["variants"])


# --- categories ----------------------------------------------------------------------


async def test_hidden_category_drops_out_of_the_breadcrumb(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    root = await catalog.category()
    hidden = await catalog.category(parent=root.id, active=False)
    leaf = await catalog.category(parent=hidden.id)
    product = await catalog.product(category=leaf.id)
    await catalog.variant(product)
    inactive_root = await catalog.category(active=False)
    other = await catalog.product(category=inactive_root.id)
    await catalog.variant(other)

    nested = await auth_client.get(f"{URL}/{product.slug}")
    top = await auth_client.get(f"{URL}/{other.slug}")

    assert nested.status_code == 200
    assert [item["id"] for item in nested.json()["breadcrumb"]] == [str(root.id)]
    assert top.status_code == 200
    assert top.json()["breadcrumb"] == []


# --- queries -------------------------------------------------------------------------


async def test_query_count_does_not_grow_with_variants_or_media(
    auth_client: AsyncClient, catalog: Catalog
) -> None:
    small = await catalog.product()
    await catalog.variant(small, options={"size": "S"}, stock=(1, 0, 0))
    await catalog.image(small, is_main=True)
    large = await catalog.product()
    for index in range(6):
        variant = await catalog.variant(large, options={"size": f"S{index}"}, stock=(1, 0, 0))
        await catalog.image(large, variant=variant, is_main=index == 0)
    await auth_client.get(f"{URL}/{small.slug}")  # warm-up (connection setup)

    with _count_queries(auth_client) as small_queries:
        assert (await auth_client.get(f"{URL}/{small.slug}")).status_code == 200
    with _count_queries(auth_client) as large_queries:
        assert (await auth_client.get(f"{URL}/{large.slug}")).status_code == 200

    assert len(large_queries) == len(small_queries)
