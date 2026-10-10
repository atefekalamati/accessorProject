from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


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
