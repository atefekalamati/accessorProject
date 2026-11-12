from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.shipping.repository import ShippingRepository
from app.shared.pagination import allowed_query_params

router = APIRouter(prefix="/shipping-methods", tags=["shipping"])


class ShippingMethodResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    # Toman; 0 means always free.
    cost: int
    # Free from this total after discounts, before tax (D34); null means never free.
    free_shipping_threshold: int | None


@router.get(
    "",
    response_model=list[ShippingMethodResponse],
    summary="Active shipping methods in display order",
    dependencies=[Depends(allowed_query_params())],
)
async def list_shipping_methods(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ShippingMethodResponse]:
    async with session.begin():
        methods = await ShippingRepository(session).list_selectable()
        return [
            ShippingMethodResponse.model_validate(method, from_attributes=True)
            for method in methods
        ]
