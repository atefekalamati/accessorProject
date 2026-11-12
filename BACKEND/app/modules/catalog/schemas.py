from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.shared.pagination import Page


class CategorySummary(BaseModel):
    """Public card of a category: enough for menus, breadcrumbs and sub-category links."""

    id: UUID
    title: str
    slug: str
    icon_key: str | None
    image_url: str | None


class CategoryTreeNode(CategorySummary):
    children: list[CategoryTreeNode]


class CategoryTreeResponse(BaseModel):
    items: list[CategoryTreeNode]


class BreadcrumbItem(BaseModel):
    id: UUID
    title: str
    slug: str


class CategoryDetailResponse(BaseModel):
    id: UUID
    title: str
    slug: str
    description: str | None
    icon_key: str | None
    image_url: str | None
    seo_title: str | None
    seo_description: str | None
    # From the root down to this category, inclusive.
    breadcrumb: list[BreadcrumbItem]
    children: list[CategorySummary]


class FilterValue(BaseModel):
    value: str
    # Published products in the category having this value.
    count: int


class PublicCategoryFilter(BaseModel):
    key: str
    label: str
    type: str
    # Empty for the ``range`` (price) filter, which has ``min`` and ``max`` instead.
    values: list[FilterValue]
    min: int | None = None
    max: int | None = None


class CategoryFiltersResponse(BaseModel):
    items: list[PublicCategoryFilter]


# --- product detail (CAT-08, PRD «جزئیات محصول» ✓) -------------------------------------


class ProductAttributeOut(BaseModel):
    key: str
    value: str


class VariantPriceOut(BaseModel):
    base_price: int
    # Null unless the sale window is open now.
    sale_price: int | None
    final_price: int
    discount_amount: int
    discount_percent: int


class ColorSwatch(BaseModel):
    """A colour option and its swatch (#RRGGBB, or null when the admin set none; D42)."""

    value: str
    hex: str | None


class PublicVariant(BaseModel):
    id: UUID
    sku: str
    options: dict[str, str]
    color_hex: str | None
    price: VariantPriceOut
    availability: str
    purchasable: bool


class PublicPriceRange(BaseModel):
    min: int
    max: int


class PublicProductMedia(BaseModel):
    id: UUID
    url: str
    alt_text: str | None
    is_main: bool
    variant_id: UUID | None
    width: int
    height: int


class ProductDetailResponse(BaseModel):
    """Explicit allowlist: no stock numbers, thresholds, price versions or actor ids."""

    id: UUID
    slug: str
    title: str
    description: str | None
    published_at: datetime | None
    breadcrumb: list[BreadcrumbItem]
    attributes: list[ProductAttributeOut]
    options: dict[str, list[str]]
    # Every distinct colour of the public variants, in variant order (D42).
    color_swatches: list[ColorSwatch]
    is_new: bool
    variants: list[PublicVariant]
    default_variant_id: UUID | None
    price_range: PublicPriceRange | None
    tax_included: bool
    availability: str
    media: list[PublicProductMedia]


# --- product listing (CAT-07, PRD «دسته‌بندی محصولات» ✓) --------------------------------


class ProductCard(BaseModel):
    """Explicit allowlist, like the detail: no stock numbers or internal fields."""

    id: UUID
    slug: str
    title: str
    published_at: datetime | None
    image_url: str | None
    # The cheapest variant's price: the listing price, used by the price filter and sort.
    price: VariantPriceOut
    price_range: PublicPriceRange
    # Highest current discount among the variants (display only, floored).
    max_discount_percent: int
    availability: str
    # Up to MAX_CARD_SWATCHES distinct colours of the public variants, in variant order.
    color_swatches: list[ColorSwatch]
    # Created within PRODUCT_NEW_DAYS days (D42).
    is_new: bool
    # The only variant, when the product has exactly one and it can be bought now;
    # otherwise null and the client opens the product page to pick a variant.
    quick_add_variant_id: UUID | None


ProductListResponse = Page[ProductCard]


# --- pricing and availability (PRC-04, INV-07; ADR-033) ---------------------------------


class VariantPricing(BaseModel):
    variant_id: UUID
    sku: str
    price: VariantPriceOut


class ProductPricingResponse(BaseModel):
    """Server-computed prices only: no price version, tax flag or stock numbers."""

    product_id: UUID
    currency: str
    tax_included: bool
    # The moment the prices were computed (the sale window is evaluated at this time).
    calculated_at: datetime
    price_range: PublicPriceRange | None
    variants: list[VariantPricing]


class VariantAvailability(BaseModel):
    variant_id: UUID
    sku: str
    availability: str
    purchasable: bool


class ProductAvailabilityResponse(BaseModel):
    """Stock status only; stock numbers stay internal (ADR-029)."""

    product_id: UUID
    availability: str
    variants: list[VariantAvailability]
