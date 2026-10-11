"""Admin product, variant and product-media writes (CAT-11, PRD «محصولات» ✓, ADR-030).

Every write locks the Product row first (``SELECT ... FOR UPDATE``) and checks the publish
invariants after the lock, so a publish cannot race the removal of the last active
variant or the main image. Every change is audited in the same transaction.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Final
from uuid import UUID

import anyio
from sqlalchemy import UnaryExpression
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
)
from app.core.time import utc_now
from app.db.models import (
    Media,
    Product,
    ProductAttribute,
    ProductMedia,
    ProductStatus,
    ProductVariant,
)
from app.modules.auth.service import CurrentUser
from app.modules.catalog.admin_product_schemas import (
    PRICE_FIELDS,
    AdminProductListItem,
    AdminProductMediaResponse,
    AdminProductResponse,
    AdminVariantResponse,
    AttributeItem,
    CategoryRef,
    ChangeProductStatusRequest,
    CreateProductRequest,
    CreateVariantRequest,
    PriceRange,
    ProductMediaFields,
    StockResponse,
    UpdateProductMediaRequest,
    UpdateProductRequest,
    UpdateVariantRequest,
)
from app.modules.catalog.product_repository import ProductFilters, ProductRepository
from app.modules.inventory.stock import free_quantity, stock_status, variant_level
from app.shared.audit import record_audit
from app.shared.media import process_image_async
from app.shared.pagination import Page, PageParams
from app.shared.storage import FileStorage, new_storage_key

logger = logging.getLogger("app.catalog")

MANAGE_PERMISSION: Final = "catalog:manage"
PRICING_PERMISSION: Final = "pricing:update"

_DRAFT, _PUBLISHED, _ARCHIVED = (
    ProductStatus.DRAFT.value,
    ProductStatus.PUBLISHED.value,
    ProductStatus.ARCHIVED.value,
)
ALLOWED_TRANSITIONS: Final = frozenset(
    {
        (_DRAFT, _PUBLISHED),
        (_PUBLISHED, _DRAFT),
        (_PUBLISHED, _ARCHIVED),
        (_DRAFT, _ARCHIVED),
        (_ARCHIVED, _DRAFT),
    }
)

BLOCKER_CATEGORY: Final = "category_missing"
BLOCKER_VARIANT: Final = "no_active_priced_variant"
BLOCKER_MAIN_IMAGE: Final = "no_main_image"
_BLOCKER_MESSAGES: Final = {
    BLOCKER_CATEGORY: "The product's category does not exist or is deleted",
    BLOCKER_VARIANT: "The product needs an active variant with a base price",
    BLOCKER_MAIN_IMAGE: "The product needs a main image",
}

_PRODUCT_FIELDS: Final = (
    "title",
    "slug",
    "category_id",
    "description",
    "status",
    "published_at",
    "is_featured",
)
_VARIANT_FIELDS: Final = (
    "sku",
    "display_order",
    "is_active",
    "is_purchasable",
    "base_price",
    "sale_price",
    "sale_start_at",
    "sale_end_at",
)
_MEDIA_FIELDS: Final = ("variant_id", "alt_text", "display_order", "is_main")


def _product_not_found() -> NotFoundError:
    return NotFoundError(message="Product not found")


def _variant_not_found() -> NotFoundError:
    return NotFoundError(message="Product variant not found")


def _media_not_found() -> NotFoundError:
    return NotFoundError(message="Product media not found")


def _duplicate_slug() -> ConflictError:
    return ConflictError(code=ErrorCode.DUPLICATE_SLUG, message="Slug is already in use")


def _duplicate_sku() -> ConflictError:
    return ConflictError(message="SKU is already in use")


def _last_active_variant() -> BusinessRuleError:
    return BusinessRuleError(message="A published product must keep at least one active variant")


def _product_snapshot(product: Product, attributes: Sequence[AttributeItem]) -> dict[str, Any]:
    snapshot = {field: getattr(product, field) for field in _PRODUCT_FIELDS}
    snapshot["attributes"] = [item.model_dump() for item in attributes]
    return snapshot


def _variant_snapshot(variant: ProductVariant, options: dict[str, str]) -> dict[str, Any]:
    snapshot = {field: getattr(variant, field) for field in _VARIANT_FIELDS}
    snapshot["options"] = dict(sorted(options.items()))
    return snapshot


def _media_snapshot(product_media: ProductMedia, media: Media) -> dict[str, Any]:
    snapshot = {field: getattr(product_media, field) for field in _MEDIA_FIELDS}
    snapshot["media_id"] = media.id
    snapshot["storage_key"] = media.storage_key
    return snapshot


def _attribute_items(attributes: Sequence[ProductAttribute]) -> list[AttributeItem]:
    return [
        AttributeItem(key=item.attribute_key, value=item.attribute_value) for item in attributes
    ]


def _attribute_rows(product_id: UUID, items: Sequence[AttributeItem]) -> list[ProductAttribute]:
    return [
        ProductAttribute(
            product_id=product_id,
            attribute_key=item.key,
            attribute_value=item.value,
            display_order=index,
        )
        for index, item in enumerate(items)
    ]


class AdminProductService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ProductRepository,
        storage: FileStorage,
    ) -> None:
        self._session = session
        self._repository = repository
        self._storage = storage

    # --- reads -------------------------------------------------------------------------

    async def list_products(
        self,
        filters: ProductFilters,
        order_by: Sequence[UnaryExpression[Any]],
        paging: PageParams,
    ) -> Page[AdminProductListItem]:
        async with self._session.begin():
            products, total = await self._repository.list_page(
                filters, order_by, offset=paging.offset, limit=paging.limit
            )
            ids = [product.id for product in products]
            summaries = await self._repository.variant_summaries(ids)
            images = await self._repository.main_image_keys(ids)
            categories = await self._repository.categories(
                {product.category_id for product in products}
            )
        items = []
        for product in products:
            summary = summaries.get(product.id)
            category = categories.get(product.category_id)
            price_range = (
                None
                if summary is None or summary.min_price is None or summary.max_price is None
                else PriceRange(min=summary.min_price, max=summary.max_price)
            )
            items.append(
                AdminProductListItem(
                    id=product.id,
                    title=product.title,
                    slug=product.slug,
                    status=product.status,
                    category=None
                    if category is None
                    else CategoryRef(id=category.id, title=category.title),
                    active_variant_count=0 if summary is None else summary.active_count,
                    price_range=price_range,
                    main_image_url=None
                    if product.id not in images
                    else self._storage.url(images[product.id]),
                    updated_at=product.updated_at,
                )
            )
        return Page.build(items, total=total, params=paging)

    async def get_product(self, product_id: UUID) -> AdminProductResponse:
        async with self._session.begin():
            product = await self._repository.get(product_id)
            if product is None:
                raise _product_not_found()
            return await self._detail(product)

    async def _detail(self, product: Product) -> AdminProductResponse:
        attributes = await self._repository.attributes_of(product.id)
        variants = await self._repository.variants_of(product.id)
        variant_ids = [variant.id for variant in variants]
        options = await self._repository.options_of(variant_ids)
        inventory = await self._repository.inventory_of(variant_ids)
        media = await self._repository.media_of(product.id)
        return AdminProductResponse(
            id=product.id,
            title=product.title,
            slug=product.slug,
            category_id=product.category_id,
            description=product.description,
            status=product.status,
            published_at=product.published_at,
            is_featured=product.is_featured,
            attributes=_attribute_items(attributes),
            variants=[
                self._variant_response(variant, options[variant.id], inventory[variant.id])
                for variant in variants
            ],
            media=[self._media_response(item, stored) for item, stored in media],
            publish_blockers=await self._blockers(product),
            created_by=product.created_by,
            updated_by=product.updated_by,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )

    def _variant_response(
        self, variant: ProductVariant, options: dict[str, str], items: Sequence[Any]
    ) -> AdminVariantResponse:
        level = variant_level(items)
        return AdminVariantResponse(
            id=variant.id,
            product_id=variant.product_id,
            sku=variant.sku,
            options=options,
            display_order=variant.display_order,
            is_active=variant.is_active,
            is_purchasable=variant.is_purchasable,
            base_price=variant.base_price,
            sale_price=variant.sale_price,
            sale_start_at=variant.sale_start_at,
            sale_end_at=variant.sale_end_at,
            tax_enabled=variant.tax_enabled,
            price_version=variant.price_version,
            stock=StockResponse(
                total=0 if level is None else level.total,
                reserved=0 if level is None else level.reserved,
                free=free_quantity(level),
                low_stock_threshold=0 if level is None else level.low_stock_threshold,
                status=stock_status(level),
            ),
            created_at=variant.created_at,
            updated_at=variant.updated_at,
        )

    def _media_response(self, item: ProductMedia, media: Media) -> AdminProductMediaResponse:
        return AdminProductMediaResponse(
            id=item.id,
            media_id=media.id,
            url=self._storage.url(media.storage_key),
            variant_id=item.variant_id,
            alt_text=item.alt_text,
            display_order=item.display_order,
            is_main=item.is_main,
            width=media.width,
            height=media.height,
            created_at=item.created_at,
        )

    async def _blockers(self, product: Product, *, lock_category: bool = False) -> list[str]:
        blockers = []
        category_ok = (
            await self._repository.lock_category(product.category_id)
            if lock_category
            else await self._repository.category_exists(product.category_id)
        )
        if not category_ok:
            blockers.append(BLOCKER_CATEGORY)
        if not await self._repository.has_active_priced_variant(product.id):
            blockers.append(BLOCKER_VARIANT)
        if not await self._repository.has_main_image(product.id):
            blockers.append(BLOCKER_MAIN_IMAGE)
        return blockers

    # --- products ----------------------------------------------------------------------

    async def create_product(
        self, actor: CurrentUser, payload: CreateProductRequest, audit_request: Request | None
    ) -> AdminProductResponse:
        async with self._session.begin():
            if not await self._repository.lock_category(payload.category_id):
                raise NotFoundError(message="Category not found")
            if await self._repository.slug_taken(payload.slug):
                raise _duplicate_slug()
            # Always a draft: status and other system fields never come from the client.
            product = Product(
                title=payload.title,
                slug=payload.slug,
                category_id=payload.category_id,
                description=payload.description,
                is_featured=payload.is_featured,
                status=ProductStatus.DRAFT,
                created_by=actor.id,
                updated_by=actor.id,
            )
            self._session.add(product)
            await self._flush_product()
            self._session.add_all(_attribute_rows(product.id, payload.attributes))
            await self._session.flush()
            await self._audit(
                actor,
                "product.created",
                "product",
                product.id,
                None,
                _product_snapshot(product, payload.attributes),
                audit_request,
            )
            response = await self._detail(product)
        logger.info("product.created", extra={"product_id": str(product.id)})
        return response

    async def update_product(
        self,
        actor: CurrentUser,
        product_id: UUID,
        payload: UpdateProductRequest,
        audit_request: Request | None,
    ) -> AdminProductResponse:
        async with self._session.begin():
            product = await self._repository.lock(product_id)
            if product is None:
                raise _product_not_found()
            attributes = _attribute_items(await self._repository.attributes_of(product.id))
            fields = payload.model_fields_set
            changes = {
                field: getattr(payload, field)
                for field in sorted(fields - {"attributes"})
                if getattr(payload, field) != getattr(product, field)
            }
            new_attributes = payload.attributes if "attributes" in fields else None
            if new_attributes == attributes:
                new_attributes = None
            if not changes and new_attributes is None:
                return await self._detail(product)
            if "category_id" in changes and not await self._repository.lock_category(
                changes["category_id"]
            ):
                raise NotFoundError(message="Category not found")
            if "slug" in changes and await self._repository.slug_taken(
                changes["slug"], exclude_id=product.id
            ):
                raise _duplicate_slug()

            before = _product_snapshot(product, attributes)
            for field, value in changes.items():
                setattr(product, field, value)
            product.updated_by = actor.id
            await self._flush_product()
            if new_attributes is not None:
                await self._repository.replace_attributes(
                    product.id, _attribute_rows(product.id, new_attributes)
                )
            await self._audit(
                actor,
                "product.updated",
                "product",
                product.id,
                before,
                _product_snapshot(
                    product, attributes if new_attributes is None else new_attributes
                ),
                audit_request,
            )
            response = await self._detail(product)
        logger.info("product.updated", extra={"product_id": str(product.id)})
        return response

    async def change_status(
        self,
        actor: CurrentUser,
        product_id: UUID,
        payload: ChangeProductStatusRequest,
        audit_request: Request | None,
    ) -> AdminProductResponse:
        target = payload.status.value
        async with self._session.begin():
            product = await self._repository.lock(product_id)
            if product is None:
                raise _product_not_found()
            if product.status == target:
                return await self._detail(product)
            if (product.status, target) not in ALLOWED_TRANSITIONS:
                raise BusinessRuleError(
                    code=ErrorCode.INVALID_STATE_TRANSITION,
                    message=f"Cannot change status from {product.status} to {target}",
                )
            if target == _PUBLISHED:
                # Checked after the lock: concurrent variant/media writes wait for it.
                blockers = await self._blockers(product, lock_category=True)
                if blockers:
                    raise BusinessRuleError(
                        message="The product cannot be published",
                        details=[
                            {"code": blocker, "message": _BLOCKER_MESSAGES[blocker]}
                            for blocker in blockers
                        ],
                    )
            before = {"status": product.status, "published_at": product.published_at}
            product.status = target
            if target == _PUBLISHED and product.published_at is None:
                product.published_at = utc_now()
            product.updated_by = actor.id
            await self._session.flush()
            await self._audit(
                actor,
                "product.status_changed",
                "product",
                product.id,
                before,
                {"status": product.status, "published_at": product.published_at},
                audit_request,
            )
            response = await self._detail(product)
        logger.info(
            "product.status_changed", extra={"product_id": str(product.id), "status": target}
        )
        return response

    async def delete_product(
        self, actor: CurrentUser, product_id: UUID, audit_request: Request | None
    ) -> None:
        """Soft delete the product and all its variants (SD rule); media and files stay."""
        async with self._session.begin():
            product = await self._repository.lock(product_id)
            if product is None:
                raise _product_not_found()
            attributes = _attribute_items(await self._repository.attributes_of(product.id))
            before = _product_snapshot(product, attributes)
            variant_ids = await self._repository.soft_delete_variants(product.id)
            before["variant_ids"] = sorted(str(variant_id) for variant_id in variant_ids)
            product.soft_delete()
            product.updated_by = actor.id
            await self._session.flush()
            await self._audit(
                actor, "product.deleted", "product", product.id, before, None, audit_request
            )
        logger.info("product.deleted", extra={"product_id": str(product.id)})

    # --- variants ----------------------------------------------------------------------

    async def create_variant(
        self,
        actor: CurrentUser,
        product_id: UUID,
        payload: CreateVariantRequest,
        audit_request: Request | None,
    ) -> AdminVariantResponse:
        # Checked on the fields sent, even as null (ADR-025, ADR-030).
        if payload.model_fields_set & PRICE_FIELDS and PRICING_PERMISSION not in actor.permissions:
            raise ForbiddenError(message="Setting a price requires pricing:update")
        options = payload.options.as_dict()
        async with self._session.begin():
            product = await self._repository.lock(product_id)
            if product is None:
                raise _product_not_found()
            if payload.is_active and payload.base_price is None:
                raise BusinessRuleError(message="An active variant needs a base price")
            if await self._repository.sku_taken(payload.sku):
                raise _duplicate_sku()
            await self._check_combination(product.id, options, exclude_id=None)
            variant = ProductVariant(
                product_id=product.id,
                sku=payload.sku,
                display_order=payload.display_order,
                is_active=payload.is_active,
                is_purchasable=payload.is_purchasable,
                base_price=payload.base_price,
                sale_price=payload.sale_price,
                sale_start_at=payload.sale_start_at,
                sale_end_at=payload.sale_end_at,
            )
            self._session.add(variant)
            await self._flush_variant()
            await self._repository.replace_options(variant.id, options)
            await self._audit(
                actor,
                "product_variant.created",
                "product_variant",
                variant.id,
                None,
                _variant_snapshot(variant, options),
                audit_request,
            )
            response = await self._variant_detail(variant)
        logger.info("product_variant.created", extra={"variant_id": str(variant.id)})
        return response

    async def update_variant(
        self,
        actor: CurrentUser,
        variant_id: UUID,
        payload: UpdateVariantRequest,
        audit_request: Request | None,
    ) -> AdminVariantResponse:
        async with self._session.begin():
            product, variant = await self._lock_variant(variant_id)
            current_options = (await self._repository.options_of([variant.id]))[variant.id]
            fields = payload.model_fields_set
            changes = {
                field: getattr(payload, field)
                for field in sorted(fields - {"options"})
                if getattr(payload, field) != getattr(variant, field)
            }
            new_options = None if payload.options is None else payload.options.as_dict()
            if new_options == current_options:
                new_options = None
            if not changes and new_options is None:
                return await self._variant_detail(variant)
            if changes.get("is_active") is True and variant.base_price is None:
                raise BusinessRuleError(message="An active variant needs a base price")
            if changes.get("is_active") is False:
                await self._check_keeps_active_variant(product, variant)
            if "sku" in changes and await self._repository.sku_taken(
                changes["sku"], exclude_id=variant.id
            ):
                raise _duplicate_sku()
            if new_options is not None:
                await self._check_combination(product.id, new_options, exclude_id=variant.id)

            before = _variant_snapshot(variant, current_options)
            for field, value in changes.items():
                setattr(variant, field, value)
            await self._flush_variant()
            if new_options is not None:
                await self._repository.replace_options(variant.id, new_options)
            await self._audit(
                actor,
                "product_variant.updated",
                "product_variant",
                variant.id,
                before,
                _variant_snapshot(variant, current_options if new_options is None else new_options),
                audit_request,
            )
            response = await self._variant_detail(variant)
        logger.info("product_variant.updated", extra={"variant_id": str(variant.id)})
        return response

    async def delete_variant(
        self, actor: CurrentUser, variant_id: UUID, audit_request: Request | None
    ) -> None:
        async with self._session.begin():
            product, variant = await self._lock_variant(variant_id)
            if variant.is_active:
                await self._check_keeps_active_variant(product, variant)
            options = (await self._repository.options_of([variant.id]))[variant.id]
            before = _variant_snapshot(variant, options)
            variant.soft_delete()
            detached = await self._repository.detach_media(variant.id)
            before["media_ids"] = sorted(str(media_id) for media_id in detached)
            await self._session.flush()
            await self._audit(
                actor,
                "product_variant.deleted",
                "product_variant",
                variant.id,
                before,
                None,
                audit_request,
            )
        logger.info("product_variant.deleted", extra={"variant_id": str(variant.id)})

    async def _lock_variant(self, variant_id: UUID) -> tuple[Product, ProductVariant]:
        """Lock the variant's product first (same lock order as every other write)."""
        product_id = await self._repository.variant_product_id(variant_id)
        if product_id is None:
            raise _variant_not_found()
        product = await self._repository.lock(product_id)
        variant = await self._repository.get_variant(variant_id)
        if product is None or variant is None:
            raise _variant_not_found()
        return product, variant

    async def _check_keeps_active_variant(self, product: Product, variant: ProductVariant) -> None:
        if product.status != _PUBLISHED:
            return
        if await self._repository.active_variant_count(product.id, excluding=variant.id) == 0:
            raise _last_active_variant()

    async def _check_combination(
        self, product_id: UUID, options: dict[str, str], *, exclude_id: UUID | None
    ) -> None:
        """Option combinations are unique among the product's variants (one default variant)."""
        others = [
            variant.id
            for variant in await self._repository.variants_of(product_id)
            if variant.id != exclude_id
        ]
        existing = await self._repository.options_of(others)
        if any(combination == options for combination in existing.values()):
            raise ConflictError(message="A variant with these options already exists")

    async def _variant_detail(self, variant: ProductVariant) -> AdminVariantResponse:
        options = await self._repository.options_of([variant.id])
        inventory = await self._repository.inventory_of([variant.id])
        return self._variant_response(variant, options[variant.id], inventory[variant.id])

    # --- media -------------------------------------------------------------------------

    async def upload_media(
        self,
        actor: CurrentUser,
        product_id: UUID,
        data: bytes,
        fields: ProductMediaFields,
        audit_request: Request | None,
    ) -> AdminProductMediaResponse:
        # Cheap check before decoding; repeated under the lock below.
        async with self._session.begin():
            if await self._repository.get(product_id) is None:
                raise _product_not_found()
        image = await process_image_async(data)
        key = new_storage_key(image.image_type.extension)
        try:
            # Inside the try: a cancellation can land after the file is written.
            await self._storage.save(key, image.data)
            async with self._session.begin():
                product = await self._repository.lock(product_id)
                if product is None:
                    raise _product_not_found()
                if fields.variant_id is not None:
                    await self._check_media_variant(product.id, fields.variant_id)
                # The first image of a product becomes its main image automatically.
                is_main = fields.is_main or await self._repository.media_count(product.id) == 0
                replaced = await self._repository.clear_main(product.id) if is_main else []
                media = Media(
                    storage_key=key,
                    content_type=image.image_type.value,
                    size_bytes=len(image.data),
                    width=image.width,
                    height=image.height,
                    created_by=actor.id,
                )
                self._session.add(media)
                await self._session.flush()
                product_media = ProductMedia(
                    product_id=product.id,
                    variant_id=fields.variant_id,
                    media_id=media.id,
                    alt_text=fields.alt_text,
                    display_order=fields.display_order,
                    is_main=is_main,
                    created_by=actor.id,
                )
                self._session.add(product_media)
                await self._flush_media()
                await self._audit(
                    actor,
                    "product_media.created",
                    "product_media",
                    product_media.id,
                    None,
                    {**_media_snapshot(product_media, media), "replaced_main": replaced},
                    audit_request,
                )
                await self._session.refresh(product_media)
                response = self._media_response(product_media, media)
        except BaseException:
            # No row points at the file: remove it, even while the request is cancelled.
            with anyio.CancelScope(shield=True):
                await self._delete_file(key)
            raise
        logger.info("product_media.created", extra={"product_media_id": str(response.id)})
        return response

    async def update_media(
        self,
        actor: CurrentUser,
        product_id: UUID,
        media_id: UUID,
        payload: UpdateProductMediaRequest,
        audit_request: Request | None,
    ) -> AdminProductMediaResponse:
        async with self._session.begin():
            product = await self._repository.lock(product_id)
            if product is None:
                raise _product_not_found()
            row = await self._repository.get_media(product.id, media_id)
            if row is None:
                raise _media_not_found()
            product_media, media = row
            changes = {
                field: getattr(payload, field)
                for field in sorted(payload.model_fields_set)
                if getattr(payload, field) != getattr(product_media, field)
            }
            if not changes:
                return self._media_response(product_media, media)
            if changes.get("variant_id") is not None:
                await self._check_media_variant(product.id, changes["variant_id"])
            if changes.get("is_main") is False:
                # Exactly one main image: choose the new one instead (it replaces this one).
                raise BusinessRuleError(
                    message="Set another image as main instead of unsetting the main image"
                )
            before = _media_snapshot(product_media, media)
            # An explicit UPDATE runs before the new main is flushed (partial unique index).
            replaced = (
                await self._repository.clear_main(product.id)
                if changes.get("is_main") is True
                else []
            )
            for field, value in changes.items():
                setattr(product_media, field, value)
            await self._flush_media()
            after = _media_snapshot(product_media, media)
            if replaced:
                after["replaced_main"] = replaced
            await self._audit(
                actor,
                "product_media.updated",
                "product_media",
                product_media.id,
                before,
                after,
                audit_request,
            )
            response = self._media_response(product_media, media)
        logger.info("product_media.updated", extra={"product_media_id": str(media_id)})
        return response

    async def delete_media(
        self, actor: CurrentUser, product_id: UUID, media_id: UUID, audit_request: Request | None
    ) -> None:
        async with self._session.begin():
            product = await self._repository.lock(product_id)
            if product is None:
                raise _product_not_found()
            row = await self._repository.get_media(product.id, media_id)
            if row is None:
                raise _media_not_found()
            product_media, media = row
            if product_media.is_main:
                if product.status == _PUBLISHED:
                    raise BusinessRuleError(message="A published product must keep its main image")
                if await self._repository.media_count(product.id) > 1:
                    raise BusinessRuleError(
                        message="Set another image as main before deleting the main image"
                    )
            before = _media_snapshot(product_media, media)
            key = media.storage_key
            await self._session.delete(product_media)
            await self._session.flush()
            await self._session.delete(media)
            await self._session.flush()
            await self._audit(
                actor,
                "product_media.deleted",
                "product_media",
                product_media.id,
                before,
                None,
                audit_request,
            )
        # Only after commit: a rolled-back delete must keep its file.
        with anyio.CancelScope(shield=True):
            await self._delete_file(key)
        logger.info("product_media.deleted", extra={"product_media_id": str(media_id)})

    async def _delete_file(self, key: str) -> None:
        # Best effort: a failed delete leaves an orphan file (OPS clean-up), never an error
        # that would hide the original one.
        try:
            await self._storage.delete(key)
        except Exception:
            logger.warning("product_media.file_delete_failed", extra={"storage_key": key})

    async def _check_media_variant(self, product_id: UUID, variant_id: UUID) -> None:
        variant = await self._repository.get_variant(variant_id)
        if variant is None or variant.product_id != product_id:
            raise BusinessRuleError(message="variant_id is not a variant of this product")

    # --- helpers -----------------------------------------------------------------------

    async def _audit(
        self,
        actor: CurrentUser,
        action: str,
        entity_type: str,
        entity_id: UUID,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        audit_request: Request | None,
    ) -> None:
        await record_audit(
            self._session,
            actor_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            request=audit_request,
        )

    async def _flush_product(self) -> None:
        # Backstop for the slug pre-check against a concurrent create.
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "uq_products_slug" in str(exc.orig):
                raise _duplicate_slug() from exc
            raise

    async def _flush_media(self) -> None:
        # The product lock serializes main-image changes; this is only a backstop.
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "uq_product_media_main" in str(exc.orig):
                raise ConflictError(message="The product already has a main image") from exc
            raise

    async def _flush_variant(self) -> None:
        # Backstop for the SKU pre-check: SKUs are global, beyond one product's lock.
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "uq_product_variants_sku" in str(exc.orig):
                raise _duplicate_sku() from exc
            raise
