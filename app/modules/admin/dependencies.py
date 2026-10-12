from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.admin.repository import AdminUserRepository
from app.modules.admin.service import AdminUserService
from app.modules.auth.repository import SessionRepository, UserRepository


def get_admin_user_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminUserService:
    return AdminUserService(
        session,
        AdminUserRepository(session),
        UserRepository(session),
        SessionRepository(session),
    )
