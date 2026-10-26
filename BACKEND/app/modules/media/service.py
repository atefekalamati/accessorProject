from __future__ import annotations

import logging
from uuid import UUID

import anyio
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.db.models import Media
from app.modules.auth.service import CurrentUser
from app.shared.audit import record_audit
from app.shared.media import process_image_async
from app.shared.storage import FileStorage, new_storage_key

logger = logging.getLogger("app.media")


class MediaResponse(BaseModel):
    id: UUID
    url: str
    content_type: str
    size_bytes: int
    width: int
    height: int


class MediaService:
    """Stores uploaded images: validate and re-encode, save the file, then record the row."""

    def __init__(self, session: AsyncSession, storage: FileStorage) -> None:
        self._session = session
        self._storage = storage

    async def upload(
        self, actor: CurrentUser, data: bytes, audit_request: Request | None
    ) -> MediaResponse:
        image = await process_image_async(data)
        key = new_storage_key(image.image_type.extension)
        try:
            # Inside the try: a cancellation can land after the file is written.
            await self._storage.save(key, image.data)
            async with self._session.begin():
                media = Media(
                    storage_key=key,
                    content_type=image.image_type.value,
                    size_bytes=len(image.data),
                    width=image.width,
                    height=image.height,
                    created_by=actor.id,
                )
                self._session.add(media)
                await self._session.flush()
                await record_audit(
                    self._session,
                    actor_id=actor.id,
                    action="media.uploaded",
                    entity_type="media",
                    entity_id=media.id,
                    before=None,
                    after={
                        "storage_key": key,
                        "content_type": media.content_type,
                        "size_bytes": media.size_bytes,
                        "width": media.width,
                        "height": media.height,
                    },
                    request=audit_request,
                )
        except BaseException:
            # No row points at the file (failed insert or commit, or a cancelled request):
            # remove it, even while the request is being cancelled.
            with anyio.CancelScope(shield=True):
                await self._storage.delete(key)
            raise
        logger.info("media.uploaded", extra={"media_id": str(media.id), "size": len(image.data)})
        return MediaResponse(
            id=media.id,
            url=self._storage.url(key),
            content_type=media.content_type,
            size_bytes=media.size_bytes,
            width=media.width,
            height=media.height,
        )
