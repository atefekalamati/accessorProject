from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.catalog.repository import CategoryRepository
from app.modules.catalog.service import CategoryService


def get_category_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CategoryService:
    return CategoryService(session, CategoryRepository(session))
