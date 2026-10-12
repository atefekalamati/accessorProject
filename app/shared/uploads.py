"""Bounded multipart/form-data parsing for single-file uploads (CAT-05, ADR-028).

FastAPI's ``File()``/``Form()`` parameters read the whole body before any check, and
Starlette's ``max_part_size`` does not apply to file parts. This parser counts bytes while
streaming and stops as soon as the request exceeds ``max_request_bytes``, so an oversized
body is rejected before it is fully read. File parts spool to a temporary file on disk
above 1 MB and are always closed (deleted) before returning.

Routes using it declare only ``Request`` plus their auth dependencies, so authorization
runs before a single body byte is read.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Collection
from dataclasses import dataclass

from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect, Request

from app.core.errors import BadRequestError
from app.shared.media import MAX_REQUEST_BYTES, MAX_UPLOAD_BYTES

FILE_FIELD = "file"
# Non-file fields are short values (alt text, ids, flags); 1 KiB each is plenty.
_MAX_FIELD_BYTES = 1024


@dataclass(frozen=True, slots=True)
class ParsedUpload:
    data: bytes
    fields: dict[str, str]


def _invalid(field: str, message: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": field, "message": message, "type": "value_error"}],
    )


def _too_large() -> BadRequestError:
    return _invalid("body.file", f"File is larger than {MAX_UPLOAD_BYTES} bytes")


async def _counted(request: Request, max_request_bytes: int) -> AsyncGenerator[bytes, None]:
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > max_request_bytes:
            raise _too_large()
        yield chunk


async def parse_single_file_upload(
    request: Request,
    *,
    allowed_fields: Collection[str] = (),
    max_request_bytes: int = MAX_REQUEST_BYTES,
    max_file_bytes: int = MAX_UPLOAD_BYTES,
) -> ParsedUpload:
    """Read exactly one file part named ``file`` plus optional ``allowed_fields``."""
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise _invalid("header.content-type", "Must be multipart/form-data")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        if not content_length.isdigit():
            raise _invalid("header.content-length", "Must be a non-negative integer")
        if int(content_length) > max_request_bytes:
            raise _too_large()

    parser = MultiPartParser(
        request.headers,
        _counted(request, max_request_bytes),
        max_files=1,
        max_fields=len(allowed_fields),
        max_part_size=_MAX_FIELD_BYTES,
    )
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        raise _invalid("body", exc.message) from None
    except ClientDisconnect:
        # Nobody is left to read the answer; a 400 keeps it out of the server-error logs.
        raise _invalid("body", "Client disconnected during upload") from None
    try:
        files = [value for _, value in form.multi_items() if isinstance(value, UploadFile)]
        unknown = sorted(
            {name for name, value in form.multi_items() if isinstance(value, str)}
            - set(allowed_fields)
        )
        if unknown:
            raise _invalid(f"body.{unknown[0]}", "Unknown field")
        file_names = [name for name, value in form.multi_items() if isinstance(value, UploadFile)]
        if file_names != [FILE_FIELD]:
            raise _invalid("body.file", "Exactly one file in the 'file' field is required")
        upload = files[0]
        if upload.size is not None and upload.size > max_file_bytes:
            raise _too_large()
        data = await upload.read(max_file_bytes + 1)
        if len(data) > max_file_bytes:
            raise _too_large()
        fields = {name: value for name, value in form.multi_items() if isinstance(value, str)}
        return ParsedUpload(data=data, fields=fields)
    finally:
        await form.close()
