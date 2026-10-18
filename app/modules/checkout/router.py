from typing import Annotated, Final

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import CurrentUser
from app.modules.checkout.schemas import CheckoutQuoteResponse, CheckoutRequest
from app.modules.checkout.service import CheckoutService
from app.shared.pagination import allowed_query_params

router = APIRouter(prefix="/checkout", tags=["checkout"])

User = Annotated[CurrentUser, Depends(get_current_user)]
_NO_STORE: Final = {"Cache-Control": "no-store"}


def get_checkout_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CheckoutService:
    return CheckoutService(session)


Service = Annotated[CheckoutService, Depends(get_checkout_service)]


@router.post(
    "/validate",
    response_model=CheckoutQuoteResponse,
    summary="Re-check the cart with an address and shipping method; quote with a fingerprint",
    dependencies=[Depends(allowed_query_params())],
)
async def validate_checkout(
    payload: CheckoutRequest, response: Response, user: User, service: Service
) -> CheckoutQuoteResponse:
    response.headers.update(_NO_STORE)
    return await service.validate(user.id, payload.address_id, payload.shipping_method_id)
