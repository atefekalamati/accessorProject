"""Public product reads: detail, listing, pricing and availability (CAT-08, CAT-07,
PRC-04, INV-07; PRD «جزئیات محصول» ✓, «دسته‌بندی محصولات» ✓, «قیمت و مالیات» ✓ and
«موجودی و رزرو» ✓; ADR-020, ADR-029, ADR-031, ADR-032, ADR-033)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.time import utc_now
from app.db.models import (
    Category,
    Media,
    Product,
    ProductMedia,
    ProductVariant,
)
from app.db.models.catalog import VariantOptionKey
from app.modules.catalog.product_query import ListingFilters, ProductSort
from app.modules.catalog.product_repository import ProductRepository
from app.modules.catalog.repository import CategoryRepository
from app.modules.catalog.schemas import (
    BreadcrumbItem,
    ColorSwatch,
    ProductAttributeOut,
    ProductAvailabilityResponse,
    ProductCard,
    ProductDetailResponse,
    ProductListResponse,
    ProductPricingResponse,
    PublicPriceRange,
    PublicProductMedia,
    PublicVariant,
    VariantAvailability,
    VariantPriceOut,
    VariantPricing,
)
from app.modules.inventory.stock import (
    StockLevel,
    StockStatus,
    free_quantity,
    product_stock_status,
    stock_status,
)
from app.modules.pricing.calculator import CURRENCY, UnitPrice, unit_price
from app.modules.pricing.variants import variant_price
from app.shared.pagination import Page, PageParams
from app.shared.storage import FileStorage

# Displayed prices never include tax; the display policy once tax is on is D11 (ADR-010).
TAX_INCLUDED: Final = False
# A product card shows at most this many colour swatches (D42).
MAX_CARD_SWATCHES: Final = 5


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


def _price_out(unit: UnitPrice) -> VariantPriceOut:
    return VariantPriceOut(
        base_price=unit.original,
        sale_price=unit.final if unit.on_sale else None,
        final_price=unit.final,
        discount_amount=unit.discount_amount,
        discount_percent=unit.discount_percent,
    )


def _purchasable(variant: ProductVariant, unit: UnitPrice, level: StockLevel | None) -> bool:
    return (
        variant.is_active
        and variant.is_purchasable
        and unit.original > 0
        and free_quantity(level) > 0
    )


def _unit(variant: ProductVariant, now: datetime) -> UnitPrice:
    unit = unit_price(variant_price(variant), now)
    if unit is None:  # callers pass active variants, and those always have a base price
        raise RuntimeError(f"variant {variant.id} has no price")
    return unit


@dataclass(frozen=True, slots=True)
class ListingRequest:
    """Validated query of a listing endpoint (parsed by the router)."""

    params: PageParams
    sort: ProductSort
    min_price: int | None = None
    max_price: int | None = None
    in_stock: bool = False
    has_discount: bool = False
    values: Mapping[str, frozenset[str]] = field(default_factory=dict)
    # Filter key → the query parameter it came from (for error details).
    sources: Mapping[str, str] = field(default_factory=dict)


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


def _swatches(
    variants: list[ProductVariant],
    colors: Mapping[UUID, tuple[str, str | None]],
    limit: int | None = None,
) -> list[ColorSwatch]:
    """Distinct colours in variant order; the first variant's hex wins for a repeated colour."""
    swatches: list[ColorSwatch] = []
    seen: set[str] = set()
    for variant in variants:
        color = colors.get(variant.id)
        if color is None or color[0] in seen:
            continue
        seen.add(color[0])
        swatches.append(ColorSwatch(value=color[0], hex=color[1]))
        if limit is not None and len(swatches) == limit:
            break
    return swatches


class ProductService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ProductRepository,
        categories: CategoryRepository,
        storage: FileStorage,
        *,
        new_days: int = 30,
    ) -> None:
        self._session = session
        self._repository = repository
        self._categories = categories
        self._storage = storage
        self._new_days = new_days

    def _is_new(self, product: Product, now: datetime) -> bool:
        return product.created_at > now - timedelta(days=self._new_days)

    async def list_products(
        self,
        request: ListingRequest,
        *,
        category_slug: str | None = None,
        at: datetime | None = None,
    ) -> ProductListResponse:
        """Published products, filtered, sorted and paged in the database (ADR-032)."""
        now = at or utc_now()
        async with self._session.begin():
            category_id = None
            if category_slug is not None:
                category_id = await self._visible_category(category_slug)
                await self._check_applicable(category_id, request)
            filters = ListingFilters(
                category_id=category_id,
                min_price=request.min_price,
                max_price=request.max_price,
                in_stock=request.in_stock,
                has_discount=request.has_discount,
                values=request.values,
            )
            listed, total = await self._repository.list_public(
                filters, request.sort, now, request.params
            )
            ids = [product.id for product in listed]
            variants = await self._repository.public_variants_of(ids)
            levels = await self._repository.stock_levels_of(
                [variant.id for items in variants.values() for variant in items], now
            )
            images = await self._repository.main_image_keys(ids)
            colors = await self._repository.colors_of(
                [variant.id for items in variants.values() for variant in items]
            )

        cards = [
            card
            for product in listed
            if (card := self._card(product, variants[product.id], levels, images, colors, now))
            is not None
        ]
        return Page.build(cards, total=total, params=request.params)

    async def pricing(
        self, product_id: UUID, *, variant_id: UUID | None = None, at: datetime | None = None
    ) -> ProductPricingResponse:
        """Current prices of a published product's public variants (or of one of them)."""
        now = at or utc_now()
        async with self._session.begin():
            variants = await self._public_variants(product_id, variant_id)
        units = [(variant, _unit(variant, now)) for variant in variants]
        finals = [unit.final for _variant, unit in units]
        return ProductPricingResponse(
            product_id=product_id,
            currency=CURRENCY,
            tax_included=TAX_INCLUDED,
            calculated_at=now,
            price_range=PublicPriceRange(min=min(finals), max=max(finals)) if finals else None,
            variants=[
                VariantPricing(variant_id=variant.id, sku=variant.sku, price=_price_out(unit))
                for variant, unit in units
            ],
        )

    async def availability(
        self, product_id: UUID, *, variant_id: UUID | None = None, at: datetime | None = None
    ) -> ProductAvailabilityResponse:
        """Stock status of a published product's public variants; no stock numbers.

        A read without locks: it may lag a concurrent order, only towards less (ADR-029).
        """
        now = at or utc_now()
        async with self._session.begin():
            variants = await self._public_variants(product_id, variant_id)
            levels = await self._repository.stock_levels_of(
                [variant.id for variant in variants], now
            )
        items: list[VariantAvailability] = []
        for variant in variants:
            level = levels[variant.id]
            items.append(
                VariantAvailability(
                    variant_id=variant.id,
                    sku=variant.sku,
                    availability=stock_status(level),
                    purchasable=_purchasable(variant, _unit(variant, now), level),
                )
            )
        return ProductAvailabilityResponse(
            product_id=product_id,
            availability=product_stock_status(StockStatus(item.availability) for item in items),
            variants=items,
        )

    async def _public_variants(
        self, product_id: UUID, variant_id: UUID | None
    ) -> list[ProductVariant]:
        """The public variants of a published product; ``variant_id`` narrows to one.

        A hidden product and a variant that is not public (or belongs to another product)
        get the same 404 as an unknown one (SD rule).
        """
        if await self._repository.get_published_by_id(product_id) is None:
            raise _not_found()
        variants = (await self._repository.public_variants_of([product_id]))[product_id]
        if variant_id is None:
            return variants
        selected = [variant for variant in variants if variant.id == variant_id]
        if not selected:
            raise NotFoundError(message="Variant not found")
        return selected

    async def _visible_category(self, slug: str) -> UUID:
        # Same visibility rule as GET /categories/{slug} (ADR-022).
        categories = await self._categories.list_visible()
        category = next((item for item in categories if item.slug == slug), None)
        if category is None:
            raise NotFoundError(message="Category not found")
        return category.id

    async def _check_applicable(self, category_id: UUID, request: ListingRequest) -> None:
        """Attribute filters must be among the category's active filters (PRD: 422)."""
        filters = await self._categories.active_filters(category_id)
        active = {item.attribute_key for item in filters}
        unknown = sorted(key for key in request.values if key not in active)
        if unknown:
            raise BusinessRuleError(
                message="Filter does not apply to this category",
                details=[
                    {
                        "field": request.sources.get(key, "query"),
                        "message": f"Filter '{key}' is not available in this category",
                        "type": "filter_not_applicable",
                    }
                    for key in unknown
                ],
            )

    def _card(
        self,
        product: Product,
        variants: list[ProductVariant],
        levels: dict[UUID, StockLevel | None],
        images: dict[UUID, str],
        colors: Mapping[UUID, tuple[str, str | None]],
        now: datetime,
    ) -> ProductCard | None:
        if not variants:  # its last variant went away between the two reads
            return None
        units = [(variant, _unit(variant, now)) for variant in variants]
        # ``min`` keeps the first of equal prices, i.e. the lowest ``display_order``.
        cheapest = min((unit for _variant, unit in units), key=lambda unit: unit.final)
        finals = [unit.final for _variant, unit in units]
        only, only_unit = units[0]
        quick_add = len(units) == 1 and _purchasable(only, only_unit, levels[only.id])
        key = images.get(product.id)
        return ProductCard(
            id=product.id,
            slug=product.slug,
            title=product.title,
            published_at=product.published_at,
            image_url=None if key is None else self._storage.url(key),
            price=_price_out(cheapest),
            price_range=PublicPriceRange(min=min(finals), max=max(finals)),
            max_discount_percent=max(unit.discount_percent for _variant, unit in units),
            availability=product_stock_status(
                stock_status(levels[variant.id]) for variant in variants
            ),
            color_swatches=_swatches(variants, colors, MAX_CARD_SWATCHES),
            is_new=self._is_new(product, now),
            quick_add_variant_id=only.id if quick_add else None,
        )

    async def detail(self, slug: str, *, at: datetime | None = None) -> ProductDetailResponse:
        """A published product; price and stock are read fresh on every request."""
        now = at or utc_now()
        async with self._session.begin():
            product = await self._repository.get_published(slug)
            if product is None:
                raise _not_found()
            chain = await self._repository.category_chain(product.category_id)
            attributes = await self._repository.attributes_of(product.id)
            # Public variants only: active, priced, not deleted (same set as CAT-07, PRC-04).
            variants = (await self._repository.public_variants_of([product.id]))[product.id]
            ids = [variant.id for variant in variants]
            options = await self._repository.options_of(ids)
            colors = await self._repository.colors_of(ids)
            levels = await self._repository.stock_levels_of(ids, now)
            media = await self._repository.media_of(product.id)

        public_variants = [
            self._variant(variant, options[variant.id], colors, levels[variant.id], now)
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
            color_swatches=_swatches(variants, colors),
            is_new=self._is_new(product, now),
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
        colors: Mapping[UUID, tuple[str, str | None]],
        level: StockLevel | None,
        now: datetime,
    ) -> PublicVariant:
        unit = _unit(variant, now)
        color = colors.get(variant.id)
        return PublicVariant(
            id=variant.id,
            sku=variant.sku,
            options=options,
            color_hex=None if color is None else color[1],
            price=_price_out(unit),
            availability=stock_status(level),
            purchasable=_purchasable(variant, unit, level),
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
