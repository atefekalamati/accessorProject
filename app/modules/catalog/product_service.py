"""Public product detail (CAT-08, PRD «جزئیات محصول» ✓, ADR-020, ADR-029, ADR-031)."""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.time import utc_now
from app.db.models import Category, InventoryItem, Media, ProductMedia, ProductVariant
from app.db.models.catalog import VariantOptionKey
from app.modules.catalog.product_repository import ProductRepository
from app.modules.catalog.schemas import (
    BreadcrumbItem,
    ProductAttributeOut,
    ProductDetailResponse,
    PublicPriceRange,
    PublicProductMedia,
    PublicVariant,
    VariantPriceOut,
)
from app.modules.inventory.stock import (
    StockStatus,
    free_quantity,
    product_stock_status,
    stock_status,
    variant_level,
)
from app.modules.pricing.calculator import UnitPrice, VariantPrice, unit_price
from app.shared.storage import FileStorage

# Displayed prices never include tax; the display policy once tax is on is D11 (ADR-010).
TAX_INCLUDED: Final = False


def _not_found() -> NotFoundError:
    # One answer for draft, archived, soft-deleted and unknown products (no existence leak).
    return NotFoundError(message="Product not found")


def _breadcrumb(chain: list[Category]) -> list[BreadcrumbItem]:
    """The visible part of the chain: from the root down to the first hidden category.

    A category is public only when it and all its ancestors are active and not deleted
    (ADR-022), so a hidden main category just drops out of the breadcrumb (ADR-020).
    """
    items: list[BreadcrumbItem] = []
    for category in chain:
        if not category.is_active or category.deleted_at is not None:
            break
        items.append(BreadcrumbItem(id=category.id, title=category.title, slug=category.slug))
    return items


def _variant_price(variant: ProductVariant) -> VariantPrice:
    return VariantPrice(
        base_price=variant.base_price,
        sale_price=variant.sale_price,
        sale_start_at=variant.sale_start_at,
        sale_end_at=variant.sale_end_at,
        tax_enabled=variant.tax_enabled,
        price_version=variant.price_version,
    )


def _price_out(unit: UnitPrice) -> VariantPriceOut:
    return VariantPriceOut(
        base_price=unit.original,
        sale_price=unit.final if unit.on_sale else None,
        final_price=unit.final,
        discount_amount=unit.discount_amount,
        discount_percent=unit.discount_percent,
    )


def _options(variants: list[tuple[ProductVariant, dict[str, str]]]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for key in VariantOptionKey:
        seen: list[str] = []
        for _variant, options in variants:
            value = options.get(key.value)
            if value is not None and value not in seen:
                seen.append(value)
        if seen:
            values[key.value] = seen
    return values


class ProductService:
    def __init__(
        self, session: AsyncSession, repository: ProductRepository, storage: FileStorage
    ) -> None:
        self._session = session
        self._repository = repository
        self._storage = storage

    async def detail(self, slug: str, *, at: datetime | None = None) -> ProductDetailResponse:
        """A published product; price and stock are read fresh on every request."""
        now = at or utc_now()
        async with self._session.begin():
            product = await self._repository.get_published(slug)
            if product is None:
                raise _not_found()
            chain = await self._repository.category_chain(product.category_id)
            attributes = await self._repository.attributes_of(product.id)
            # Active, non-deleted variants only (the active ones always have a price).
            variants = [
                variant
                for variant in await self._repository.variants_of(product.id)
                if variant.is_active and variant.base_price is not None
            ]
            ids = [variant.id for variant in variants]
            options = await self._repository.options_of(ids)
            inventory = await self._repository.inventory_of(ids)
            media = await self._repository.media_of(product.id)

        public_variants = [
            self._variant(variant, options[variant.id], inventory[variant.id], now)
            for variant in variants
        ]
        purchasable = [variant for variant in public_variants if variant.purchasable]
        candidates = purchasable or public_variants
        default = candidates[0] if candidates else None
        finals = [variant.price.final_price for variant in public_variants]
        return ProductDetailResponse(
            id=product.id,
            slug=product.slug,
            title=product.title,
            description=product.description,
            published_at=product.published_at,
            breadcrumb=_breadcrumb(chain),
            attributes=[
                ProductAttributeOut(key=item.attribute_key, value=item.attribute_value)
                for item in attributes
            ],
            options=_options([(variant, options[variant.id]) for variant in variants]),
            variants=public_variants,
            default_variant_id=None if default is None else default.id,
            price_range=PublicPriceRange(min=min(finals), max=max(finals)) if finals else None,
            tax_included=TAX_INCLUDED,
            availability=product_stock_status(
                StockStatus(variant.availability) for variant in public_variants
            ),
            media=self._media(media, set(ids)),
        )

    def _variant(
        self,
        variant: ProductVariant,
        options: dict[str, str],
        items: list[InventoryItem],
        now: datetime,
    ) -> PublicVariant:
        unit = unit_price(_variant_price(variant), now)
        if unit is None:  # filtered out above: active variants always have a base price
            raise RuntimeError(f"variant {variant.id} has no price")
        level = variant_level(items)
        return PublicVariant(
            id=variant.id,
            sku=variant.sku,
            options=options,
            price=_price_out(unit),
            availability=stock_status(level),
            purchasable=variant.is_active
            and variant.is_purchasable
            and unit.original > 0
            and free_quantity(level) > 0,
        )

    def _media(
        self, media: list[tuple[ProductMedia, Media]], variant_ids: set[object]
    ) -> list[PublicProductMedia]:
        # Images of a variant that is not shown are not shown either; main image first.
        visible = [
            (item, stored)
            for item, stored in media
            if item.variant_id is None or item.variant_id in variant_ids
        ]
        visible.sort(key=lambda row: not row[0].is_main)
        return [
            PublicProductMedia(
                id=item.id,
                url=self._storage.url(stored.storage_key),
                alt_text=item.alt_text,
                is_main=item.is_main,
                variant_id=item.variant_id,
                width=stored.width,
                height=stored.height,
            )
            for item, stored in visible
        ]
