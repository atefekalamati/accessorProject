from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from conftest import Account, MakeAccount
from httpx import AsyncClient, Response
from PIL import Image
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    AuditLog,
    Category,
    InventoryItem,
    InventoryMovement,
    InventoryReservation,
    InventoryReservationItem,
    Media,
    PriceHistory,
    Product,
    ProductAttribute,
    ProductMedia,
    ProductVariant,
    Role,
    RolePermission,
    UserRole,
    VariantOption,
)
from app.db.models.inventory import DEFAULT_WAREHOUSE_ID
from app.db.seed import permission_id, role_id
from app.shared.money import MAX_PRICE_TOMAN
from app.shared.storage import InMemoryFileStorage

pytestmark = pytest.mark.integration

PRODUCTS_URL = "/api/v1/admin/products"
VARIANTS_URL = "/api/v1/admin/product-variants"
CATEGORIES_URL = "/api/v1/admin/categories"
CATALOG_ONLY_ROLE = "test_catalog_only"


def _slug(prefix: str = "prd") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _sku() -> str:
    return f"sku-{uuid4().hex[:10]}"


def _image(fmt: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 120, 200)).save(output, fmt)
    return output.getvalue()


def _storage(client: AsyncClient) -> InMemoryFileStorage:
    storage = client._transport.app.state.file_storage  # type: ignore[attr-defined]
    assert isinstance(storage, InMemoryFileStorage)
    return storage


def _error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    return body


# --- fixtures ------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin(make_account: MakeAccount) -> Account:
    return await make_account("admin")


@pytest_asyncio.fixture
async def catalog_only(make_account: MakeAccount, db_engine: AsyncEngine) -> AsyncIterator[Account]:
    """catalog:manage without pricing:update (no seeded role has that combination)."""
    async with AsyncSession(db_engine) as session, session.begin():
        await session.merge(
            Role(id=role_id(CATALOG_ONLY_ROLE), name=CATALOG_ONLY_ROLE, is_system=False)
        )
        await session.flush()
        exists = await session.scalar(
            select(func.count()).where(
                RolePermission.role_id == role_id(CATALOG_ONLY_ROLE),
                RolePermission.permission_id == permission_id("catalog:manage"),
            )
        )
        if not exists:
            session.add(
                RolePermission(
                    role_id=role_id(CATALOG_ONLY_ROLE),
                    permission_id=permission_id("catalog:manage"),
                )
            )
    yield await make_account(CATALOG_ONLY_ROLE)
    # Other tests count the seeded roles and permissions.
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(
            delete(UserRole).where(UserRole.role_id == role_id(CATALOG_ONLY_ROLE))
        )
        await session.execute(
            delete(RolePermission).where(RolePermission.role_id == role_id(CATALOG_ONLY_ROLE))
        )
        await session.execute(delete(Role).where(Role.id == role_id(CATALOG_ONLY_ROLE)))


@dataclass
class Created:
    categories: list[UUID] = field(default_factory=list)


@pytest_asyncio.fixture
async def created(db_engine: AsyncEngine) -> AsyncIterator[Created]:
    """Categories made by a test; their products, variants and media go with them."""
    tracked = Created()
    yield tracked
    ids = tracked.categories
    async with AsyncSession(db_engine) as session, session.begin():
        products = select(Product.id).where(Product.category_id.in_(ids))
        variants = select(ProductVariant.id).where(ProductVariant.product_id.in_(products))
        media = select(ProductMedia.media_id).where(ProductMedia.product_id.in_(products))
        media_ids = list((await session.scalars(media)).all())
        await session.execute(delete(ProductMedia).where(ProductMedia.product_id.in_(products)))
        await session.execute(delete(Media).where(Media.id.in_(media_ids)))
        items = select(InventoryItem.id).where(InventoryItem.product_id.in_(products))
        reservations = list(
            await session.scalars(
                select(InventoryReservationItem.reservation_id).where(
                    InventoryReservationItem.inventory_item_id.in_(items)
                )
            )
        )
        await session.execute(
            delete(InventoryReservationItem).where(
                InventoryReservationItem.reservation_id.in_(reservations)
            )
        )
        await session.execute(
            delete(InventoryReservation).where(InventoryReservation.id.in_(reservations))
        )
        await session.execute(
            delete(InventoryMovement).where(InventoryMovement.inventory_item_id.in_(items))
        )
        await session.execute(delete(InventoryItem).where(InventoryItem.product_id.in_(products)))
        await session.execute(delete(PriceHistory).where(PriceHistory.product_id.in_(products)))
        await session.execute(delete(VariantOption).where(VariantOption.variant_id.in_(variants)))
        await session.execute(delete(ProductVariant).where(ProductVariant.product_id.in_(products)))
        await session.execute(
            delete(ProductAttribute).where(ProductAttribute.product_id.in_(products))
        )
        await session.execute(delete(Product).where(Product.category_id.in_(ids)))
        await session.execute(update(Category).where(Category.id.in_(ids)).values(parent_id=None))
        await session.execute(delete(Category).where(Category.id.in_(ids)))


async def _category(client: AsyncClient, actor: Account, created: Created) -> UUID:
    response = await client.post(
        CATEGORIES_URL, json={"title": "Rings", "slug": _slug("cat")}, headers=actor.headers
    )
    assert response.status_code == 201, response.text
    category_id = UUID(response.json()["id"])
    created.categories.append(category_id)
    return category_id


async def _create_product(
    client: AsyncClient, actor: Account, created: Created, **fields: Any
) -> Response:
    if "category_id" not in fields:
        fields["category_id"] = str(await _category(client, actor, created))
    body = {"title": "Silver ring", "slug": _slug(), **fields}
    return await client.post(PRODUCTS_URL, json=body, headers=actor.headers)


async def _product(client: AsyncClient, actor: Account, created: Created, **fields: Any) -> UUID:
    response = await _create_product(client, actor, created, **fields)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _create_variant(
    client: AsyncClient, actor: Account, product_id: UUID, **fields: Any
) -> Response:
    body = {"sku": _sku(), **fields}
    return await client.post(
        f"{PRODUCTS_URL}/{product_id}/variants", json=body, headers=actor.headers
    )


async def _variant(client: AsyncClient, actor: Account, product_id: UUID, **fields: Any) -> UUID:
    response = await _create_variant(client, actor, product_id, **fields)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _upload(
    client: AsyncClient,
    actor: Account,
    product_id: UUID,
    data: bytes | None = None,
    /,
    **fields: str,
) -> Response:
    files = {"file": ("photo.png", _image() if data is None else data, "image/png")}
    return await client.post(
        f"{PRODUCTS_URL}/{product_id}/media", files=files, data=fields, headers=actor.headers
    )


async def _media(client: AsyncClient, actor: Account, product_id: UUID, **fields: str) -> UUID:
    response = await _upload(client, actor, product_id, **fields)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _publishable(
    client: AsyncClient, actor: Account, created: Created
) -> tuple[UUID, UUID, UUID]:
    """A draft product with one active priced variant and a main image."""
    product_id = await _product(client, actor, created)
    variant_id = await _variant(client, actor, product_id, base_price=150_000, is_active=True)
    media_id = await _media(client, actor, product_id)
    return product_id, variant_id, media_id


async def _set_status(
    client: AsyncClient, actor: Account, product_id: UUID, status: str
) -> Response:
    return await client.patch(
        f"{PRODUCTS_URL}/{product_id}/status", json={"status": status}, headers=actor.headers
    )


async def _detail(client: AsyncClient, actor: Account, product_id: UUID) -> dict[str, Any]:
    response = await client.get(f"{PRODUCTS_URL}/{product_id}", headers=actor.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _audits(db_engine: AsyncEngine, entity_id: UUID) -> list[AuditLog]:
    async with AsyncSession(db_engine) as session:
        statement = (
            select(AuditLog).where(AuditLog.entity_id == entity_id).order_by(AuditLog.created_at)
        )
        return list((await session.scalars(statement)).all())


# --- authorization -------------------------------------------------------------------

# Fixed, so every pytest-xdist worker collects the same test ids.
_ID = "00000000-0000-4000-8000-000000000001"
ENDPOINTS = [
    ("GET", PRODUCTS_URL),
    ("GET", f"{PRODUCTS_URL}/{_ID}"),
    ("POST", PRODUCTS_URL),
    ("PATCH", f"{PRODUCTS_URL}/{_ID}"),
    ("PATCH", f"{PRODUCTS_URL}/{_ID}/status"),
    ("DELETE", f"{PRODUCTS_URL}/{_ID}"),
    ("POST", f"{PRODUCTS_URL}/{_ID}/variants"),
    ("PATCH", f"{VARIANTS_URL}/{_ID}"),
    ("DELETE", f"{VARIANTS_URL}/{_ID}"),
    ("POST", f"{PRODUCTS_URL}/{_ID}/media"),
    ("PATCH", f"{PRODUCTS_URL}/{_ID}/media/{_ID}"),
    ("DELETE", f"{PRODUCTS_URL}/{_ID}/media/{_ID}"),
]


@pytest.mark.parametrize(("method", "url"), ENDPOINTS)
async def test_endpoints_need_authentication_before_validation(
    auth_client: AsyncClient, method: str, url: str
) -> None:
    response = await auth_client.request(method, url, json={"unknown": True})

    _error(response, 401, "UNAUTHORIZED")


@pytest.mark.parametrize("role", ["content_manager", "support", "customer"])
@pytest.mark.parametrize(("method", "url"), ENDPOINTS)
async def test_endpoints_need_catalog_manage(
    auth_client: AsyncClient, make_account: MakeAccount, role: str, method: str, url: str
) -> None:
    account = await make_account(role)

    response = await auth_client.request(method, url, json={}, headers=account.headers)

    _error(response, 403, "FORBIDDEN")


# --- create / read -------------------------------------------------------------------


async def test_create_product_is_a_draft_and_ignores_system_fields(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    response = await _create_product(
        auth_client,
        admin,
        created,
        status="published",
        published_at="2026-01-01T00:00:00Z",
        id=str(uuid4()),
        created_by=str(uuid4()),
        description="Handmade",
        is_featured=True,
        attributes=[{"key": "material", "value": "silver"}, {"key": "weight", "value": "4g"}],
    )

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == "draft"
    assert body["published_at"] is None
    assert body["created_by"] == str(admin.id)
    assert body["is_featured"] is True
    assert body["attributes"] == [
        {"key": "material", "value": "silver"},
        {"key": "weight", "value": "4g"},
    ]
    assert body["variants"] == []
    assert body["media"] == []
    assert body["publish_blockers"] == ["no_active_priced_variant", "no_main_image"]
    audits = await _audits(db_engine, UUID(body["id"]))
    assert [audit.action for audit in audits] == ["product.created"]


@pytest.mark.parametrize(
    "fields",
    [
        {"unknown": 1},
        {"slug": "Bad Slug"},
        {"slug": "ab"},
        {"title": "   "},
        {"title": "x" * 201},
        {"description": "x" * 10_001},
        {"attributes": [{"key": "a", "value": "1"}, {"key": "a", "value": "2"}]},
        {"attributes": [{"key": f"k{i}", "value": "v"} for i in range(51)]},
        {"attributes": [{"key": "a", "value": ""}]},
    ],
)
async def test_create_product_validation(
    auth_client: AsyncClient, admin: Account, created: Created, fields: dict[str, Any]
) -> None:
    response = await _create_product(auth_client, admin, created, **fields)

    _error(response, 400, "VALIDATION_ERROR")


async def test_create_product_with_duplicate_slug(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    slug = _slug()
    await _product(auth_client, admin, created, slug=slug)

    response = await _create_product(auth_client, admin, created, slug=slug)

    _error(response, 409, "DUPLICATE_SLUG")


async def test_slug_of_a_deleted_product_is_reusable(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    slug = _slug()
    product_id = await _product(auth_client, admin, created, slug=slug)
    deleted = await auth_client.delete(f"{PRODUCTS_URL}/{product_id}", headers=admin.headers)
    assert deleted.status_code == 204

    response = await _create_product(auth_client, admin, created, slug=slug)

    assert response.status_code == 201, response.text


async def test_create_product_in_missing_or_deleted_category(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    missing = await _create_product(auth_client, admin, created, category_id=str(uuid4()))
    _error(missing, 404, "NOT_FOUND")

    category_id = await _category(auth_client, admin, created)
    deleted = await auth_client.delete(f"{CATEGORIES_URL}/{category_id}", headers=admin.headers)
    assert deleted.status_code == 204
    response = await _create_product(auth_client, admin, created, category_id=str(category_id))
    _error(response, 404, "NOT_FOUND")


async def test_get_missing_product(auth_client: AsyncClient, admin: Account) -> None:
    missing = await auth_client.get(f"{PRODUCTS_URL}/{uuid4()}", headers=admin.headers)
    invalid = await auth_client.get(f"{PRODUCTS_URL}/not-a-uuid", headers=admin.headers)

    _error(missing, 404, "NOT_FOUND")
    _error(invalid, 400, "VALIDATION_ERROR")


async def test_detail_shows_variant_stock_from_inventory(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created)
    stocked = await _variant(auth_client, admin, product_id, base_price=1000, options={"size": "M"})
    await _variant(auth_client, admin, product_id, options={"size": "L"})
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(
            InventoryItem(
                warehouse_id=DEFAULT_WAREHOUSE_ID,
                product_id=product_id,
                variant_id=stocked,
                total_quantity=10,
                reserved_quantity=2,
                low_stock_threshold=3,
            )
        )

    variants = {
        item["id"]: item for item in (await _detail(auth_client, admin, product_id))["variants"]
    }

    assert variants[str(stocked)]["stock"] == {
        "total": 10,
        "reserved": 2,
        "free": 8,
        "low_stock_threshold": 3,
        "status": "in_stock",
    }
    unstocked = next(item for key, item in variants.items() if key != str(stocked))
    assert unstocked["stock"]["status"] == "out_of_stock"
    assert unstocked["stock"]["free"] == 0


# --- update --------------------------------------------------------------------------


async def test_update_product_fields_and_attributes(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(
        auth_client, admin, created, attributes=[{"key": "material", "value": "gold"}]
    )
    other_category = await _category(auth_client, admin, created)

    response = await auth_client.patch(
        f"{PRODUCTS_URL}/{product_id}",
        json={
            "title": "Gold ring",
            "category_id": str(other_category),
            "attributes": [{"key": "color", "value": "yellow"}],
            "updated_at": "2020-01-01T00:00:00Z",
        },
        headers=admin.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Gold ring"
    assert body["category_id"] == str(other_category)
    assert body["attributes"] == [{"key": "color", "value": "yellow"}]
    assert body["updated_by"] == str(admin.id)
    actions = [audit.action for audit in await _audits(db_engine, product_id)]
    assert actions == ["product.created", "product.updated"]


async def test_update_without_changes_is_not_audited(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created, title="Same")

    response = await auth_client.patch(
        f"{PRODUCTS_URL}/{product_id}", json={"title": "Same"}, headers=admin.headers
    )

    assert response.status_code == 200
    assert [audit.action for audit in await _audits(db_engine, product_id)] == ["product.created"]


@pytest.mark.parametrize(
    "body",
    [{}, {"title": None}, {"attributes": None}, {"status": "published"}, {"slug": "BAD"}],
)
async def test_update_product_validation(
    auth_client: AsyncClient, admin: Account, created: Created, body: dict[str, Any]
) -> None:
    product_id = await _product(auth_client, admin, created)

    response = await auth_client.patch(
        f"{PRODUCTS_URL}/{product_id}", json=body, headers=admin.headers
    )

    _error(response, 400, "VALIDATION_ERROR")


async def test_update_product_conflicts_and_missing(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    taken = _slug()
    await _product(auth_client, admin, created, slug=taken)
    product_id = await _product(auth_client, admin, created)

    duplicate = await auth_client.patch(
        f"{PRODUCTS_URL}/{product_id}", json={"slug": taken}, headers=admin.headers
    )
    no_category = await auth_client.patch(
        f"{PRODUCTS_URL}/{product_id}", json={"category_id": str(uuid4())}, headers=admin.headers
    )
    missing = await auth_client.patch(
        f"{PRODUCTS_URL}/{uuid4()}", json={"title": "x"}, headers=admin.headers
    )

    _error(duplicate, 409, "DUPLICATE_SLUG")
    _error(no_category, 404, "NOT_FOUND")
    _error(missing, 404, "NOT_FOUND")


# --- list ----------------------------------------------------------------------------


async def test_list_filters_search_and_summaries(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    category_id = await _category(auth_client, admin, created)
    marker = uuid4().hex[:8]
    first = await _product(
        auth_client, admin, created, category_id=str(category_id), title=f"A {marker}"
    )
    await _variant(
        auth_client, admin, first, base_price=2000, is_active=True, options={"size": "S"}
    )
    await _variant(
        auth_client, admin, first, base_price=5000, is_active=True, options={"size": "L"}
    )
    await _variant(auth_client, admin, first, base_price=9000, options={"size": "XL"})
    await _media(auth_client, admin, first)
    sku = f"FIND-{uuid4().hex[:10].upper()}"
    second = await _product(auth_client, admin, created, category_id=str(category_id), title="B")
    await _variant(auth_client, admin, second, sku=sku)
    deleted = await _product(auth_client, admin, created, category_id=str(category_id))
    await auth_client.delete(f"{PRODUCTS_URL}/{deleted}", headers=admin.headers)

    by_category = await auth_client.get(
        PRODUCTS_URL,
        params={"category_id": str(category_id), "sort": "title"},
        headers=admin.headers,
    )
    by_sku = await auth_client.get(PRODUCTS_URL, params={"q": sku.lower()}, headers=admin.headers)
    by_title = await auth_client.get(PRODUCTS_URL, params={"q": marker}, headers=admin.headers)
    drafts = await auth_client.get(
        PRODUCTS_URL,
        params={"category_id": str(category_id), "status": "published"},
        headers=admin.headers,
    )

    assert by_category.status_code == 200, by_category.text
    assert by_category.headers["cache-control"] == "no-store"
    page = by_category.json()
    assert page["total"] == 2
    assert [item["id"] for item in page["items"]] == [str(first), str(second)]
    item = page["items"][0]
    assert item["active_variant_count"] == 2
    assert item["price_range"] == {"min": 2000, "max": 5000}
    assert item["main_image_url"].startswith("https://cdn.example.com/media/")
    assert item["category"]["id"] == str(category_id)
    assert page["items"][1]["price_range"] is None
    assert page["items"][1]["main_image_url"] is None
    assert [item["id"] for item in by_sku.json()["items"]] == [str(second)]
    assert [item["id"] for item in by_title.json()["items"]] == [str(first)]
    assert drafts.json()["total"] == 0


async def test_list_search_escapes_like_wildcards(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    await _product(auth_client, admin, created)

    response = await auth_client.get(PRODUCTS_URL, params={"q": "%"}, headers=admin.headers)

    assert response.status_code == 200
    assert all("%" in item["title"] for item in response.json()["items"])


@pytest.mark.parametrize(
    "params",
    [
        {"unknown": "1"},
        {"limit": "101"},
        {"page": "0"},
        {"q": "   "},
        {"q": "x" * 101},
        {"status": "deleted"},
        {"category_id": "nope"},
        {"sort": "price"},
    ],
)
async def test_list_validation(
    auth_client: AsyncClient, admin: Account, params: dict[str, str]
) -> None:
    response = await auth_client.get(PRODUCTS_URL, params=params, headers=admin.headers)

    _error(response, 400, "VALIDATION_ERROR")


# --- status --------------------------------------------------------------------------


async def test_publish_flow(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id, _variant_id, _media_id = await _publishable(auth_client, admin, created)

    published = await _set_status(auth_client, admin, product_id, "published")
    assert published.status_code == 200, published.text
    first_published_at = published.json()["published_at"]
    assert first_published_at is not None
    assert published.json()["publish_blockers"] == []

    again = await _set_status(auth_client, admin, product_id, "published")
    draft = await _set_status(auth_client, admin, product_id, "draft")
    republished = await _set_status(auth_client, admin, product_id, "published")
    archived = await _set_status(auth_client, admin, product_id, "archived")

    assert again.status_code == 200
    assert draft.json()["status"] == "draft"
    assert republished.json()["published_at"] == first_published_at
    assert archived.json()["status"] == "archived"
    actions = [audit.action for audit in await _audits(db_engine, product_id)]
    assert actions == ["product.created"] + ["product.status_changed"] * 4


async def test_publish_blockers(auth_client: AsyncClient, admin: Account, created: Created) -> None:
    product_id = await _product(auth_client, admin, created)
    await _variant(auth_client, admin, product_id)  # inactive, no price

    response = await _set_status(auth_client, admin, product_id, "published")

    body = _error(response, 422, "BUSINESS_RULE_VIOLATION")
    assert [item["code"] for item in body["details"]] == [
        "no_active_priced_variant",
        "no_main_image",
    ]


async def test_invalid_transitions(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    product_id = await _product(auth_client, admin, created)
    archived = await _set_status(auth_client, admin, product_id, "archived")
    assert archived.status_code == 200

    response = await _set_status(auth_client, admin, product_id, "published")
    invalid = await _set_status(auth_client, admin, product_id, "deleted")
    missing = await _set_status(auth_client, admin, uuid4(), "draft")

    _error(response, 422, "INVALID_STATE_TRANSITION")
    _error(invalid, 400, "VALIDATION_ERROR")
    _error(missing, 404, "NOT_FOUND")


# --- delete --------------------------------------------------------------------------


async def test_delete_product_soft_deletes_it_and_its_variants(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id, variant_id, _media_id = await _publishable(auth_client, admin, created)

    response = await auth_client.delete(f"{PRODUCTS_URL}/{product_id}", headers=admin.headers)

    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    async with AsyncSession(db_engine) as session:
        product = await session.get(Product, product_id)
        variant = await session.get(ProductVariant, variant_id)
    assert product is not None and product.deleted_at is not None
    assert variant is not None and variant.deleted_at is not None
    detail = await auth_client.get(f"{PRODUCTS_URL}/{product_id}", headers=admin.headers)
    patch = await auth_client.patch(
        f"{PRODUCTS_URL}/{product_id}", json={"title": "x"}, headers=admin.headers
    )
    variant_patch = await auth_client.patch(
        f"{VARIANTS_URL}/{variant_id}", json={"is_purchasable": False}, headers=admin.headers
    )
    new_variant = await _create_variant(auth_client, admin, product_id)
    again = await auth_client.delete(f"{PRODUCTS_URL}/{product_id}", headers=admin.headers)
    for missing in (detail, patch, variant_patch, new_variant, again):
        _error(missing, 404, "NOT_FOUND")
    listed = await auth_client.get(
        PRODUCTS_URL, params={"q": str(product.slug)}, headers=admin.headers
    )
    assert listed.json()["total"] == 0
    audit = (await _audits(db_engine, product_id))[-1]
    assert audit.action == "product.deleted"
    assert str(variant_id) in str(audit.metadata_["diff"])


# --- variants ------------------------------------------------------------------------


async def test_create_variant_with_initial_price(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created)

    response = await _create_variant(
        auth_client,
        admin,
        product_id,
        sku="  ring-001-s ",
        options={"color": " Silver ", "size": "S"},
        base_price=150_000,
        sale_price=120_000,
        sale_start_at="2026-10-01T00:00:00Z",
        sale_end_at="2026-11-01T00:00:00Z",
        is_active=True,
        price_version=9,
        stock=100,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sku"] == "RING-001-S"
    assert body["options"] == {"color": "Silver", "size": "S"}
    assert (body["base_price"], body["sale_price"], body["price_version"]) == (150_000, 120_000, 0)
    assert body["is_active"] is True
    assert body["stock"]["status"] == "out_of_stock"
    actions = [audit.action for audit in await _audits(db_engine, UUID(body["id"]))]
    assert actions == ["product_variant.created"]


async def test_initial_price_needs_pricing_update(
    auth_client: AsyncClient, admin: Account, catalog_only: Account, created: Created
) -> None:
    product_id = await _product(auth_client, admin, created)

    priced = await _create_variant(auth_client, catalog_only, product_id, base_price=1000)
    null_price = await _create_variant(auth_client, catalog_only, product_id, base_price=None)
    unpriced = await _create_variant(auth_client, catalog_only, product_id)

    _error(priced, 403, "FORBIDDEN")
    _error(null_price, 403, "FORBIDDEN")
    assert unpriced.status_code == 201, unpriced.text


@pytest.mark.parametrize(
    "fields",
    [
        {"sku": "bad sku!"},
        {"sku": "X" * 65},
        {"options": {"material": "gold"}},
        {"options": {"color": ""}},
        {"options": {"color": "x" * 51}},
        {"base_price": 0},
        {"base_price": MAX_PRICE_TOMAN + 1},
        {"base_price": "1000"},
        {"base_price": 10.5},
        {"base_price": 1000, "sale_price": 1001},
        {"sale_price": 100},
        {"base_price": 1000, "sale_start_at": "2026-10-01T00:00:00Z"},
        {
            "base_price": 1000,
            "sale_price": 900,
            "sale_start_at": "2026-11-01T00:00:00Z",
            "sale_end_at": "2026-10-01T00:00:00Z",
        },
        {"base_price": 1000, "sale_price": 900, "sale_start_at": "2026-10-01T00:00:00"},
        {"display_order": -1},
        {"unknown": True},
    ],
)
async def test_create_variant_validation(
    auth_client: AsyncClient, admin: Account, created: Created, fields: dict[str, Any]
) -> None:
    product_id = await _product(auth_client, admin, created)

    response = await _create_variant(auth_client, admin, product_id, **fields)

    _error(response, 400, "VALIDATION_ERROR")


async def test_create_variant_rules(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    product_id = await _product(auth_client, admin, created)
    other_product = await _product(auth_client, admin, created)
    sku = _sku()
    await _variant(auth_client, admin, other_product, sku=sku)
    await _variant(auth_client, admin, product_id, options={"color": "Red"})
    await _variant(auth_client, admin, product_id)

    active_without_price = await _create_variant(auth_client, admin, product_id, is_active=True)
    duplicate_sku = await _create_variant(auth_client, admin, product_id, sku=sku.upper())
    duplicate_options = await _create_variant(
        auth_client, admin, product_id, options={"color": "Red"}
    )
    second_default = await _create_variant(auth_client, admin, product_id)
    missing = await _create_variant(auth_client, admin, uuid4())

    _error(active_without_price, 422, "BUSINESS_RULE_VIOLATION")
    _error(duplicate_sku, 409, "CONFLICT")
    _error(duplicate_options, 409, "CONFLICT")
    _error(second_default, 409, "CONFLICT")
    _error(missing, 404, "NOT_FOUND")


async def test_sku_of_a_deleted_variant_is_reusable(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    product_id = await _product(auth_client, admin, created)
    sku = _sku()
    variant_id = await _variant(auth_client, admin, product_id, sku=sku, options={"size": "S"})
    deleted = await auth_client.delete(f"{VARIANTS_URL}/{variant_id}", headers=admin.headers)
    assert deleted.status_code == 204

    response = await _create_variant(auth_client, admin, product_id, sku=sku, options={"size": "S"})

    assert response.status_code == 201, response.text


async def test_update_variant(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created)
    variant_id = await _variant(
        auth_client, admin, product_id, base_price=1000, options={"size": "S"}
    )

    response = await auth_client.patch(
        f"{VARIANTS_URL}/{variant_id}",
        json={
            "is_active": True,
            "options": {"size": "M", "color": "Blue"},
            "display_order": 3,
            "base_price": 1,
            "sale_price": 1,
        },
        headers=admin.headers,
    )
    unchanged = await auth_client.patch(
        f"{VARIANTS_URL}/{variant_id}", json={"display_order": 3}, headers=admin.headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_active"] is True
    assert body["options"] == {"color": "Blue", "size": "M"}
    assert (body["base_price"], body["sale_price"]) == (1000, None)
    assert unchanged.status_code == 200
    actions = [audit.action for audit in await _audits(db_engine, variant_id)]
    assert actions == ["product_variant.created", "product_variant.updated"]


async def test_update_variant_rules(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    product_id, variant_id, _media_id = await _publishable(auth_client, admin, created)
    unpriced = await _variant(auth_client, admin, product_id, options={"size": "L"})
    other = await _variant(auth_client, admin, product_id, options={"size": "XL"})
    assert (await _set_status(auth_client, admin, product_id, "published")).status_code == 200

    activate_unpriced = await auth_client.patch(
        f"{VARIANTS_URL}/{unpriced}", json={"is_active": True}, headers=admin.headers
    )
    deactivate_last = await auth_client.patch(
        f"{VARIANTS_URL}/{variant_id}", json={"is_active": False}, headers=admin.headers
    )
    delete_last = await auth_client.delete(f"{VARIANTS_URL}/{variant_id}", headers=admin.headers)
    duplicate_options = await auth_client.patch(
        f"{VARIANTS_URL}/{other}", json={"options": {"size": "L"}}, headers=admin.headers
    )
    variants = (await _detail(auth_client, admin, product_id))["variants"]
    variant_sku = next(item["sku"] for item in variants if item["id"] == str(variant_id))
    duplicate_sku = await auth_client.patch(
        f"{VARIANTS_URL}/{other}", json={"sku": variant_sku}, headers=admin.headers
    )
    null_field = await auth_client.patch(
        f"{VARIANTS_URL}/{other}", json={"is_active": None}, headers=admin.headers
    )
    missing = await auth_client.patch(
        f"{VARIANTS_URL}/{uuid4()}", json={"is_active": False}, headers=admin.headers
    )

    _error(activate_unpriced, 422, "BUSINESS_RULE_VIOLATION")
    _error(deactivate_last, 422, "BUSINESS_RULE_VIOLATION")
    _error(delete_last, 422, "BUSINESS_RULE_VIOLATION")
    _error(duplicate_options, 409, "CONFLICT")
    _error(duplicate_sku, 409, "CONFLICT")
    _error(null_field, 400, "VALIDATION_ERROR")
    _error(missing, 404, "NOT_FOUND")


async def test_delete_variant_detaches_its_images(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created)
    variant_id = await _variant(auth_client, admin, product_id, options={"color": "Red"})
    await _media(auth_client, admin, product_id)
    tied = await _media(auth_client, admin, product_id, variant_id=str(variant_id))

    response = await auth_client.delete(f"{VARIANTS_URL}/{variant_id}", headers=admin.headers)

    assert response.status_code == 204
    detail = await _detail(auth_client, admin, product_id)
    assert detail["variants"] == []
    assert {item["id"]: item["variant_id"] for item in detail["media"]}[str(tied)] is None
    audits = await _audits(db_engine, variant_id)
    assert audits[-1].action == "product_variant.deleted"
    again = await auth_client.delete(f"{VARIANTS_URL}/{variant_id}", headers=admin.headers)
    _error(again, 404, "NOT_FOUND")


# --- media ---------------------------------------------------------------------------


async def test_upload_media_and_main_image(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created)

    first = await _upload(auth_client, admin, product_id, alt_text=" Front ")
    second = await _upload(auth_client, admin, product_id, display_order="2")
    third = await _upload(auth_client, admin, product_id, is_main="true")

    assert first.status_code == 201, first.text
    assert first.json()["is_main"] is True
    assert first.json()["alt_text"] == "Front"
    assert second.json()["is_main"] is False
    assert second.json()["display_order"] == 2
    assert third.json()["is_main"] is True
    media = (await _detail(auth_client, admin, product_id))["media"]
    assert [item["id"] for item in media if item["is_main"]] == [third.json()["id"]]
    assert len(_storage(auth_client).files) >= 3
    audits = await _audits(db_engine, UUID(third.json()["id"]))
    assert [audit.action for audit in audits] == ["product_media.created"]


async def test_upload_media_errors_keep_no_file(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    product_id = await _product(auth_client, admin, created)
    foreign = await _variant(
        auth_client, admin, await _product(auth_client, admin, created), options={"size": "S"}
    )
    files_before = set(_storage(auth_client).files)

    not_image = await _upload(auth_client, admin, product_id, b"GIF89a not an image")
    unknown_field = await _upload(auth_client, admin, product_id, caption="x")
    bad_order = await _upload(auth_client, admin, product_id, display_order="-1")
    foreign_variant = await _upload(auth_client, admin, product_id, variant_id=str(foreign))
    missing = await _upload(auth_client, admin, uuid4())

    _error(not_image, 400, "VALIDATION_ERROR")
    _error(unknown_field, 400, "VALIDATION_ERROR")
    _error(bad_order, 400, "VALIDATION_ERROR")
    _error(foreign_variant, 422, "BUSINESS_RULE_VIOLATION")
    _error(missing, 404, "NOT_FOUND")
    assert set(_storage(auth_client).files) == files_before


async def test_update_media(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created)
    variant_id = await _variant(auth_client, admin, product_id, options={"size": "S"})
    foreign = await _variant(
        auth_client, admin, await _product(auth_client, admin, created), options={"size": "S"}
    )
    main = await _media(auth_client, admin, product_id)
    other = await _media(auth_client, admin, product_id)
    url = f"{PRODUCTS_URL}/{product_id}/media"

    unset_main = await auth_client.patch(
        f"{url}/{main}", json={"is_main": False}, headers=admin.headers
    )
    foreign_variant = await auth_client.patch(
        f"{url}/{other}", json={"variant_id": str(foreign)}, headers=admin.headers
    )
    swap = await auth_client.patch(
        f"{url}/{other}",
        json={"is_main": True, "alt_text": "Side", "variant_id": str(variant_id)},
        headers=admin.headers,
    )
    unchanged = await auth_client.patch(
        f"{url}/{other}", json={"alt_text": "Side"}, headers=admin.headers
    )
    null_order = await auth_client.patch(
        f"{url}/{other}", json={"display_order": None}, headers=admin.headers
    )
    missing = await auth_client.patch(
        f"{url}/{uuid4()}", json={"alt_text": "x"}, headers=admin.headers
    )

    _error(unset_main, 422, "BUSINESS_RULE_VIOLATION")
    _error(foreign_variant, 422, "BUSINESS_RULE_VIOLATION")
    assert swap.status_code == 200, swap.text
    assert swap.json()["is_main"] is True
    assert swap.json()["variant_id"] == str(variant_id)
    assert unchanged.status_code == 200
    _error(null_order, 400, "VALIDATION_ERROR")
    _error(missing, 404, "NOT_FOUND")
    media = (await _detail(auth_client, admin, product_id))["media"]
    assert [item["id"] for item in media if item["is_main"]] == [str(other)]
    actions = [audit.action for audit in await _audits(db_engine, other)]
    assert actions == ["product_media.created", "product_media.updated"]


async def test_delete_media(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(auth_client, admin, created)
    main = await _media(auth_client, admin, product_id)
    other = await _media(auth_client, admin, product_id)
    url = f"{PRODUCTS_URL}/{product_id}/media"
    async with AsyncSession(db_engine) as session:
        other_key = await session.scalar(
            select(Media.storage_key)
            .join(ProductMedia, ProductMedia.media_id == Media.id)
            .where(ProductMedia.id == other)
        )

    main_with_others = await auth_client.delete(f"{url}/{main}", headers=admin.headers)
    removed = await auth_client.delete(f"{url}/{other}", headers=admin.headers)
    only_main = await auth_client.delete(f"{url}/{main}", headers=admin.headers)
    missing = await auth_client.delete(f"{url}/{main}", headers=admin.headers)

    _error(main_with_others, 422, "BUSINESS_RULE_VIOLATION")
    assert removed.status_code == 204
    assert other_key not in _storage(auth_client).files
    assert only_main.status_code == 204
    _error(missing, 404, "NOT_FOUND")
    assert (await _audits(db_engine, other))[-1].action == "product_media.deleted"


async def test_published_product_keeps_its_main_image(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    product_id, _variant_id, media_id = await _publishable(auth_client, admin, created)
    assert (await _set_status(auth_client, admin, product_id, "published")).status_code == 200

    response = await auth_client.delete(
        f"{PRODUCTS_URL}/{product_id}/media/{media_id}", headers=admin.headers
    )

    _error(response, 422, "BUSINESS_RULE_VIOLATION")


# --- concurrency ---------------------------------------------------------------------


async def test_publish_and_deactivating_the_last_variant_are_serialized(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    for _ in range(3):
        product_id, variant_id, _media_id = await _publishable(auth_client, admin, created)

        publish, deactivate = await asyncio.gather(
            _set_status(auth_client, admin, product_id, "published"),
            auth_client.patch(
                f"{VARIANTS_URL}/{variant_id}", json={"is_active": False}, headers=admin.headers
            ),
        )

        detail = await _detail(auth_client, admin, product_id)
        active = [item for item in detail["variants"] if item["is_active"]]
        assert not (detail["status"] == "published" and not active)
        assert {publish.status_code, deactivate.status_code} <= {200, 422}


async def test_publish_and_deleting_the_main_image_are_serialized(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    for _ in range(3):
        product_id, _variant_id, media_id = await _publishable(auth_client, admin, created)

        await asyncio.gather(
            _set_status(auth_client, admin, product_id, "published"),
            auth_client.delete(
                f"{PRODUCTS_URL}/{product_id}/media/{media_id}", headers=admin.headers
            ),
        )

        detail = await _detail(auth_client, admin, product_id)
        assert not (detail["status"] == "published" and not detail["media"])


async def test_concurrent_first_uploads_leave_one_main_image(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    product_id = await _product(auth_client, admin, created)

    responses = await asyncio.gather(*(_upload(auth_client, admin, product_id) for _ in range(3)))

    assert [response.status_code for response in responses] == [201, 201, 201]
    media = (await _detail(auth_client, admin, product_id))["media"]
    assert len([item for item in media if item["is_main"]]) == 1


async def test_category_delete_and_product_create_are_serialized(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    for _ in range(3):
        category_id = await _category(auth_client, admin, created)

        await asyncio.gather(
            auth_client.delete(f"{CATEGORIES_URL}/{category_id}", headers=admin.headers),
            _create_product(auth_client, admin, created, category_id=str(category_id)),
        )

        async with AsyncSession(db_engine) as session:
            category = await session.get(Category, category_id)
            products = await session.scalar(
                select(func.count()).where(
                    Product.category_id == category_id, Product.deleted_at.is_(None)
                )
            )
        assert category is not None
        assert not (category.deleted_at is not None and products)


# --- audit content -------------------------------------------------------------------


async def test_audit_records_before_and_after(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id = await _product(
        auth_client, admin, created, title="Old", attributes=[{"key": "k", "value": "v"}]
    )
    variant_id = await _variant(auth_client, admin, product_id, options={"color": "Red"})
    tied = await _media(auth_client, admin, product_id)
    second = await _media(auth_client, admin, product_id, variant_id=str(variant_id))

    await auth_client.patch(
        f"{PRODUCTS_URL}/{product_id}",
        json={"title": "New", "attributes": []},
        headers=admin.headers,
    )
    await auth_client.patch(
        f"{VARIANTS_URL}/{variant_id}", json={"options": {}}, headers=admin.headers
    )
    await auth_client.patch(
        f"{PRODUCTS_URL}/{product_id}/media/{second}",
        json={"is_main": True},
        headers=admin.headers,
    )
    await auth_client.delete(f"{VARIANTS_URL}/{variant_id}", headers=admin.headers)

    product_diff = (await _audits(db_engine, product_id))[-1].metadata_["diff"]
    assert product_diff["title"] == {"before": "Old", "after": "New", "changed": True}
    assert product_diff["attributes"]["after"] == []
    variant_audits = await _audits(db_engine, variant_id)
    assert variant_audits[1].metadata_["diff"]["options"] == {
        "before": {"color": "Red"},
        "after": {},
        "changed": True,
    }
    assert variant_audits[2].metadata_["diff"]["media_ids"]["before"] == [str(second)]
    swap_diff = (await _audits(db_engine, second))[-1].metadata_["diff"]
    assert swap_diff["replaced_main"]["after"] == [str(tied)]
    assert swap_diff["is_main"]["after"] is True


async def test_status_audit_records_published_at(
    auth_client: AsyncClient, admin: Account, created: Created, db_engine: AsyncEngine
) -> None:
    product_id, _variant_id, _media_id = await _publishable(auth_client, admin, created)

    published = await _set_status(auth_client, admin, product_id, "published")

    diff = (await _audits(db_engine, product_id))[-1].metadata_["diff"]
    assert diff["status"] == {"before": "draft", "after": "published", "changed": True}
    assert diff["published_at"]["after"] == published.json()["published_at"].replace("Z", "+00:00")


async def test_blank_alt_text_is_stored_as_null(
    auth_client: AsyncClient, admin: Account, created: Created
) -> None:
    product_id = await _product(auth_client, admin, created)

    response = await _upload(auth_client, admin, product_id, alt_text="   ")

    assert response.status_code == 201, response.text
    assert response.json()["alt_text"] is None
