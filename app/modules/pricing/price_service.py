"""Admin price changes with history and audit (PRC-03, PRD «قیمت و مالیات» ✓, ADR-030,
ADR-035)."""

from __future__ import annotations

import logging
from dataclasses import asdict, replace
from typing import Any, Final
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError, NotFoundError
from app.db.models import Product, ProductVariant
from app.modules.auth.service import CurrentUser
from app.modules.catalog.product_repository import ProductRepository
from app.modules.pricing.history import PriceState, history_page, record_price_change
from app.modules.pricing.schemas import (
    PRICE_FIELDS,
    PriceHistoryItem,
    UpdatePriceRequest,
    VariantPriceResponse,
)
from app.shared.audit import record_audit
from app.shared.pagination import Page, PageParams

logger = logging.getLogger(__name__)

PRICING_PERMISSION: Final = "pricing:update"


def _variant_not_found() -> NotFoundError:
    return NotFoundError(message="Variant not found")


def _product_not_found() -> NotFoundError:
    return NotFoundError(message="Product not found")


def _rule(message: str, kind: str) -> BusinessRuleError:
    return BusinessRuleError(message=message, details=[{"type": kind}])


def _merge(current: PriceState, payload: UpdatePriceRequest) -> PriceState:
    """The price after applying the fields sent; removing the sale also removes its window."""
    sent = payload.model_fields_set & set(PRICE_FIELDS)
    merged = replace(current, **{field: getattr(payload, field) for field in sent})
    if "sale_price" in sent and payload.sale_price is None:
        merged = replace(merged, sale_start_at=None, sale_end_at=None)
    return merged


def _check_against_stored(price: PriceState) -> None:
    """Rules that only fail together with the stored price: 422, not 400 (ADR-011)."""
    if price.base_price is None:
        raise _rule("The variant has no base price; send base_price", "base_price_required")
    if price.sale_price is not None and price.sale_price > price.base_price:
        raise _rule("sale_price must not exceed base_price", "sale_above_base")
    if price.sale_price is None and (
        price.sale_start_at is not None or price.sale_end_at is not None
    ):
        raise _rule("A sale window needs sale_price", "window_without_sale")
    start, end = price.sale_start_at, price.sale_end_at
    if start is not None and end is not None and start >= end:
        raise _rule("sale_start_at must be before sale_end_at", "invalid_window")


def _response(variant: ProductVariant) -> VariantPriceResponse:
    return VariantPriceResponse(
        variant_id=variant.id,
        product_id=variant.product_id,
        base_price=variant.base_price,
        sale_price=variant.sale_price,
        sale_start_at=variant.sale_start_at,
        sale_end_at=variant.sale_end_at,
        price_version=variant.price_version,
    )


def _log_change(response: VariantPriceResponse) -> None:
    # After commit, so a rolled-back change is never logged as done.
    logger.info(
        "product_variant.price_changed",
        extra={"variant_id": str(response.variant_id), "price_version": response.price_version},
    )


def _audit_view(price: PriceState, version: int) -> dict[str, Any]:
    return asdict(price) | {"price_version": version}


class PriceService:
    def __init__(self, session: AsyncSession, products: ProductRepository) -> None:
        self._session = session
        self._products = products

    async def update_variant_price(
        self,
        actor: CurrentUser,
        variant_id: UUID,
        payload: UpdatePriceRequest,
        audit_request: Request | None,
    ) -> VariantPriceResponse:
        async with self._session.begin():
            # Product first, then the variant: the lock order of every catalog write (ADR-030).
            product_id = await self._products.variant_product_id(variant_id)
            if product_id is None or await self._products.lock(product_id) is None:
                raise _variant_not_found()
            variant = await self._products.get_variant(variant_id)
            if variant is None:  # deleted while we waited for the product lock
                raise _variant_not_found()
            response = await self._apply(actor, variant, payload, audit_request)
        _log_change(response)
        return response

    async def update_product_price(
        self,
        actor: CurrentUser,
        product_id: UUID,
        payload: UpdatePriceRequest,
        audit_request: Request | None,
    ) -> VariantPriceResponse:
        """Only for a product with exactly one non-deleted variant (D29: no bulk change)."""
        async with self._session.begin():
            if await self._products.lock(product_id) is None:
                raise _product_not_found()
            # Counted under the product lock, which variant create and delete also take.
            variants = await self._products.variants_of(product_id)
            if len(variants) != 1:
                raise _rule(
                    "This product has several variants; change each variant's price",
                    "multiple_variants",
                )
            response = await self._apply(actor, variants[0], payload, audit_request)
        _log_change(response)
        return response

    async def _apply(
        self,
        actor: CurrentUser,
        variant: ProductVariant,
        payload: UpdatePriceRequest,
        audit_request: Request | None,
    ) -> VariantPriceResponse:
        before = PriceState.of(variant)
        after = _merge(before, payload)
        _check_against_stored(after)
        if after == before:
            return _response(variant)  # nothing changed: no history, audit or version bump
        variant.base_price = after.base_price
        variant.sale_price = after.sale_price
        variant.sale_start_at = after.sale_start_at
        variant.sale_end_at = after.sale_end_at
        old_version = variant.price_version
        variant.price_version += 1
        await self._session.flush()
        history = await record_price_change(
            self._session, variant, before=before, actor_id=actor.id, reason=payload.reason
        )
        await record_audit(
            self._session,
            actor_id=actor.id,
            action="product_variant.price_changed",
            entity_type="product_variant",
            entity_id=variant.id,
            before=_audit_view(before, old_version),
            after=_audit_view(after, variant.price_version)
            | {"price_history_id": history.id, "reason": payload.reason},
            request=audit_request,
        )
        return _response(variant)

    async def history(self, product_id: UUID, params: PageParams) -> Page[PriceHistoryItem]:
        """Price changes of a product, deleted ones included (admin view, ADR-030)."""
        async with self._session.begin():
            exists = await self._session.scalar(select(Product.id).where(Product.id == product_id))
            if exists is None:
                raise _product_not_found()
            rows, total = await history_page(
                self._session, product_id, offset=params.offset, limit=params.limit
            )
            items = [PriceHistoryItem.model_validate(row, from_attributes=True) for row in rows]
        return Page.build(items, total=total, params=params)
