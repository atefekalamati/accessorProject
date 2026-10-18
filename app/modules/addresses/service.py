"""A customer's own shipping addresses (ADDR-01, ADR-045).

Every write takes a per-user advisory lock, so the 10-address cap and the single default
hold under concurrent requests (the partial unique index is the DB backstop). Orders keep
an address snapshot (ORD-01), so editing or deleting an address never changes an order.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessRuleError, NotFoundError
from app.core.time import utc_now
from app.db.models import Address
from app.modules.addresses.schemas import (
    AddressResponse,
    CreateAddressRequest,
    UpdateAddressRequest,
)

MAX_ADDRESSES: Final = 10


def _not_found() -> NotFoundError:
    # Someone else's address looks exactly like a missing one (no 403).
    return NotFoundError(message="Address not found")


def _response(address: Address) -> AddressResponse:
    return AddressResponse.model_validate(address, from_attributes=True)


class AddressService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_own(self, user_id: UUID) -> list[AddressResponse]:
        async with self._session.begin():
            rows = await self._session.scalars(
                select(Address)
                .where(Address.user_id == user_id)
                .order_by(Address.is_default.desc(), Address.created_at.desc(), Address.id)
            )
            return [_response(address) for address in rows]

    async def get_own(self, user_id: UUID, address_id: UUID) -> AddressResponse:
        async with self._session.begin():
            return _response(await self._own(user_id, address_id))

    async def create(self, user_id: UUID, payload: CreateAddressRequest) -> AddressResponse:
        async with self._session.begin():
            await self._lock_user(user_id)
            existing = list(
                await self._session.scalars(select(Address.id).where(Address.user_id == user_id))
            )
            if len(existing) >= MAX_ADDRESSES:
                raise BusinessRuleError(
                    message=f"At most {MAX_ADDRESSES} addresses are allowed",
                    details=[{"field": "body", "type": "address_limit"}],
                )
            # The first address is the default; a new default replaces the old one.
            make_default = payload.is_default or not existing
            if make_default:
                await self._clear_default(user_id)
            address = Address(
                user_id=user_id,
                **payload.model_dump(exclude={"is_default"}),
                is_default=make_default,
            )
            self._session.add(address)
            await self._session.flush()
            return _response(address)

    async def update(
        self, user_id: UUID, address_id: UUID, payload: UpdateAddressRequest
    ) -> AddressResponse:
        sent = payload.model_dump(exclude_unset=True)
        async with self._session.begin():
            await self._lock_user(user_id)
            address = await self._own(user_id, address_id)
            if sent.get("is_default") is True and not address.is_default:
                await self._clear_default(user_id)
            for field, value in sent.items():
                setattr(address, field, value)
            # Bumped even when the same values are resent (onupdate only fires on a change).
            address.updated_at = utc_now()
            await self._session.flush()
            return _response(address)

    async def delete(self, user_id: UUID, address_id: UUID) -> None:
        async with self._session.begin():
            await self._lock_user(user_id)
            address = await self._own(user_id, address_id)
            was_default = address.is_default
            await self._session.delete(address)
            await self._session.flush()
            if was_default:
                # The newest remaining address becomes the default.
                successor = (
                    await self._session.scalars(
                        select(Address)
                        .where(Address.user_id == user_id)
                        .order_by(Address.created_at.desc(), Address.id)
                        .limit(1)
                    )
                ).one_or_none()
                if successor is not None:
                    successor.is_default = True
                    await self._session.flush()

    async def _own(self, user_id: UUID, address_id: UUID) -> Address:
        address = (
            await self._session.scalars(
                select(Address).where(Address.id == address_id, Address.user_id == user_id)
            )
        ).one_or_none()
        if address is None:
            raise _not_found()
        return address

    async def _lock_user(self, user_id: UUID) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"addresses:{user_id}"},
        )

    async def _clear_default(self, user_id: UUID) -> None:
        await self._session.execute(
            update(Address)
            .where(Address.user_id == user_id, Address.is_default.is_(True))
            .values(is_default=False)
        )
