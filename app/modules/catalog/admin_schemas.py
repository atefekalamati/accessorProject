from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.db.models.catalog import SLUG_PATTERN, CategoryFilterType, VariantOptionKey

# Fields that categories:edit_content may change; everything else needs catalog:manage
# (ADR-023). icon_key and the SEO fields stay with catalog:manage for now.
CONTENT_FIELDS: Final = frozenset({"title", "description", "image_url", "display_order"})
# Columns that cannot be NULL; PATCH may omit them but not send null.
_NOT_NULL_FIELDS: Final = frozenset({"title", "slug", "display_order", "is_active"})

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
Description = Annotated[str, StringConstraints(max_length=5000)]
IconKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
# Checked further (https, allowed host) by the service, which knows the settings.
ImageUrl = Annotated[str, StringConstraints(min_length=1, max_length=500)]
DisplayOrder = Annotated[int, Field(ge=0, le=1_000_000)]
SeoTitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
SeoDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class CreateCategoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    slug: Slug
    parent_id: UUID | None = None
    description: Description | None = None
    icon_key: IconKey | None = None
    image_url: ImageUrl | None = None
    display_order: DisplayOrder = 0
    is_active: bool = True
    seo_title: SeoTitle | None = None
    seo_description: SeoDescription | None = None


class UpdateCategoryRequest(BaseModel):
    """Partial update; only the fields present in the body are changed."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    slug: Slug | None = None
    parent_id: UUID | None = None
    description: Description | None = None
    icon_key: IconKey | None = None
    image_url: ImageUrl | None = None
    display_order: DisplayOrder | None = None
    is_active: bool | None = None
    seo_title: SeoTitle | None = None
    seo_description: SeoDescription | None = None

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        nulls = sorted(
            name for name in self.model_fields_set & _NOT_NULL_FIELDS if getattr(self, name) is None
        )
        if nulls:
            raise ValueError(f"must not be null: {', '.join(nulls)}")
        return self


class AdminCategoryResponse(BaseModel):
    id: UUID
    parent_id: UUID | None
    title: str
    slug: str
    description: str | None
    icon_key: str | None
    image_url: str | None
    display_order: int
    is_active: bool
    seo_title: str | None
    seo_description: str | None
    created_at: datetime
    updated_at: datetime


MAX_CATEGORY_FILTERS: Final = 30
PRICE_FILTER_KEY: Final = "price"

FilterKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
FilterLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CategoryFilterItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute_key: FilterKey
    label: FilterLabel
    filter_type: CategoryFilterType
    display_order: DisplayOrder = 0
    is_active: bool = True

    @model_validator(mode="after")
    def check_type(self) -> Self:
        # price is the only range; a color swatch only makes sense for the color option.
        is_price = self.attribute_key == PRICE_FILTER_KEY
        if is_price != (self.filter_type == CategoryFilterType.RANGE):
            raise ValueError("filter_type 'range' is only for attribute_key 'price', and back")
        if (
            self.filter_type == CategoryFilterType.COLOR
            and self.attribute_key != VariantOptionKey.COLOR
        ):
            raise ValueError("filter_type 'color' is only for attribute_key 'color'")
        return self


class ReplaceCategoryFiltersRequest(BaseModel):
    """The complete new filter set of the category; it replaces the current one."""

    model_config = ConfigDict(extra="forbid")

    filters: list[CategoryFilterItem] = Field(max_length=MAX_CATEGORY_FILTERS)

    @model_validator(mode="after")
    def check_unique_keys(self) -> Self:
        keys = [item.attribute_key for item in self.filters]
        if len(keys) != len(set(keys)):
            raise ValueError("attribute_key must be unique")
        return self


class AdminCategoryFilterResponse(BaseModel):
    id: UUID
    attribute_key: str
    label: str
    filter_type: str
    display_order: int
    is_active: bool


class AdminCategoryFiltersResponse(BaseModel):
    items: list[AdminCategoryFilterResponse]
