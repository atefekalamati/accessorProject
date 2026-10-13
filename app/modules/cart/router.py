from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.modules.cart.dependencies import get_cart_owner, get_cart_service, get_cart_view
from app.modules.cart.schemas import (
    AddCartItemRequest,
    CartItemResponse,
    CartResponse,
    UpdateCartItemRequest,
)
from app.modules.cart.service import CartOwner, CartService, CartWrite
from app.modules.cart.tokens import set_cart_cookie
from app.modules.cart.view import CartView
from app.shared.pagination import allowed_query_params

router = APIRouter(prefix="/cart", tags=["cart"])

Owner = Annotated[CartOwner, Depends(get_cart_owner)]
Service = Annotated[CartService, Depends(get_cart_service)]
View = Annotated[CartView, Depends(get_cart_view)]
_NO_STORE: Final = {"Cache-Control": "no-store"}


def _respond(response: Response, written: CartWrite) -> None:
    response.headers.update(_NO_STORE)
    if written.guest_token is not None:
        set_cart_cookie(response, written.guest_token)


def _item(written: CartWrite) -> CartItemResponse:
    assert written.item is not None
    return CartItemResponse.model_validate(written.item, from_attributes=True)


@router.get(
    "",
    response_model=CartResponse,
    summary="The cart priced by the server, with price and stock change flags",
    dependencies=[Depends(allowed_query_params())],
)
async def get_cart(response: Response, owner: Owner, view: View) -> CartResponse:
    response.headers.update(_NO_STORE)
    return await view.view(owner)


@router.post(
    "/acknowledge-prices",
    response_model=CartResponse,
    summary="Accept the current prices: clears every line's price-changed flag",
)
async def acknowledge_prices(
    response: Response, owner: Owner, service: Service, view: View
) -> CartResponse:
    token = await service.acknowledge_prices(owner)
    _respond(response, CartWrite(None, token))
    return await view.view(owner)


@router.post(
    "/items",
    response_model=CartItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a variant to the cart (a guest gets a cart cookie); reserves nothing",
)
async def add_cart_item(
    payload: AddCartItemRequest, response: Response, owner: Owner, service: Service
) -> CartItemResponse:
    written = await service.add_item(owner, payload.variant_id, payload.quantity)
    _respond(response, written)
    return _item(written)


@router.patch("/items/{item_id}", response_model=CartItemResponse, summary="Set a line's quantity")
async def update_cart_item(
    item_id: UUID,
    payload: UpdateCartItemRequest,
    response: Response,
    owner: Owner,
    service: Service,
) -> CartItemResponse:
    written = await service.update_item(owner, item_id, payload.quantity)
    _respond(response, written)
    return _item(written)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a line")
async def remove_cart_item(item_id: UUID, owner: Owner, service: Service) -> Response:
    written = await service.remove_item(owner, item_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _respond(response, written)
    return response
