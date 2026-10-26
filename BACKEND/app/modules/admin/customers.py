"""Customers for support and admins: list and detail (ADM-03, PRD «مشتریان» ✓, D38).

The list masks the mobile; the detail shows it in full and records each view in the
audit log (``customer.viewed``, ids only). No session, OTP or token data is returned.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import UnaryExpression

from app.core.errors import NotFoundError
from app.core.redaction import mask_phone
from app.db.models import Address, Order, PaymentStatus, Role, User, UserRole, UserStatus
from app.db.models.common import not_deleted
from app.db.session import get_db_session
from app.modules.addresses.schemas import AddressResponse
from app.modules.auth.dependencies import require_permission
from app.modules.auth.service import CUSTOMER_ROLE, CurrentUser
from app.shared.audit import record_audit
from app.shared.idempotency import NO_STORE
from app.shared.pagination import (
    Page,
    PageParams,
    admin_page_params,
    allowed_query_params,
    escape_like,
    paginate,
    resolve_sort,
)
from app.shared.search import invalid_query, is_mobile_search, mobile_digits

RECENT_ORDERS: Final = 10

router = APIRouter(prefix="/admin/customers", tags=["admin-customers"])

CUSTOMER_SORTS: Final[dict[str, tuple[UnaryExpression[Any], ...]]] = {
    "newest": (User.created_at.desc(),),
    "oldest": (User.created_at.asc(),),
}


class AdminCustomerSummaryResponse(BaseModel):
    id: UUID
    first_name: str | None
    last_name: str | None
    # Masked (D38); the detail shows it in full.
    phone: str
    status: str
    order_count: int
    created_at: datetime


class CustomerOrderResponse(BaseModel):
    id: UUID
    order_number: str
    status: str
    payment_status: str
    shipment_status: str
    grand_total: int
    created_at: datetime


class AdminCustomerDetailResponse(BaseModel):
    id: UUID
    phone: str
    first_name: str | None
    last_name: str | None
    email: str | None
    status: str
    mobile_verified_at: datetime | None
    created_at: datetime
    addresses: list[AddressResponse]
    order_count: int
    # Sum of grand_total over successful sales (payment_status = paid, ADR-047), Toman.
    paid_total: int
    recent_orders: list[CustomerOrderResponse]


@dataclass(frozen=True, slots=True)
class CustomerFilters:
    name: str | None = None
    mobile_digits: str | None = None
    status: str | None = None


def _is_customer() -> ColumnElement[bool]:
    return exists().where(
        UserRole.user_id == User.id,
        UserRole.role_id == Role.id,
        Role.name == CUSTOMER_ROLE,
    )


class AdminCustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_customers(
        self,
        filters: CustomerFilters,
        order_by: Sequence[UnaryExpression[Any]],
        paging: PageParams,
    ) -> Page[AdminCustomerSummaryResponse]:
        order_count = select(func.count()).where(Order.user_id == User.id).scalar_subquery()
        criteria: list[ColumnElement[bool]] = [not_deleted(User), _is_customer()]
        if filters.status is not None:
            criteria.append(User.status == filters.status)
        if filters.mobile_digits is not None:
            criteria.append(User.phone.like(f"%{escape_like(filters.mobile_digits)}%", escape="\\"))
        if filters.name is not None:
            pattern = f"%{escape_like(filters.name)}%"
            criteria.append(
                or_(
                    User.first_name.ilike(pattern, escape="\\"),
                    User.last_name.ilike(pattern, escape="\\"),
                )
            )
        statement = select(User, order_count).where(*criteria)
        async with self._session.begin():
            rows, total = await paginate(
                self._session, statement, order_by, tie_breaker=User.id, params=paging
            )
        items = [
            AdminCustomerSummaryResponse(
                id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                phone=mask_phone(user.phone),
                status=user.status,
                order_count=int(count),
                created_at=user.created_at,
            )
            for user, count in rows
        ]
        return Page.build(items, total=total, params=paging)

    async def detail(
        self, actor: CurrentUser, user_id: UUID, request: Request | None
    ) -> AdminCustomerDetailResponse:
        async with self._session.begin():
            user = await self._session.scalar(
                select(User).where(User.id == user_id, not_deleted(User), _is_customer())
            )
            if user is None:
                raise NotFoundError(message="Customer not found")
            addresses = list(
                await self._session.scalars(
                    select(Address)
                    .where(Address.user_id == user.id)
                    .order_by(Address.is_default.desc(), Address.created_at.desc(), Address.id)
                )
            )
            count, paid = (
                await self._session.execute(
                    select(
                        func.count(),
                        func.coalesce(
                            func.sum(Order.grand_total).filter(
                                Order.payment_status == PaymentStatus.PAID
                            ),
                            0,
                        ),
                    ).where(Order.user_id == user.id)
                )
            ).one()
            recent = list(
                await self._session.scalars(
                    select(Order)
                    .where(Order.user_id == user.id)
                    .order_by(Order.created_at.desc(), Order.id.desc())
                    .limit(RECENT_ORDERS)
                )
            )
            # Every view of the full mobile is accountable (D38): ids only, no PII.
            await record_audit(
                self._session,
                actor_id=actor.id,
                action="customer.viewed",
                entity_type="user",
                entity_id=user.id,
                before=None,
                after=None,
                request=request,
            )
        return AdminCustomerDetailResponse(
            id=user.id,
            phone=user.phone,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            status=user.status,
            mobile_verified_at=user.mobile_verified_at,
            created_at=user.created_at,
            addresses=[
                AddressResponse.model_validate(address, from_attributes=True)
                for address in addresses
            ],
            order_count=int(count),
            paid_total=int(paid),
            recent_orders=[
                CustomerOrderResponse(
                    id=order.id,
                    order_number=order.order_number,
                    status=order.status,
                    payment_status=order.payment_status,
                    shipment_status=order.shipment_status,
                    grand_total=order.grand_total,
                    created_at=order.created_at,
                )
                for order in recent
            ],
        )


def get_admin_customer_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminCustomerService:
    return AdminCustomerService(session)


def _search(q: str | None) -> tuple[str | None, str | None]:
    """``q`` as (name text, mobile digits)."""
    if q is None or q.strip() == "":
        return None, None
    q = q.strip()
    if is_mobile_search(q):
        return None, mobile_digits(q, field="q")
    if len(q) < 2:
        raise invalid_query("q", "Must be at least 2 characters")
    return q, None


@router.get(
    "",
    response_model=Page[AdminCustomerSummaryResponse],
    summary="List customers by name or mobile digits and status; mobiles are masked",
    # Authorization first, so an unauthenticated caller learns nothing from validation.
    dependencies=[
        Depends(require_permission("customers:read")),
        Depends(allowed_query_params("page", "limit", "q", "status", "sort")),
    ],
)
async def list_customers(
    paging: Annotated[PageParams, Depends(admin_page_params)],
    service: Annotated[AdminCustomerService, Depends(get_admin_customer_service)],
    q: Annotated[str | None, Query(max_length=60)] = None,
    status: UserStatus | None = None,
    sort: str | None = None,
) -> JSONResponse:
    order_by = resolve_sort(sort, CUSTOMER_SORTS, default="newest")
    name, digits = _search(q)
    filters = CustomerFilters(name=name, mobile_digits=digits, status=status)
    page = await service.list_customers(filters, order_by, paging)
    return JSONResponse(content=page.model_dump(mode="json"), headers=dict(NO_STORE))


@router.get(
    "/{user_id}",
    response_model=AdminCustomerDetailResponse,
    summary="One customer with the full mobile, addresses and recent orders (audited)",
)
async def get_customer(
    actor: Annotated[CurrentUser, Depends(require_permission("customers:read"))],
    _: Annotated[None, Depends(allowed_query_params())],
    user_id: UUID,
    request: Request,
    service: Annotated[AdminCustomerService, Depends(get_admin_customer_service)],
) -> JSONResponse:
    detail = await service.detail(actor, user_id, request)
    return JSONResponse(content=detail.model_dump(mode="json"), headers=dict(NO_STORE))
