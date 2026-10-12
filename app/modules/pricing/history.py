"""Price history rows (PRC-03, ADR-035); shared by the price endpoints and variant creation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceHistory, ProductVariant


@dataclass(frozen=True, slots=True)
class PriceState:
    base_price: int | None
    sale_price: int | None
    sale_start_at: datetime | None
    sale_end_at: datetime | None

    @classmethod
    def of(cls, variant: ProductVariant) -> PriceState:
        return cls(
            base_price=variant.base_price,
            sale_price=variant.sale_price,
            sale_start_at=variant.sale_start_at,
            sale_end_at=variant.sale_end_at,
        )


async def record_price_change(
    session: AsyncSession,
    variant: ProductVariant,
    *,
    before: PriceState | None,
    actor_id: UUID | None,
    reason: str | None = None,
) -> PriceHistory:
    """Add the history row for a price already set on ``variant`` (row locked by the caller).

    ``before`` is ``None`` for the first price of a variant.
    """
    if variant.base_price is None:
        raise ValueError("a price history row needs the new base price")
    old = before or PriceState(None, None, None, None)
    row = PriceHistory(
        product_id=variant.product_id,
        variant_id=variant.id,
        old_base_price=old.base_price,
        new_base_price=variant.base_price,
        old_sale_price=old.sale_price,
        new_sale_price=variant.sale_price,
        old_sale_start_at=old.sale_start_at,
        new_sale_start_at=variant.sale_start_at,
        old_sale_end_at=old.sale_end_at,
        new_sale_end_at=variant.sale_end_at,
        reason=reason,
        changed_by=actor_id,
    )
    session.add(row)
    await session.flush()
    return row


async def history_page(
    session: AsyncSession, product_id: UUID, *, offset: int, limit: int
) -> tuple[Sequence[PriceHistory], int]:
    """A product's price changes, newest first by insertion order (``seq``)."""
    total = await session.scalar(
        select(func.count()).select_from(PriceHistory).where(PriceHistory.product_id == product_id)
    )
    statement = (
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.seq.desc())
        .offset(offset)
        .limit(limit)
    )
    return (await session.scalars(statement)).all(), int(total or 0)
