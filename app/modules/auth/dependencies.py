from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_app_settings
from app.db.session import get_db_session
from app.modules.auth.repository import OtpRepository, SessionRepository, UserRepository
from app.modules.auth.service import AuthService, OtpService
from app.modules.auth.sms import SmsSender, get_sms_sender


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
