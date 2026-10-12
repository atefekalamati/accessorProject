"""Request and response models of the admin product endpoints (CAT-11, PRD «محصولات» ✓)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.db.models.catalog import SKU_PATTERN, SLUG_PATTERN, ProductStatus, VariantOptionKey
from app.shared.money import MAX_PRICE_TOMAN

MAX_PRODUCT_ATTRIBUTES: Final = 50
PRICE_FIELDS: Final = frozenset({"base_price", "sale_price", "sale_start_at", "sale_end_at"})
# Server-owned fields a client may send but never sets (PRD «محصولات»): dropped before
# validation, while any other unknown key is still a 400.
_SYSTEM_FIELDS: Final = frozenset(
    {
        "id",
        "product_id",
        "status",
        "published_at",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "deleted_at",
        "price_version",
        "tax_enabled",
        "stock",
        "total_quantity",
        "reserved_quantity",
        "low_stock_threshold",
    }
)


def _drop_fields(data: Any, fields: frozenset[str]) -> Any:
    if isinstance(data, dict):
        return {key: value for key, value in data.items() if key not in fields}
    return data


def _check_not_null(model: BaseModel, fields: frozenset[str]) -> None:
    if not model.model_fields_set:
        raise ValueError("at least one field is required")
    nulls = sorted(name for name in model.model_fields_set & fields if getattr(model, name) is None)
    if nulls:
        raise ValueError(f"must not be null: {', '.join(nulls)}")


def _upper_sku(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
Description = Annotated[str, StringConstraints(max_length=10_000)]
Sku = Annotated[str, BeforeValidator(_upper_sku), StringConstraints(pattern=SKU_PATTERN)]
DisplayOrder = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
Price = Annotated[int, Field(strict=True, ge=1, le=MAX_PRICE_TOMAN)]
AttributeKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
AttributeValue = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
OptionValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
# A blank alt text is stored as null, so "" and null are the same value.
AltText = Annotated[
    str | None,
    StringConstraints(strip_whitespace=True, max_length=200),
    AfterValidator(lambda value: value or None),
]


class _SystemFieldsIgnored(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def drop_system_fields(cls, data: Any) -> Any:
        return _drop_fields(data, _SYSTEM_FIELDS)


class AttributeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: AttributeKey
    value: AttributeValue


def _check_unique_keys(attributes: list[AttributeItem] | None) -> None:
    if attributes is None:
        return
    keys = [item.key for item in attributes]
    if len(keys) != len(set(keys)):
        raise ValueError("attribute keys must be unique")


class CreateProductRequest(_SystemFieldsIgnored):
    title: Title
    slug: Slug
    category_id: UUID
    description: Description | None = None
    is_featured: bool = False
    attributes: list[AttributeItem] = Field(default_factory=list, max_length=MAX_PRODUCT_ATTRIBUTES)

    @model_validator(mode="after")
    def check_attributes(self) -> Self:
        _check_unique_keys(self.attributes)
        return self


class UpdateProductRequest(_SystemFieldsIgnored):
    """Partial update; ``attributes`` replaces the whole set when present.

    ``status`` is rejected (400 unknown field) instead of ignored: it has its own endpoint.
    """

    @model_validator(mode="before")
    @classmethod
    def drop_system_fields(cls, data: Any) -> Any:
        return _drop_fields(data, _SYSTEM_FIELDS - {"status"})

    title: Title | None = None
    slug: Slug | None = None
    category_id: UUID | None = None
    description: Description | None = None
    is_featured: bool | None = None
    attributes: list[AttributeItem] | None = Field(default=None, max_length=MAX_PRODUCT_ATTRIBUTES)

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        _check_not_null(
            self, frozenset({"title", "slug", "category_id", "is_featured", "attributes"})
        )
        _check_unique_keys(self.attributes)
        return self


class ChangeProductStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProductStatus


class VariantOptions(BaseModel):
    """At most one value per key; an empty object is the product's default variant."""

    model_config = ConfigDict(extra="forbid")

    color: OptionValue | None = None
    size: OptionValue | None = None
    model: OptionValue | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            key.value: value
            for key in VariantOptionKey
            if (value := getattr(self, key.value)) is not None
        }


class CreateVariantRequest(_SystemFieldsIgnored):
    sku: Sku
    options: VariantOptions = Field(default_factory=VariantOptions)
    display_order: DisplayOrder = 0
    is_active: bool = False
    is_purchasable: bool = True
    # The initial price; needs pricing:update. Later changes use the pricing endpoints.
    base_price: Price | None = None
    sale_price: Price | None = None
    sale_start_at: datetime | None = None
    sale_end_at: datetime | None = None

    @model_validator(mode="after")
    def check_price(self) -> Self:
        if self.sale_price is not None:
            if self.base_price is None:
                raise ValueError("sale_price requires base_price")
            if self.sale_price > self.base_price:
                raise ValueError("sale_price must not exceed base_price")
        elif self.sale_start_at is not None or self.sale_end_at is not None:
            raise ValueError("the sale window requires sale_price")
        for moment in (self.sale_start_at, self.sale_end_at):
            if moment is not None and moment.tzinfo is None:
                raise ValueError("sale window times need a timezone")
        if (
            self.sale_start_at is not None
            and self.sale_end_at is not None
            and self.sale_start_at >= self.sale_end_at
        ):
            raise ValueError("sale_start_at must be before sale_end_at")
        return self


class UpdateVariantRequest(_SystemFieldsIgnored):
    """Partial update without prices: price fields are ignored like system fields (PRD)."""

    sku: Sku | None = None
    options: VariantOptions | None = None
    display_order: DisplayOrder | None = None
    is_active: bool | None = None
    is_purchasable: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def drop_price_fields(cls, data: Any) -> Any:
        return _drop_fields(data, PRICE_FIELDS)

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        _check_not_null(self, frozenset(type(self).model_fields))
        return self


class ProductMediaFields(BaseModel):
    """Form fields of a product image upload (multipart, next to ``file``)."""

    model_config = ConfigDict(extra="forbid")

    alt_text: AltText | None = None
    variant_id: UUID | None = None
    display_order: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    is_main: bool = False


class UpdateProductMediaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alt_text: AltText | None = None
    variant_id: UUID | None = None
    display_order: DisplayOrder | None = None
    is_main: bool | None = None

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        _check_not_null(self, frozenset({"display_order", "is_main"}))
        return self


# --- responses -------------------------------------------------------------------------


class CategoryRef(BaseModel):
    id: UUID
    title: str


class PriceRange(BaseModel):
    min: int
    max: int


class AdminProductListItem(BaseModel):
    id: UUID
    title: str
    slug: str
    status: str
    category: CategoryRef | None
    active_variant_count: int
    # Over base prices of active variants; null when there is none.
    price_range: PriceRange | None
    main_image_url: str | None
    updated_at: datetime


class StockResponse(BaseModel):
    """Admin-only numbers; public responses carry only the status (ADR-029)."""

    total: int
    reserved: int
    free: int
    low_stock_threshold: int
    status: str


class AdminVariantResponse(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    options: dict[str, str]
    display_order: int
    is_active: bool
    is_purchasable: bool
    base_price: int | None
    sale_price: int | None
    sale_start_at: datetime | None
    sale_end_at: datetime | None
    tax_enabled: bool
    price_version: int
    stock: StockResponse
    created_at: datetime
    updated_at: datetime


class AdminProductMediaResponse(BaseModel):
    id: UUID
    media_id: UUID
    url: str
    variant_id: UUID | None
    alt_text: str | None
    display_order: int
    is_main: bool
    width: int
    height: int
    created_at: datetime


class AdminProductResponse(BaseModel):
    id: UUID
    title: str
    slug: str
    category_id: UUID
    description: str | None
    status: str
    published_at: datetime | None
    is_featured: bool
    attributes: list[AttributeItem]
    variants: list[AdminVariantResponse]
    media: list[AdminProductMediaResponse]
    # Unmet publish conditions; empty when the product can be published.
    publish_blockers: list[str]
    created_by: UUID | None
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime
