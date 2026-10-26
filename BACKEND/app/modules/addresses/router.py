from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.addresses.schemas import (
    AddressResponse,
    CreateAddressRequest,
    UpdateAddressRequest,
)
from app.modules.addresses.service import AddressService
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import CurrentUser
from app.shared.pagination import allowed_query_params

router = APIRouter(prefix="/addresses", tags=["addresses"])

User = Annotated[CurrentUser, Depends(get_current_user)]
_NO_STORE: Final = {"Cache-Control": "no-store"}


def get_address_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AddressService:
    return AddressService(session)


Service = Annotated[AddressService, Depends(get_address_service)]


@router.get(
    "",
    response_model=list[AddressResponse],
    summary="Your addresses, the default first",
    dependencies=[Depends(get_current_user), Depends(allowed_query_params())],
)
async def list_addresses(response: Response, user: User, service: Service) -> list[AddressResponse]:
    response.headers.update(_NO_STORE)
    return await service.list_own(user.id)


@router.get("/{address_id}", response_model=AddressResponse)
async def get_address(
    address_id: UUID, response: Response, user: User, service: Service
) -> AddressResponse:
    response.headers.update(_NO_STORE)
    return await service.get_own(user.id, address_id)


@router.post(
    "",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an address (at most 10; the first one is the default)",
)
async def create_address(
    payload: CreateAddressRequest, response: Response, user: User, service: Service
) -> AddressResponse:
    response.headers.update(_NO_STORE)
    return await service.create(user.id, payload)


@router.patch("/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: UUID,
    payload: UpdateAddressRequest,
    response: Response,
    user: User,
    service: Service,
) -> AddressResponse:
    response.headers.update(_NO_STORE)
    return await service.update(user.id, address_id, payload)


@router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an address; the newest remaining one becomes the default",
)
async def delete_address(address_id: UUID, user: User, service: Service) -> Response:
    await service.delete(user.id, address_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)
