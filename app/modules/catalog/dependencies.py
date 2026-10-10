from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_app_settings
from app.db.session import get_db_session
from app.modules.catalog.admin_service import AdminCategoryService
from app.modules.catalog.repository import AdminCategoryRepository, CategoryRepository
from app.modules.catalog.service import CategoryService


def get_category_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CategoryService:
    return CategoryService(session, CategoryRepository(session))


def get_admin_category_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AdminCategoryService:
    return AdminCategoryService(
        session, AdminCategoryRepository(session), settings.media_allowed_hosts
    )
