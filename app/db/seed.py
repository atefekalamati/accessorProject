from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Role
from app.db.session import create_database_engine, create_session_factory


@dataclass(frozen=True, slots=True)
class RoleSeed:
    name: str
    description: str


DEFAULT_ROLES: tuple[RoleSeed, ...] = (
    RoleSeed("customer", "Store customer"),
    RoleSeed("admin", "Store administrator"),
    RoleSeed("content_manager", "Content manager"),
    RoleSeed("warehouse_manager", "Warehouse manager"),
    RoleSeed("support", "Customer support agent"),
)


def role_id(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"project-ak:role:{name}")


async def seed_roles(session: AsyncSession, roles: Sequence[RoleSeed] = DEFAULT_ROLES) -> None:
    rows = [
        {
            "id": role_id(role.name),
            "name": role.name,
            "description": role.description,
            "is_system": True,
        }
        for role in roles
    ]
    statement = insert(Role).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[Role.name],
        set_={
            "description": statement.excluded.description,
            "is_system": True,
        },
    )
    await session.execute(statement)


async def seed_database() -> None:
    engine = create_database_engine(get_settings())
    session_factory = create_session_factory(engine)
    try:
        async with session_factory.begin() as session:
            await seed_roles(session)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())
