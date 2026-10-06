from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_app_settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.db.seed import ALL_PERMISSION_KEYS
from app.db.session import get_db_session
from app.modules.auth.repository import OtpRepository, SessionRepository, UserRepository
from app.modules.auth.service import AccessService, AuthService, CurrentUser, OtpService
from app.modules.auth.sms import SmsSender, get_sms_sender

# auto_error=False: a missing or non-Bearer header must be our 401, not FastAPI's 403.
_bearer = HTTPBearer(auto_error=False)


def get_otp_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    sms_sender: Annotated[SmsSender, Depends(get_sms_sender)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> OtpService:
    return OtpService(session, OtpRepository(session), sms_sender, settings)


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AuthService:
    return AuthService(
        session,
        OtpRepository(session),
        UserRepository(session),
        SessionRepository(session),
        settings,
    )


def get_access_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AccessService:
    return AccessService(session, UserRepository(session), settings)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    service: Annotated[AccessService, Depends(get_access_service)],
) -> CurrentUser:
    """The active user of the bearer access token: 401 when unauthenticated, 403 when
    the account is inactive or blocked."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError(
            message="Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    return await service.authenticate(credentials.credentials)


def require_permission(key: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """A dependency that requires ``key`` among the user's database permissions.

    Unknown keys fail at import time, so a typo cannot silently deny (or allow) access.
    """
    if key not in ALL_PERMISSION_KEYS:
        raise ValueError(f"Unknown permission key: {key!r}")

    async def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if key not in user.permissions:
            raise ForbiddenError(message="Permission denied")
        return user

    return dependency


def ensure_owner(owner_id: UUID | None, user: CurrentUser) -> None:
    """Raise 404 unless ``user`` owns the resource; 404 does not reveal that it exists."""
    if owner_id is None or owner_id != user.id:
        raise NotFoundError(message="Resource not found")
