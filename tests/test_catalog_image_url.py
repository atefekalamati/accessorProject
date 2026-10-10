from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import BadRequestError
from app.modules.catalog.admin_service import check_image_url

ALLOWED = frozenset({"cdn.example.com"})


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.example.com/banners/hair.webp",
        "https://CDN.example.com/a.png",
        "https://cdn.example.com/a.png?v=2#top",
    ],
)
def test_https_url_on_allowed_host_is_accepted(url: str) -> None:
    check_image_url(url, ALLOWED)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)//cdn.example.com",
        "data:image/png;base64,AAAA",
        "http://cdn.example.com/a.png",
        "//cdn.example.com/a.png",
        "/banners/a.png",
        "https://evil.example.org/a.png",
        "https://cdn.example.com.evil.org/a.png",
        "https://sub.cdn.example.com/a.png",
        "https://user@cdn.example.com/a.png",
        "https://cdn.example.com@evil.org/a.png",
        "https://cdn.example.com\\@evil.org/a.png",
        "https://cdn.example.com:8443/a.png",
        "https://cdn.example.com:443/a.png",
        "https://cdn.example.com:bad/a.png",
        "https://cdn.example.com/a b.png",
        "https://cdn.example.com/a\n.png",
        "https://cdn.exämple.com/a.png",
        "https:///a.png",
    ],
)
def test_other_urls_are_rejected_with_400(url: str) -> None:
    with pytest.raises(BadRequestError) as caught:
        check_image_url(url, ALLOWED)

    assert caught.value.status_code == 400
    assert caught.value.details[0]["field"] == "body.image_url"


def test_empty_allowlist_rejects_every_url() -> None:
    with pytest.raises(BadRequestError):
        check_image_url("https://cdn.example.com/a.png", frozenset())


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+asyncpg://user:password@localhost:5432/project_ak",
        "jwt_secret": "test-secret-that-is-at-least-32-characters",
        **overrides,
    }
    return Settings(**values)  # type: ignore[arg-type]


def test_media_allowed_hosts_parses_comma_separated_list() -> None:
    settings = _settings(media_allowed_hosts="cdn.example.com, img.example.org")

    assert settings.media_allowed_hosts == ["cdn.example.com", "img.example.org"]


@pytest.mark.parametrize(
    "hosts", ["https://cdn.example.com", "CDN.example.com", "cdn.example.com/x", "*"]
)
def test_media_allowed_hosts_must_be_bare_lowercase_hosts(hosts: str) -> None:
    with pytest.raises(ValidationError):
        _settings(media_allowed_hosts=hosts)
