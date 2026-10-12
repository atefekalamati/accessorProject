from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.inventory.admin_service import AdminInventoryService


def get_admin_inventory_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminInventoryService:
    return AdminInventoryService(session)
