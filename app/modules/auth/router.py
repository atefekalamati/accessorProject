from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.modules.auth.dependencies import get_otp_service
from app.modules.auth.schemas import RequestOtpRequest, RequestOtpResponse
from app.modules.auth.service import OtpService
from app.shared.audit import client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


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
