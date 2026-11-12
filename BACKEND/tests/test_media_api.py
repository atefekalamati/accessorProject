from __future__ import annotations

import io
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import AuditLog, Media, OtpCode, User, UserRole
from app.db.seed import role_id
from app.shared.media import MAX_REQUEST_BYTES, MAX_UPLOAD_BYTES
from app.shared.storage import InMemoryFileStorage

pytestmark = pytest.mark.integration

MEDIA_URL = "/api/v1/admin/media"
MEDIA_BASE_URL = "https://cdn.example.com/media"  # settings fixture in conftest
Headers = dict[str, str]


def _image(fmt: str = "PNG", size: tuple[int, int] = (40, 30)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(output, fmt)
    return output.getvalue()


def _storage(client: AsyncClient) -> InMemoryFileStorage:
    storage = client._transport.app.state.file_storage  # type: ignore[attr-defined]
    assert isinstance(storage, InMemoryFileStorage)
    return storage


@pytest_asyncio.fixture
async def login(
    auth_client: AsyncClient,
    issue_otp: Callable[..., Awaitable[OtpCode]],
    db_engine: AsyncEngine,
) -> AsyncIterator[Callable[..., Awaitable[Headers]]]:
    mobiles: list[str] = []

    async def _login(*roles: str) -> Headers:
        mobile = f"+989{uuid4().int % 1_000_000_000:09d}"
        mobiles.append(mobile)
        await issue_otp(mobile)
        response = await auth_client.post(
            "/api/v1/auth/verify-otp", json={"mobile": mobile, "code": "123456"}
        )
        async with AsyncSession(db_engine) as session, session.begin():
            user_id = (await session.scalars(select(User.id).where(User.phone == mobile))).one()
            await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
            session.add_all(UserRole(user_id=user_id, role_id=role_id(name)) for name in roles)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    yield _login
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(User).where(User.phone.in_(mobiles)))


@pytest_asyncio.fixture
async def uploaded(db_engine: AsyncEngine) -> AsyncIterator[list[UUID]]:
    ids: list[UUID] = []
    yield ids
    async with AsyncSession(db_engine) as session, session.begin():
        await session.execute(delete(Media).where(Media.id.in_(ids)))


async def _upload(
    client: AsyncClient,
    headers: Headers,
    *,
    uploaded: list[UUID] | None = None,
    **kwargs: Any,
) -> Response:
    if not kwargs:
        kwargs = {"files": {"file": ("photo.png", _image(), "image/png")}}
    response = await client.post(MEDIA_URL, headers=headers, **kwargs)
    if response.status_code == 201 and uploaded is not None:
        uploaded.append(UUID(response.json()["id"]))
    return response


def _error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


# --- authorization -------------------------------------------------------------------


async def test_upload_needs_authentication_before_reading_the_body(
    auth_client: AsyncClient,
) -> None:
    big: dict[str, Any] = {
        "files": {"file": ("x.png", b"\x00" * (MAX_REQUEST_BYTES + 1), "image/png")}
    }

    response = await _upload(auth_client, {}, **big)

    _error(response, 401, "UNAUTHORIZED")


@pytest.mark.parametrize("roles", [("customer",), ("support",), ()])
async def test_upload_is_forbidden_without_catalog_permissions(
    auth_client: AsyncClient, login: Callable[..., Awaitable[Headers]], roles: tuple[str, ...]
) -> None:
    headers = await login(*roles)
    big: dict[str, Any] = {
        "files": {"file": ("x.png", b"\x00" * (MAX_REQUEST_BYTES + 1), "image/png")}
    }

    _error(await _upload(auth_client, headers, **big), 403, "FORBIDDEN")
    assert _storage(auth_client).files == {}


# --- success -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "fmt", "content_type"),
    [
        ("admin", "PNG", "image/png"),
        ("admin", "JPEG", "image/jpeg"),
        ("content_manager", "WEBP", "image/webp"),
    ],
)
async def test_upload_stores_reencoded_image_with_audit(
    auth_client: AsyncClient,
    db_engine: AsyncEngine,
    login: Callable[..., Awaitable[Headers]],
    uploaded: list[UUID],
    role: str,
    fmt: str,
    content_type: str,
) -> None:
    headers = await login(role)
    # Client filename and Content-Type are ignored; the magic bytes decide.
    files = {"file": ("../../evil.exe", _image(fmt), "text/html")}

    response = await _upload(auth_client, headers, uploaded=uploaded, files=files)

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["content_type"], body["width"], body["height"]) == (content_type, 40, 30)
    key = body["url"].removeprefix(f"{MEDIA_BASE_URL}/")
    assert key.endswith("." + {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt])
    assert "evil" not in key
    stored = _storage(auth_client).files[key]
    assert len(stored) == body["size_bytes"]
    async with AsyncSession(db_engine) as session:
        media = await session.get(Media, UUID(body["id"]))
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "media.uploaded", AuditLog.entity_id == UUID(body["id"])
            )
        )
    assert media is not None and media.storage_key == key
    assert audit is not None


# --- rejected requests ---------------------------------------------------------------


async def test_body_over_limit_by_content_length_is_400(
    auth_client: AsyncClient, login: Callable[..., Awaitable[Headers]]
) -> None:
    headers = await login("admin")
    big: dict[str, Any] = {
        "files": {"file": ("x.png", b"\x00" * (MAX_REQUEST_BYTES + 1), "image/png")}
    }

    _error(await _upload(auth_client, headers, **big), 400, "VALIDATION_ERROR")


async def test_streamed_body_over_limit_without_content_length_is_400(
    auth_client: AsyncClient, login: Callable[..., Awaitable[Headers]]
) -> None:
    headers = await login("admin")
    boundary = "boundary123"
    sent = 0

    async def body() -> AsyncIterator[bytes]:
        nonlocal sent
        yield (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            'filename="x.png"\r\nContent-Type: image/png\r\n\r\n'
        ).encode()
        chunk = b"\x00" * 65536
        for _ in range(MAX_REQUEST_BYTES // len(chunk) + 50):
            sent += len(chunk)
            yield chunk

    response = await auth_client.post(
        MEDIA_URL,
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
        content=body(),
    )

    _error(response, 400, "VALIDATION_ERROR")
    # Reading stopped at the cap instead of consuming the whole stream.
    assert sent < MAX_REQUEST_BYTES + 2 * 65536


async def test_file_one_byte_over_limit_is_400(
    auth_client: AsyncClient, login: Callable[..., Awaitable[Headers]]
) -> None:
    headers = await login("admin")
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_UPLOAD_BYTES + 1 - 8)
    assert len(data) == MAX_UPLOAD_BYTES + 1 < MAX_REQUEST_BYTES

    response = await _upload(auth_client, headers, files={"file": ("x.png", data, "image/png")})

    _error(response, 400, "VALIDATION_ERROR")
    assert response.json()["error"]["details"][0]["field"] == "body.file"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"files": [("file", ("a.png", _image())), ("file", ("b.png", _image()))]},
        {"files": {"image": ("a.png", _image())}},
        {"files": {"file": ("a.png", _image())}, "data": {"alt_text": "x"}},
        {"data": {"file": "not a file"}},
        {"json": {"file": "x"}},
        {"content": b"raw", "headers": {"Content-Type": "image/png"}},
        {"files": {"file": ("a.png", b"GIF89a....")}},
        {"files": {"file": ("a.svg", b"<svg onload='alert(1)'/>")}},
    ],
    ids=[
        "two-files",
        "wrong-field-name",
        "extra-field",
        "no-file",
        "json",
        "raw-body",
        "gif",
        "svg",
    ],
)
async def test_invalid_uploads_are_400(
    auth_client: AsyncClient,
    login: Callable[..., Awaitable[Headers]],
    kwargs: dict[str, Any],
) -> None:
    headers = await login("admin")
    extra_headers = kwargs.pop("headers", {})

    response = await _upload(auth_client, {**headers, **extra_headers}, **kwargs)

    _error(response, 400, "VALIDATION_ERROR")
    assert _storage(auth_client).files == {}


async def test_malformed_multipart_is_400(
    auth_client: AsyncClient, login: Callable[..., Awaitable[Headers]]
) -> None:
    headers = await login("admin")

    response = await auth_client.post(
        MEDIA_URL,
        headers={**headers, "Content-Type": "multipart/form-data"},  # no boundary
        content=b"--x\r\n",
    )

    _error(response, 400, "VALIDATION_ERROR")


# --- failure after the file is stored ------------------------------------------------


async def test_stored_file_is_removed_when_the_database_write_fails(
    auth_client: AsyncClient,
    login: Callable[..., Awaitable[Headers]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await login("admin")

    async def failing_audit(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("audit write failed")

    monkeypatch.setattr("app.modules.media.service.record_audit", failing_audit)

    with pytest.raises(RuntimeError, match="audit write failed"):
        await _upload(auth_client, headers)

    assert _storage(auth_client).files == {}
