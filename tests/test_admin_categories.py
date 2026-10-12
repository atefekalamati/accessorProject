from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    AuditLog,
    Category,
    Media,
    OtpCode,
    Product,
    ProductMedia,
    User,
    UserRole,
)
from app.db.seed import role_id
from app.modules.catalog.admin_service import MAX_CATEGORY_DEPTH

pytestmark = pytest.mark.integration

ADMIN_URL = "/api/v1/admin/categories"
PUBLIC_URL = "/api/v1/categories"
MEDIA_BASE_URL = "https://cdn.example.com/media"  # settings fixture in conftest
MakeMedia = Callable[[], Awaitable[Media]]
STRUCTURAL_FIELDS: dict[str, Any] = {
    "slug": "new-slug-value",
    "parent_id": None,
    "is_active": False,
    "icon_key": "ring",
    "seo_title": "SEO",
    "seo_description": "SEO description",
}


def _slug(prefix: str = "cat") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@dataclass(frozen=True, slots=True)
class Account:
    id: UUID
    headers: dict[str, str]


MakeAccount = Callable[..., Awaitable[Account]]


@pytest_asyncio.fixture
async def make_account(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    db_engine: AsyncEngine,
) -> AsyncIterator[MakeAccount]:
    """Log a new user in through verify-otp, then give them ``roles`` in the database."""
    mobiles: list[str] = []

    async def _make(*roles: str) -> Account:
        mobile = f"+989{uuid4().int % 1_000_000_000:09d}"
        mobiles.append(mobile)
        await issue_otp(mobile)
        response = await auth_client.post(
            "/api/v1/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
        )
        assert response.status_code == 200
        async with AsyncSession(db_engine) as session, session.begin():
            user_id: UUID = (
                await session.scalars(select(User.id).where(User.phone == mobile))
            ).one()
            await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
            session.add_all(UserRole(user_id=user_id, role_id=role_id(name)) for name in roles)
        return Account(
            id=user_id, headers={"Authorization": f"Bearer {response.json()['access_token']}"}
        )

    yield _make
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone.in_(mobiles)))


@pytest_asyncio.fixture
async def created(db_engine: AsyncEngine) -> AsyncIterator[list[UUID]]:
    """Ids of categories made by a test; removed with their products afterwards."""
    ids: list[UUID] = []
    yield ids
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(Product).where(Product.category_id.in_(ids)))
        await session.execute(update(Category).where(Category.id.in_(ids)).values(parent_id=None))
        await session.execute(delete(Category).where(Category.id.in_(ids)))


@pytest_asyncio.fixture
async def admin(make_account: MakeAccount) -> Account:
    return await make_account("admin")


@pytest_asyncio.fixture
async def editor(make_account: MakeAccount) -> Account:
    return await make_account("content_manager")


async def _create(
    client: AsyncClient, actor: Account, created: list[UUID], **fields: Any
) -> Response:
    body = {"title": "Category", "slug": _slug(), **fields}
    body = {key: str(value) if isinstance(value, UUID) else value for key, value in body.items()}
    response = await client.post(ADMIN_URL, json=body, headers=actor.headers)
    if response.status_code == 201:
        created.append(UUID(response.json()["id"]))
    return response


async def _new(client: AsyncClient, actor: Account, created: list[UUID], **fields: Any) -> UUID:
    response = await _create(client, actor, created, **fields)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def _chain(
    client: AsyncClient, actor: Account, created: list[UUID], length: int
) -> list[UUID]:
    ids: list[UUID] = []
    for _ in range(length):
        ids.append(await _new(client, actor, created, parent_id=ids[-1] if ids else None))
    return ids


async def _patch(client: AsyncClient, actor: Account, category_id: UUID, **body: Any) -> Response:
    payload = {key: str(value) if isinstance(value, UUID) else value for key, value in body.items()}
    return await client.patch(f"{ADMIN_URL}/{category_id}", json=payload, headers=actor.headers)


async def _audits(db_engine: AsyncEngine, category_id: UUID) -> list[AuditLog]:
    async with AsyncSession(db_engine) as session:
        statement = (
            select(AuditLog)
            .where(AuditLog.entity_type == "category", AuditLog.entity_id == category_id)
            .order_by(AuditLog.created_at)
        )
        return list((await session.scalars(statement)).all())


async def _category(db_engine: AsyncEngine, category_id: UUID) -> Category:
    async with AsyncSession(db_engine) as session:
        return (await session.scalars(select(Category).where(Category.id == category_id))).one()


def _error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


# --- authorization -------------------------------------------------------------------


async def test_every_endpoint_requires_authentication(auth_client: AsyncClient) -> None:
    target = f"{ADMIN_URL}/{uuid4()}"
    responses = [
        await auth_client.get(ADMIN_URL),
        await auth_client.post(ADMIN_URL, json={}),
        await auth_client.patch(target, json={}),
        await auth_client.delete(target),
    ]
    for response in responses:
        _error(response, 401, "UNAUTHORIZED")


@pytest.mark.parametrize("roles", [(), ("customer",), ("support",)])
async def test_roles_without_category_permissions_get_403(
    auth_client: AsyncClient, make_account: MakeAccount, roles: tuple[str, ...]
) -> None:
    actor = await make_account(*roles)
    target = f"{ADMIN_URL}/{uuid4()}"
    responses = [
        await auth_client.get(ADMIN_URL, headers=actor.headers),
        await auth_client.post(ADMIN_URL, json={}, headers=actor.headers),
        await auth_client.patch(target, json={"title": "x"}, headers=actor.headers),
        await auth_client.delete(target, headers=actor.headers),
    ]
    for response in responses:
        _error(response, 403, "FORBIDDEN")


async def test_content_manager_cannot_create_or_delete(
    auth_client: AsyncClient,
    db_engine: AsyncEngine,
    admin: Account,
    editor: Account,
    created: list[UUID],
) -> None:
    category_id = await _new(auth_client, admin, created)

    _error(await _create(auth_client, editor, created), 403, "FORBIDDEN")
    response = await auth_client.delete(f"{ADMIN_URL}/{category_id}", headers=editor.headers)
    _error(response, 403, "FORBIDDEN")
    assert (await _category(db_engine, category_id)).deleted_at is None


async def test_content_manager_edits_content_fields(
    auth_client: AsyncClient,
    admin: Account,
    editor: Account,
    created: list[UUID],
    make_media: MakeMedia,
) -> None:
    category_id = await _new(auth_client, admin, created)
    banner = await make_media()

    list_response = await auth_client.get(ADMIN_URL, headers=editor.headers)
    response = await _patch(
        auth_client,
        editor,
        category_id,
        title="Rings",
        description="All rings",
        image_media_id=banner.id,
        display_order=7,
    )

    assert list_response.status_code == 200
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["title"], body["description"], body["display_order"]) == ("Rings", "All rings", 7)
    assert body["image_media_id"] == str(banner.id)
    assert body["image_url"] == f"{MEDIA_BASE_URL}/{banner.storage_key}"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("field", sorted(STRUCTURAL_FIELDS))
async def test_content_manager_cannot_send_structural_fields(
    auth_client: AsyncClient,
    db_engine: AsyncEngine,
    admin: Account,
    editor: Account,
    created: list[UUID],
    field: str,
) -> None:
    category_id = await _new(auth_client, admin, created)
    before = await _category(db_engine, category_id)

    response = await _patch(
        auth_client, editor, category_id, title="Changed", **{field: STRUCTURAL_FIELDS[field]}
    )

    _error(response, 403, "FORBIDDEN")
    after = await _category(db_engine, category_id)
    assert (after.title, after.slug, after.updated_at) == (
        before.title,
        before.slug,
        before.updated_at,
    )
    assert len(await _audits(db_engine, category_id)) == 1


# --- create --------------------------------------------------------------------------


async def test_admin_creates_category_with_audit(
    auth_client: AsyncClient,
    db_engine: AsyncEngine,
    admin: Account,
    created: list[UUID],
    make_media: MakeMedia,
) -> None:
    banner = await make_media()
    parent_id = await _new(auth_client, admin, created)
    slug = _slug()

    response = await _create(
        auth_client,
        admin,
        created,
        title="  Hair  ",
        slug=slug,
        parent_id=parent_id,
        image_media_id=banner.id,
        display_order=3,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Hair"
    assert body["parent_id"] == str(parent_id)
    assert body["is_active"] is True
    assert response.headers["cache-control"] == "no-store"
    audits = await _audits(db_engine, UUID(body["id"]))
    assert [audit.action for audit in audits] == ["category.created"]
    assert audits[0].actor_user_id == admin.id
    assert audits[0].metadata_["diff"]["slug"] == {"before": None, "after": slug, "changed": True}
    public = await auth_client.get(f"{PUBLIC_URL}/{slug}")
    assert public.status_code == 200
    assert (
        public.json()["image_url"] == body["image_url"] == f"{MEDIA_BASE_URL}/{banner.storage_key}"
    )


async def test_duplicate_slug_is_409(
    auth_client: AsyncClient, admin: Account, created: list[UUID]
) -> None:
    slug = _slug()
    await _new(auth_client, admin, created, slug=slug)
    other_id = await _new(auth_client, admin, created)

    _error(await _create(auth_client, admin, created, slug=slug), 409, "DUPLICATE_SLUG")
    _error(await _patch(auth_client, admin, other_id, slug=slug), 409, "DUPLICATE_SLUG")


async def test_slug_of_deleted_category_can_be_reused(
    auth_client: AsyncClient, admin: Account, created: list[UUID]
) -> None:
    slug = _slug()
    category_id = await _new(auth_client, admin, created, slug=slug)
    await auth_client.delete(f"{ADMIN_URL}/{category_id}", headers=admin.headers)

    assert (await _create(auth_client, admin, created, slug=slug)).status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        {"title": "   "},
        {"slug": "Bad Slug"},
        {"display_order": -1},
        {"unknown": 1},
        {"price": 1000},
        {"parent_id": "not-a-uuid"},
    ],
)
async def test_invalid_create_body_is_400(
    auth_client: AsyncClient, admin: Account, created: list[UUID], body: dict[str, Any]
) -> None:
    _error(await _create(auth_client, admin, created, **body), 400, "VALIDATION_ERROR")


@pytest.mark.parametrize("deleted", [False, True])
async def test_missing_or_deleted_parent_is_422(
    auth_client: AsyncClient, admin: Account, created: list[UUID], deleted: bool
) -> None:
    parent_id = uuid4()
    if deleted:
        parent_id = await _new(auth_client, admin, created)
        await auth_client.delete(f"{ADMIN_URL}/{parent_id}", headers=admin.headers)

    response = await _create(auth_client, admin, created, parent_id=parent_id)

    _error(response, 422, "BUSINESS_RULE_VIOLATION")


# --- image_media_id ------------------------------------------------------------------


async def test_unknown_image_media_is_422(
    auth_client: AsyncClient,
    db_engine: AsyncEngine,
    admin: Account,
    editor: Account,
    created: list[UUID],
) -> None:
    category_id = await _new(auth_client, admin, created)

    create = await _create(auth_client, admin, created, image_media_id=uuid4())
    patch = await _patch(auth_client, editor, category_id, image_media_id=uuid4())

    for response in (create, patch):
        _error(response, 422, "BUSINESS_RULE_VIOLATION")
    assert (await _category(db_engine, category_id)).image_media_id is None


async def test_product_image_cannot_be_a_category_banner(
    auth_client: AsyncClient,
    db_engine: AsyncEngine,
    admin: Account,
    created: list[UUID],
    make_media: MakeMedia,
) -> None:
    owner = await _new(auth_client, admin, created)
    media = await make_media()
    async with AsyncSession(db_engine, expire_on_commit=False) as session, session.begin():
        product = Product(category_id=owner, title="Ring", slug=_slug("prd"))
        session.add(product)
        await session.flush()
        session.add(ProductMedia(product_id=product.id, media_id=media.id, is_main=True))
    try:
        response = await _create(auth_client, admin, created, image_media_id=media.id)

        _error(response, 422, "BUSINESS_RULE_VIOLATION")
    finally:
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(ProductMedia).where(ProductMedia.media_id == media.id))


@pytest.mark.parametrize("value", ["https://cdn.example.com/a.webp", "not-a-uuid"])
async def test_image_url_input_is_gone(
    auth_client: AsyncClient, admin: Account, created: list[UUID], value: str
) -> None:
    category_id = await _new(auth_client, admin, created)

    _error(await _patch(auth_client, admin, category_id, image_url=value), 400, "VALIDATION_ERROR")
    response = await _patch(auth_client, admin, category_id, image_media_id=value)
    _error(response, 400, "VALIDATION_ERROR")


async def test_image_can_be_cleared(
    auth_client: AsyncClient, admin: Account, created: list[UUID], make_media: MakeMedia
) -> None:
    banner = await make_media()
    category_id = await _new(auth_client, admin, created, image_media_id=banner.id)

    response = await _patch(auth_client, admin, category_id, image_media_id=None)

    assert response.status_code == 200
    assert response.json()["image_url"] is None
    assert response.json()["image_media_id"] is None


# --- update --------------------------------------------------------------------------


async def test_update_audits_only_changed_fields(
    auth_client: AsyncClient, db_engine: AsyncEngine, admin: Account, created: list[UUID]
) -> None:
    category_id = await _new(auth_client, admin, created, title="Old")

    response = await _patch(auth_client, admin, category_id, title="New", display_order=0)
    unchanged = await _patch(auth_client, admin, category_id, title="New")

    assert response.status_code == 200 and unchanged.status_code == 200
    audits = await _audits(db_engine, category_id)
    assert [audit.action for audit in audits] == ["category.created", "category.updated"]
    assert audits[1].metadata_["diff"] == {
        "title": {"before": "Old", "after": "New", "changed": True}
    }


@pytest.mark.parametrize("body", [{}, {"title": None}, {"is_active": None}, {"slug": None}])
async def test_invalid_patch_body_is_400(
    auth_client: AsyncClient, admin: Account, created: list[UUID], body: dict[str, Any]
) -> None:
    category_id = await _new(auth_client, admin, created)

    _error(await _patch(auth_client, admin, category_id, **body), 400, "VALIDATION_ERROR")


async def test_patch_unknown_or_deleted_category_is_404(
    auth_client: AsyncClient, admin: Account, created: list[UUID]
) -> None:
    category_id = await _new(auth_client, admin, created)
    await auth_client.delete(f"{ADMIN_URL}/{category_id}", headers=admin.headers)

    for target in (uuid4(), category_id):
        _error(await _patch(auth_client, admin, target, title="x"), 404, "NOT_FOUND")


async def test_deactivating_hides_category_and_subtree_from_public_api(
    auth_client: AsyncClient, admin: Account, created: list[UUID]
) -> None:
    root_slug, child_slug = _slug(), _slug()
    root_id = await _new(auth_client, admin, created, slug=root_slug)
    await _new(auth_client, admin, created, slug=child_slug, parent_id=root_id)

    response = await _patch(auth_client, admin, root_id, is_active=False)

    assert response.status_code == 200
    for slug in (root_slug, child_slug):
        _error(await auth_client.get(f"{PUBLIC_URL}/{slug}"), 404, "NOT_FOUND")


# --- tree rules ----------------------------------------------------------------------


async def test_cycles_are_409(
    auth_client: AsyncClient, admin: Account, created: list[UUID]
) -> None:
    root, child, grandchild = await _chain(auth_client, admin, created, 3)

    _error(await _patch(auth_client, admin, root, parent_id=root), 409, "CONFLICT")
    _error(await _patch(auth_client, admin, root, parent_id=grandchild), 409, "CONFLICT")
    _error(await _patch(auth_client, admin, child, parent_id=grandchild), 409, "CONFLICT")


async def test_move_reparents_subtree(
    auth_client: AsyncClient, admin: Account, created: list[UUID]
) -> None:
    _root, child = await _chain(auth_client, admin, created, 2)
    other = await _new(auth_client, admin, created)

    moved = await _patch(auth_client, admin, child, parent_id=other)
    to_root = await _patch(auth_client, admin, child, parent_id=None)

    assert moved.json()["parent_id"] == str(other)
    assert to_root.json()["parent_id"] is None


async def test_depth_limit_on_create_is_422(
    auth_client: AsyncClient, admin: Account, created: list[UUID]
) -> None:
    chain = await _chain(auth_client, admin, created, MAX_CATEGORY_DEPTH)

    response = await _create(auth_client, admin, created, parent_id=chain[-1])

    _error(response, 422, "BUSINESS_RULE_VIOLATION")


async def test_depth_limit_counts_moved_subtree(
    auth_client: AsyncClient, admin: Account, created: list[UUID]
) -> None:
    deep = await _chain(auth_client, admin, created, MAX_CATEGORY_DEPTH - 1)
    subtree = await _chain(auth_client, admin, created, 2)

    too_deep = await _patch(auth_client, admin, subtree[0], parent_id=deep[-1])
    fits = await _patch(auth_client, admin, subtree[0], parent_id=deep[-2])

    _error(too_deep, 422, "BUSINESS_RULE_VIOLATION")
    assert fits.status_code == 200, fits.text


async def test_concurrent_cross_moves_cannot_create_a_cycle(
    auth_client: AsyncClient, db_engine: AsyncEngine, admin: Account, created: list[UUID]
) -> None:
    first = await _new(auth_client, admin, created)
    second = await _new(auth_client, admin, created)

    responses = await asyncio.gather(
        _patch(auth_client, admin, first, parent_id=second),
        _patch(auth_client, admin, second, parent_id=first),
    )

    assert sorted(response.status_code for response in responses) == [200, 409]
    parents = {
        (await _category(db_engine, first)).parent_id,
        (await _category(db_engine, second)).parent_id,
    }
    assert None in parents


# --- delete --------------------------------------------------------------------------


async def test_delete_soft_deletes_with_audit(
    auth_client: AsyncClient, db_engine: AsyncEngine, admin: Account, created: list[UUID]
) -> None:
    slug = _slug()
    category_id = await _new(auth_client, admin, created, slug=slug)

    response = await auth_client.delete(f"{ADMIN_URL}/{category_id}", headers=admin.headers)
    again = await auth_client.delete(f"{ADMIN_URL}/{category_id}", headers=admin.headers)

    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    _error(again, 404, "NOT_FOUND")
    assert (await _category(db_engine, category_id)).deleted_at is not None
    audits = await _audits(db_engine, category_id)
    assert [audit.action for audit in audits] == ["category.created", "category.deleted"]
    assert audits[1].metadata_["diff"]["slug"] == {"before": slug, "after": None, "changed": True}
    _error(await auth_client.get(f"{PUBLIC_URL}/{slug}"), 404, "NOT_FOUND")


async def test_delete_with_children_or_products_is_409(
    auth_client: AsyncClient, db_engine: AsyncEngine, admin: Account, created: list[UUID]
) -> None:
    parent, _child = await _chain(auth_client, admin, created, 2)
    with_product = await _new(auth_client, admin, created)
    async with AsyncSession(db_engine) as session, session.begin():
        session.add(Product(category_id=with_product, title="Ring", slug=_slug("prd")))

    for target in (parent, with_product):
        response = await auth_client.delete(f"{ADMIN_URL}/{target}", headers=admin.headers)
        _error(response, 409, "CONFLICT")
        assert (await _category(db_engine, target)).deleted_at is None


# --- list ----------------------------------------------------------------------------


async def test_list_includes_inactive_and_excludes_deleted(
    auth_client: AsyncClient, admin: Account, created: list[UUID]
) -> None:
    inactive = await _new(auth_client, admin, created, is_active=False)
    deleted = await _new(auth_client, admin, created)
    await auth_client.delete(f"{ADMIN_URL}/{deleted}", headers=admin.headers)

    response = await auth_client.get(
        ADMIN_URL, params={"sort": "newest", "limit": 100}, headers=admin.headers
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    ids = {item["id"] for item in response.json()["items"]}
    assert str(inactive) in ids and str(deleted) not in ids


@pytest.mark.parametrize("params", [{"sort": "price"}, {"limit": 1000}, {"parent": "x"}])
async def test_invalid_list_query_is_400(
    auth_client: AsyncClient, admin: Account, params: dict[str, Any]
) -> None:
    response = await auth_client.get(ADMIN_URL, params=params, headers=admin.headers)

    _error(response, 400, "VALIDATION_ERROR")
