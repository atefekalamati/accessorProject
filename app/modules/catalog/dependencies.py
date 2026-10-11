from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.catalog.admin_product_service import AdminProductService
from app.modules.catalog.admin_service import AdminCategoryService
from app.modules.catalog.product_repository import ProductRepository
from app.modules.catalog.product_service import ProductService
from app.modules.catalog.repository import AdminCategoryRepository, CategoryRepository
from app.modules.catalog.service import CategoryService
from app.shared.storage import FileStorage, get_file_storage


def get_category_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> CategoryService:
    return CategoryService(session, CategoryRepository(session), storage)


def get_admin_category_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> AdminCategoryService:
    return AdminCategoryService(session, AdminCategoryRepository(session), storage)


def get_admin_product_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> AdminProductService:
    return AdminProductService(session, ProductRepository(session), storage)


def get_product_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> ProductService:
    return ProductService(session, ProductRepository(session), CategoryRepository(session), storage)
