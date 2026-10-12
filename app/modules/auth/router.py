from typing import Annotated, Final

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from app.core.errors import UnauthorizedError
from app.core.time import utc_now
from app.modules.auth.dependencies import (
    get_auth_service,
    get_current_user,
    get_otp_service,
    get_profile_service,
)
from app.modules.auth.schemas import (
    ProfileResponse,
    RequestOtpRequest,
    RequestOtpResponse,
    TokenResponse,
    UpdateProfileRequest,
    VerifyOtpRequest,
)
from app.modules.auth.service import (
    AuthService,
    ClientInfo,
    CurrentUser,
    IssuedTokens,
    OtpService,
    ProfileService,
)
from app.shared.audit import client_ip

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])

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


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate the refresh cookie and return a new access token",
)
async def refresh(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> TokenResponse:
    # Read from the cookie only; a token in the body or a header is never accepted.
    if not refresh_token:
        raise UnauthorizedError(message="Invalid or expired session")
    tokens = await service.refresh(refresh_token, _client_info(request), request)
    return _token_response(response, tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current session and clear the refresh cookie",
)
async def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> None:
    # Idempotent: a missing, unknown or already revoked cookie still gets cleared.
    if refresh_token:
        await service.logout(refresh_token, request)
    # Same name and attributes as when set, or the browser keeps the cookie.
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"


@router.get(
    "/me",
    response_model=ProfileResponse,
    summary="The current user's profile, roles and permissions",
)
async def me(
    response: Response,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.get_profile(user)


@users_router.patch(
    "/me",
    response_model=ProfileResponse,
    summary="Complete or edit the current user's name and email",
)
async def update_me(
    payload: UpdateProfileRequest,
    request: Request,
    response: Response,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileResponse:
    response.headers["Cache-Control"] = "no-store"
    # Only fields the client sent; omitted ones stay unchanged.
    changes = payload.model_dump(include=payload.model_fields_set)
    return await service.update_profile(user, changes, request)
