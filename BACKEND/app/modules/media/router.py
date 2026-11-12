from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_any_permission
from app.modules.auth.service import CurrentUser
from app.modules.media.service import MediaResponse, MediaService
from app.shared.storage import FileStorage, get_file_storage
from app.shared.uploads import parse_single_file_upload

router = APIRouter(prefix="/admin/media", tags=["admin-media"])

# Images not tied to a product (category banners); product images use
# POST /admin/products/{id}/media (CAT-11).
_MEDIA_UPLOADER = require_any_permission("catalog:manage", "categories:edit_content")


def get_media_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> MediaService:
    return MediaService(session, storage)


@router.post(
    "",
    response_model=MediaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one JPEG, PNG or WebP image (multipart field 'file', at most 5 MiB)",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def upload_media(
    request: Request,
    response: Response,
    actor: Annotated[CurrentUser, Depends(_MEDIA_UPLOADER)],
    service: Annotated[MediaService, Depends(get_media_service)],
) -> MediaResponse:
    # The body is read only here, after authentication and the permission check.
    upload = await parse_single_file_upload(request)
    response.headers["Cache-Control"] = "no-store"
    return await service.upload(actor, upload.data, request)
