"""Page/limit pagination and sort/filter allowlists for list endpoints.

Public lists and admin lists both use page/limit: the PRD («دسته‌بندی محصولات») requires
``page``, ``limit``, the total count and pagination info in the response. Only the caps differ.

Every violation is a 400 ``VALIDATION_ERROR`` in the standard error shape (ADR-011):
out-of-range ``page``/``limit`` via FastAPI query validation; unknown sort keys and
unknown query parameters via ``BadRequestError``.

Usage::

    PRODUCT_SORTS = {"newest": ..., "price_asc": ...}

    @router.get(
        "/products",
        dependencies=[Depends(allowed_query_params("page", "limit", "sort", "min_price"))],
    )
    async def list_products(
        paging: Annotated[PageParams, Depends(public_page_params)],
        sort: str | None = None,
    ) -> Page[ProductOut]:
        order_by = resolve_sort(sort, PRODUCT_SORTS, default="newest")
        ...
        return Page.build(items, total=total, params=paging)
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Query, Request
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, UnaryExpression, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import QueryableAttribute

from app.core.errors import BadRequestError

PUBLIC_DEFAULT_LIMIT = 24
PUBLIC_MAX_LIMIT = 48
ADMIN_DEFAULT_LIMIT = 20
ADMIN_MAX_LIMIT = 100
# Any SELECT, whatever its row shape (SQLAlchemy 2.1 types ``Select`` by its columns).
AnySelect = Select[*tuple[Any, ...]]
# Deep OFFSETs are expensive; the PRD requires page to be bounded as well as limit.
MAX_PAGE = 1000


@dataclass(frozen=True, slots=True)
class PageParams:
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def page_params(
    *, default_limit: int, max_limit: int, max_page: int = MAX_PAGE
) -> Callable[..., PageParams]:
    """Build a ``Depends`` callable validating ``page`` and ``limit`` against the given caps."""
    if not 1 <= default_limit <= max_limit:
        raise ValueError("default_limit must be between 1 and max_limit")

    # Upper bounds are checked in the body: with postponed annotations FastAPI cannot
    # resolve closure variables inside ``Annotated[..., Query(le=...)]``.
    def dependency(
        page: Annotated[int, Query(ge=1)] = 1,
        limit: Annotated[int | None, Query(ge=1)] = None,
    ) -> PageParams:
        errors: list[tuple[str, str]] = []
        if page > max_page:
            errors.append(("query.page", f"Must be at most {max_page}"))
        if limit is not None and limit > max_limit:
            errors.append(("query.limit", f"Must be at most {max_limit}"))
        if errors:
            raise _not_allowed(*errors)
        return PageParams(page=page, limit=default_limit if limit is None else limit)

    return dependency


public_page_params = page_params(default_limit=PUBLIC_DEFAULT_LIMIT, max_limit=PUBLIC_MAX_LIMIT)
admin_page_params = page_params(default_limit=ADMIN_DEFAULT_LIMIT, max_limit=ADMIN_MAX_LIMIT)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(cls, items: Sequence[T], *, total: int, params: PageParams) -> Page[T]:
        return cls(
            items=list(items),
            total=total,
            page=params.page,
            limit=params.limit,
            pages=math.ceil(total / params.limit),
        )


def _not_allowed(*fields: tuple[str, str]) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[
            {"field": field, "message": message, "type": "not_allowed"} for field, message in fields
        ],
    )


def resolve_sort[T](raw: str | None, allowed: Mapping[str, T], *, default: str) -> T:
    """Map a public sort key (e.g. ``price_asc``) to its ordering spec; unknown key → 400.

    Clients only ever pick a key; column names and directions stay server-side.
    """
    if default not in allowed:
        raise ValueError(f"default sort {default!r} is not in the allowlist")
    key = default if raw is None or raw == "" else raw
    if key not in allowed:
        raise _not_allowed(("query.sort", f"Allowed values: {', '.join(sorted(allowed))}"))
    return allowed[key]


def allowed_query_params(*names: str) -> Callable[[Request], Any]:
    """Build a ``Depends`` callable rejecting any query parameter outside ``names`` with 400.

    FastAPI silently ignores unknown query parameters; for filterable lists a typo or an
    unsupported filter must fail loudly instead of returning unfiltered results.
    """
    allowed = frozenset(names)

    def dependency(request: Request) -> None:
        unknown = sorted(set(request.query_params.keys()) - allowed)
        if unknown:
            raise _not_allowed(*((f"query.{name}", "Unknown parameter") for name in unknown))

    return dependency


async def paginate(
    session: AsyncSession,
    statement: AnySelect,
    order_by: Sequence[UnaryExpression[Any] | ColumnElement[Any]],
    *,
    tie_breaker: ColumnElement[Any] | QueryableAttribute[Any],
    params: PageParams,
) -> tuple[list[Any], int]:
    """Run one page of ``statement`` and the total count of its rows (two queries).

    ``tie_breaker`` (a unique column, e.g. ``Product.id``) is appended to ``order_by`` so
    rows that tie on the sort key keep one order on every page: no row repeats or goes
    missing between pages as long as the data does not change.
    """
    total = await session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    page = statement.order_by(*order_by, tie_breaker).offset(params.offset).limit(params.limit)
    rows = (await session.execute(page)).all()
    return list(rows), int(total or 0)
