"""Payment endpoints (PAY-02, PAY-03) and the fake gateway's development page."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_app_settings
from app.core.errors import NotFoundError
from app.db.models import FakeGatewaySession
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import CurrentUser
from app.modules.payments.callback import CallbackService, read_body
from app.modules.payments.gateways import get_payment_gateway
from app.modules.payments.gateways.base import PaymentGateway
from app.modules.payments.gateways.fake import FakeGateway
from app.modules.payments.schemas import (
    CallbackResponse,
    FakeCompleteRequest,
    FakeSessionResponse,
    InitPaymentRequest,
    PaymentInitResponse,
)
from app.modules.payments.service import PaymentService
from app.shared.idempotency import NO_STORE, idempotency_key
from app.shared.pagination import allowed_query_params

router = APIRouter(prefix="/payments", tags=["payments"])
fake_gateway_router = APIRouter(prefix="/payments/fake", tags=["development"])


def get_payment_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> PaymentService:
    return PaymentService(session, gateway, settings)


@router.post(
    "/init",
    response_model=PaymentInitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start paying your order; the amount is the order's total (Idempotency-Key)",
)
async def init_payment(
    payload: InitPaymentRequest,
    request: Request,
    # Authentication first, then the query and the header: none answers before 401.
    user: Annotated[CurrentUser, Depends(get_current_user)],
    _: Annotated[None, Depends(allowed_query_params())],
    key: Annotated[str, Depends(idempotency_key)],
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> JSONResponse:
    started = await service.init(user.id, key, payload, request)
    return JSONResponse(
        status_code=started.status_code, content=started.body, headers=dict(NO_STORE)
    )


@router.post(
    "/callback",
    response_model=CallbackResponse,
    summary="The gateway's notice; verified with the gateway before anything changes",
)
async def payment_callback(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> JSONResponse:
    # Size-capped while it is read; its shape is the adapter's business.
    payload = await read_body(request)
    applied = await CallbackService(session, gateway, settings).handle(payload, request)
    body = CallbackResponse(
        outcome=applied.outcome.value,
        order_number=applied.order_number,
        order_status=applied.order_status,
        order_payment_status=applied.order_payment_status,
        payment_status=applied.payment_status,
    )
    return JSONResponse(content=body.model_dump(mode="json"), headers=dict(NO_STORE))


def _fake(gateway: PaymentGateway) -> FakeGateway:
    if not isinstance(gateway, FakeGateway):
        raise NotFoundError(message="Not found")
    return gateway


@fake_gateway_router.get(
    "/{reference}",
    response_model=FakeSessionResponse,
    summary="The fake gateway's page (development only)",
)
async def fake_page(
    reference: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
) -> FakeSessionResponse:
    _fake(gateway)
    fake = await session.get(FakeGatewaySession, reference)
    if fake is None:
        raise NotFoundError(message="Unknown payment session")
    return FakeSessionResponse(reference=fake.reference, status=fake.status)


@fake_gateway_router.post(
    "/{reference}/complete",
    response_model=FakeSessionResponse,
    summary="Pay or abandon a fake gateway session (development only)",
)
async def fake_complete(
    reference: str,
    payload: FakeCompleteRequest,
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
) -> FakeSessionResponse:
    fake = _fake(gateway)
    paid = payload.result == "paid"
    if not await fake.complete(reference, paid=paid, amount_rial=payload.amount_rial):
        raise NotFoundError(message="Unknown, finished or expired payment session")
    return FakeSessionResponse(reference=reference, status=payload.result)
