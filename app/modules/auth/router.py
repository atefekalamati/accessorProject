from typing import Annotated, Final

from fastapi import APIRouter, Depends, Request, Response

from app.core.time import utc_now
from app.modules.auth.dependencies import get_auth_service, get_otp_service
from app.modules.auth.schemas import (
    RequestOtpRequest,
    RequestOtpResponse,
    TokenResponse,
    VerifyOtpRequest,
)
from app.modules.auth.service import AuthService, ClientInfo, IssuedTokens, OtpService
from app.shared.audit import client_ip

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie transport lives only here; services never see HTTP (ADR-012).
REFRESH_COOKIE_NAME: Final = "refresh_token"
REFRESH_COOKIE_PATH: Final = "/api/v1/auth"


def _client_info(request: Request) -> ClientInfo:
    return ClientInfo(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


def _token_response(response: Response, tokens: IssuedTokens) -> TokenResponse:
    max_age = max(0, int((tokens.refresh_expires_at - utc_now()).total_seconds()))
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        tokens.refresh_token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in_seconds=tokens.access_expires_in_seconds,
    )


@router.post(
    "/request-otp",
    response_model=RequestOtpResponse,
    summary="Send a one-time login code to a mobile number",
)
async def request_otp(
    payload: RequestOtpRequest,
    request: Request,
    service: Annotated[OtpService, Depends(get_otp_service)],
) -> RequestOtpResponse:
    return await service.request_otp(payload.mobile, client_ip(request))


@router.post(
    "/verify-otp",
    response_model=TokenResponse,
    summary="Verify a login code; returns an access token and sets the refresh cookie",
)
async def verify_otp(
    payload: VerifyOtpRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    tokens = await service.verify_otp(payload.mobile, payload.code, _client_info(request), request)
    return _token_response(response, tokens)
