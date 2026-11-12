"""Image validation and re-encoding for uploads (CAT-05, ADR-020, ADR-024, ADR-028).

Every upload is decoded and written again from raw pixels only, so EXIF, XMP, ICC profiles,
comments and text chunks never reach storage and appended payloads (polyglots) are dropped.
The file type comes from magic bytes; the client's filename and Content-Type are ignored.
"""

from __future__ import annotations

import io
import logging
import warnings
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import anyio
from PIL import Image, ImageOps

from app.core.errors import BadRequestError

# "5 MB" in ADR-020 / PRD «محصولات», as exact bytes.
MAX_UPLOAD_BYTES: Final = 5 * 1024 * 1024
# Room for multipart boundaries and part headers on top of the file itself.
MAX_REQUEST_BYTES: Final = MAX_UPLOAD_BYTES + 64 * 1024
MAX_DIMENSION: Final = 6000
# Re-encoding can grow a well-compressed upload; stored files stay under this bound.
MAX_STORED_BYTES: Final = 4 * MAX_UPLOAD_BYTES
MAX_PIXELS: Final = 36_000_000

logger = logging.getLogger("app.media")

# Pillow warns above MAX_IMAGE_PIXELS and raises above twice that; make both fatal.
# Process-wide on purpose: warnings.catch_warnings is not thread-safe under to_thread.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
warnings.simplefilter("error", Image.DecompressionBombWarning)

# Decoding a 6000×6000 image needs ~144 MB; at most two decode at once.
_DECODE_LIMITER: Final = anyio.CapacityLimiter(2)
_JPEG_QUALITY: Final = 85


class ImageType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"

    @property
    def extension(self) -> str:
        return {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[self.value]

    @property
    def pil_format(self) -> str:
        return {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[self.value]


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    data: bytes
    image_type: ImageType
    width: int
    height: int


def invalid_file(message: str) -> BadRequestError:
    return BadRequestError(
        message="Request validation failed",
        details=[{"field": "body.file", "message": message, "type": "value_error"}],
    )


def detect_image_type(head: bytes) -> ImageType | None:
    """Image type from the first bytes of the file only."""
    if head.startswith(b"\xff\xd8\xff"):
        return ImageType.JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ImageType.PNG
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ImageType.WEBP
    return None


def process_image(data: bytes) -> ProcessedImage:
    """Validate ``data`` as a still jpeg/png/webp within the limits and re-encode it."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise invalid_file(f"File is larger than {MAX_UPLOAD_BYTES} bytes")
    image_type = detect_image_type(data[:16])
    if image_type is None:
        raise invalid_file("Only JPEG, PNG and WebP images are accepted")
    try:
        # Only the decoder of the detected type is reachable.
        with Image.open(io.BytesIO(data), formats=[image_type.pil_format]) as image:
            width, height = image.size  # from the header; nothing decoded yet
            if width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
                raise invalid_file(f"Image dimensions exceed {MAX_DIMENSION}px or {MAX_PIXELS}px")
            if getattr(image, "n_frames", 1) > 1:
                raise invalid_file("Animated images are not accepted")
            image.load()
            return _reencode(image, image_type)
    except BadRequestError:
        raise
    except Exception as exc:
        # Decoders and EXIF parsing raise many types on hostile input (OSError, EOFError,
        # struct.error, KeyError, ...); every one of them means "not a usable image".
        logger.debug("media.decode_failed", extra={"error": type(exc).__name__})
        raise invalid_file("File is not a valid image") from None


async def process_image_async(data: bytes) -> ProcessedImage:
    return await anyio.to_thread.run_sync(process_image, data, limiter=_DECODE_LIMITER)


def _reencode(image: Image.Image, image_type: ImageType) -> ProcessedImage:
    oriented = ImageOps.exif_transpose(image)
    if image_type is ImageType.JPEG:
        oriented = oriented.convert("RGB")
    elif oriented.mode not in {"RGB", "RGBA", "L", "LA"}:
        oriented = oriented.convert("RGBA")
    # A fresh image from raw pixels has an empty ``info``: savers fall back to info for
    # icc_profile (PNG) and comment (JPEG), so nothing from the upload can leak through.
    clean = Image.frombytes(oriented.mode, oriented.size, oriented.tobytes())
    output = io.BytesIO()
    if image_type is ImageType.JPEG:
        clean.save(output, "JPEG", quality=_JPEG_QUALITY, optimize=True, icc_profile=None)
    elif image_type is ImageType.PNG:
        clean.save(output, "PNG", optimize=True)
    else:
        clean.save(output, "WEBP", quality=_JPEG_QUALITY, icc_profile=None)
    if output.tell() > MAX_STORED_BYTES:
        raise invalid_file("Image is too large after re-encoding")
    return ProcessedImage(
        data=output.getvalue(), image_type=image_type, width=clean.width, height=clean.height
    )
