from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path
from typing import Any

import anyio
import pytest
from PIL import Image, PngImagePlugin
from pydantic import ValidationError

from app.core.config import Environment, MediaStorage, Settings
from app.core.errors import BadRequestError
from app.shared.media import (
    MAX_DIMENSION,
    MAX_UPLOAD_BYTES,
    ImageType,
    detect_image_type,
    process_image,
)
from app.shared.storage import InMemoryFileStorage, LocalFileStorage, new_storage_key

SECRET = b"secret-metadata-marker"


def _image(fmt: str, size: tuple[int, int] = (40, 30), mode: str = "RGB", **params: Any) -> bytes:
    output = io.BytesIO()
    Image.new(mode, size, (200, 30, 30) if mode == "RGB" else None).save(output, fmt, **params)
    return output.getvalue()


def _exif() -> Image.Exif:
    exif = Image.Exif()
    exif[0x010E] = SECRET.decode()  # ImageDescription
    exif[0x0112] = 1  # Orientation
    return exif


def _png_header(width: int, height: int) -> bytes:
    """A PNG signature plus a valid IHDR chunk only: Pillow can read the size, not decode."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr))
        + chunk
        + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
    )


def _reject(data: bytes) -> BadRequestError:
    with pytest.raises(BadRequestError) as caught:
        process_image(data)
    assert caught.value.status_code == 400
    assert caught.value.details[0]["field"] == "body.file"
    return caught.value


# --- type detection ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [("JPEG", ImageType.JPEG), ("PNG", ImageType.PNG), ("WEBP", ImageType.WEBP)],
)
def test_detects_type_from_magic_bytes(fmt: str, expected: ImageType) -> None:
    assert detect_image_type(_image(fmt)[:16]) is expected


@pytest.mark.parametrize(
    "data",
    [
        b"GIF89a" + b"\x00" * 20,
        b"%PDF-1.7\n",
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        b"hello world",
        b"",
    ],
    ids=["gif", "pdf", "svg", "text", "empty"],
)
def test_other_files_are_rejected(data: bytes) -> None:
    _reject(data)


def test_gif_image_is_rejected() -> None:
    _reject(_image("GIF"))


def test_magic_bytes_decide_not_the_content_behind_them() -> None:
    _reject(b"\x89PNG\r\n\x1a\n" + _image("JPEG"))


def test_truncated_image_is_rejected() -> None:
    data = _image("JPEG", (400, 300))
    _reject(data[: len(data) // 2])


# Pillow warns about the corruption it tolerates; that is the point of the test.
@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.parametrize("offset", range(0, 60, 3))
def test_corrupted_exif_never_escapes_as_server_error(offset: int) -> None:
    data = bytearray(_image("JPEG", exif=_exif()))
    start = data.index(b"Exif\x00\x00") + 6
    data[start + offset : start + offset + 4] = b"\xff\xff\xff\xff"

    try:
        result = process_image(bytes(data))
    except BadRequestError as exc:
        assert exc.status_code == 400
    else:
        assert SECRET not in result.data


# --- limits --------------------------------------------------------------------------


def test_file_over_size_limit_is_rejected() -> None:
    _reject(_image("PNG") + b"\x00" * MAX_UPLOAD_BYTES)


@pytest.mark.parametrize(
    "size",
    [(MAX_DIMENSION + 1, 10), (10, MAX_DIMENSION + 1), (100_000, 100_000)],
    ids=["too-wide", "too-tall", "decompression-bomb"],
)
def test_oversized_dimensions_are_rejected_from_the_header(size: tuple[int, int]) -> None:
    # The data has no pixel chunks at all: rejection must come before any decoding.
    _reject(_png_header(*size))


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_animated_images_are_rejected(fmt: str) -> None:
    frames = [Image.new("RGB", (20, 20), color) for color in ("red", "blue")]
    output = io.BytesIO()
    frames[0].save(output, fmt, save_all=True, append_images=frames[1:], duration=100, loop=0)

    _reject(output.getvalue())


# --- re-encoding ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "params"),
    [
        ("JPEG", {"exif": _exif(), "icc_profile": SECRET, "comment": SECRET}),
        ("WEBP", {"exif": _exif(), "icc_profile": SECRET, "xmp": SECRET}),
    ],
)
def test_reencode_strips_metadata(fmt: str, params: dict[str, Any]) -> None:
    data = _image(fmt, **params)
    assert SECRET in data

    result = process_image(data)

    assert SECRET not in result.data
    with Image.open(io.BytesIO(result.data)) as reopened:
        assert not set(reopened.info) & {"exif", "icc_profile", "comment", "xmp"}
        assert reopened.getexif().get(0x010E) is None
    assert (result.width, result.height) == (40, 30)


def test_png_text_chunks_and_icc_profile_are_stripped() -> None:
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", SECRET.decode())
    info.add_itxt("XML:com.adobe.xmp", SECRET.decode())
    data = _image("PNG", pnginfo=info, icc_profile=SECRET)
    assert SECRET in data

    result = process_image(data)

    assert SECRET not in result.data
    with Image.open(io.BytesIO(result.data)) as reopened:
        assert "icc_profile" not in reopened.info


def test_polyglot_payload_after_the_image_is_dropped() -> None:
    payload = b"PK\x03\x04" + SECRET
    result = process_image(_image("JPEG") + payload)

    assert payload not in result.data
    assert result.image_type is ImageType.JPEG


def test_exif_orientation_is_applied_before_stripping() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise to display
    result = process_image(_image("JPEG", (40, 30), exif=exif))

    assert (result.width, result.height) == (30, 40)


@pytest.mark.parametrize("mode", ["RGBA", "P", "LA", "CMYK", "I;16"])
def test_unusual_modes_are_reencoded(mode: str) -> None:
    fmt = "JPEG" if mode == "CMYK" else "PNG"
    image = Image.new(mode, (10, 10))
    output = io.BytesIO()
    image.save(output, fmt)

    result = process_image(output.getvalue())

    assert result.width == 10


# --- storage -------------------------------------------------------------------------


async def test_local_storage_writes_atomically_and_deletes(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path, "https://cdn.example.com/media/")
    key = new_storage_key("png")

    await storage.save(key, b"data")

    assert (tmp_path / key).read_bytes() == b"data"
    assert [path.name async for path in anyio.Path(tmp_path).iterdir()] == [key]
    assert storage.url(key) == f"https://cdn.example.com/media/{key}"
    await storage.delete(key)
    await storage.delete(key)  # missing file is fine
    assert not (tmp_path / key).exists()


@pytest.mark.parametrize(
    "key",
    [
        "../evil.png",
        "..\\evil.png",
        "sub/" + "a" * 32 + ".png",
        "A" * 32 + ".png",
        "a" * 32 + ".gif",
        "a" * 32 + ".png/../../x",
        "/etc/passwd",
    ],
)
async def test_storage_rejects_keys_outside_the_server_format(tmp_path: Path, key: str) -> None:
    for storage in (
        LocalFileStorage(tmp_path, "https://x.test"),
        InMemoryFileStorage("https://x.test"),
    ):
        with pytest.raises(ValueError):
            await storage.save(key, b"data")
        with pytest.raises(ValueError):
            storage.url(key)
    assert [path async for path in anyio.Path(tmp_path).iterdir()] == []


# --- settings ------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://user:password@localhost:5432/project_ak",
        "jwt_secret": "test-secret-that-is-at-least-32-characters",
        "otp_hash_secret": "test-otp-hash-secret-at-least-32-characters",
        **overrides,
    }
    return Settings(**values)


def test_default_media_settings_are_valid_for_development() -> None:
    settings = _settings(_env_file=None)

    assert settings.media_storage is MediaStorage.LOCAL
    assert settings.media_public_base_url == "http://localhost:8000/media"


def test_media_allowed_hosts_parses_comma_separated_list() -> None:
    settings = _settings(
        media_allowed_hosts="cdn.example.com, img.example.org",
        media_public_base_url="https://img.example.org/media",
    )

    assert settings.media_allowed_hosts == ["cdn.example.com", "img.example.org"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"media_public_base_url": "https://evil.example.org/media"},
        {"media_public_base_url": "ftp://localhost/media"},
        {"media_public_base_url": "https://user@localhost/media"},
        {"media_public_base_url": "https://localhost/media?x=1"},
        {"media_public_base_url": "/media"},
        {"media_allowed_hosts": "https://cdn.example.com"},
        {"media_allowed_hosts": "CDN.example.com"},
    ],
)
def test_invalid_media_settings_fail_closed(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _settings(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"media_public_base_url": "http://localhost/media"},
        {"media_public_base_url": "https://localhost/media", "media_storage": "memory"},
    ],
)
def test_production_requires_https_media_and_real_storage(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _settings(environment=Environment.PRODUCTION, otp_mock_enabled=False, **overrides)


def test_production_accepts_https_media_on_allowed_host() -> None:
    settings = _settings(
        environment=Environment.PRODUCTION,
        otp_mock_enabled=False,
        media_public_base_url="https://cdn.example.com/media",
        media_allowed_hosts="cdn.example.com",
    )

    assert settings.media_public_base_url.startswith("https://")
