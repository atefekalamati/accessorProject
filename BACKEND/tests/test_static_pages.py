"""Static pages: public read, admin CRUD, Markdown rule, audit, access (CNT-04)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from conftest import MakeAccount
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.time import utc_now
from app.db.models import AuditLog, StaticPage
from app.db.models.content import MAX_PAGE_BODY_LENGTH
from app.modules.content.markdown import check_markdown

URL = "/api/v1/admin/pages"
PUBLIC_URL = "/api/v1/pages"


def _slug() -> str:
    return f"page-{uuid4().hex[:10]}"


def _error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()["error"]
    assert body["code"] == code
    return body


# --- Markdown rule (no database) --------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "<script>alert(1)</script>",
        "hello <b>bold</b>",
        "closing </div> only",
        "<!-- comment -->",
        "<?php echo 1 ?>",
        "<img src=x onerror=alert(1)>",
        "`<span>` in code",
        "<https://example.com> autolink",
        "null\x00byte",
    ],
)
def test_html_and_control_characters_are_refused(value: str) -> None:
    with pytest.raises(ValueError):
        check_markdown(value)


@pytest.mark.parametrize(
    "value",
    ["# Title\n\n- item\n", "a < b and c > d", "2<3", "[link](/about)", "tabs\tand\r\nnewlines"],
)
def test_plain_markdown_is_accepted(value: str) -> None:
    assert check_markdown(value) == value


# --- API --------------------------------------------------------------------------------


@pytest.mark.integration
class TestStaticPages:
    @pytest_asyncio.fixture(autouse=True)
    async def _cleanup(self, db_engine: AsyncEngine) -> AsyncIterator[None]:
        started = utc_now()
        yield
        async with AsyncSession(db_engine) as session, session.begin():
            await session.execute(delete(StaticPage).where(StaticPage.created_at >= started))

    @staticmethod
    async def _create(
        client: AsyncClient, headers: dict[str, str], **fields: Any
    ) -> dict[str, Any]:
        body = {"slug": _slug(), "title": "About us", "body": "# Hello"} | fields
        response = await client.post(URL, json=body, headers=headers)
        assert response.status_code == 201, response.text
        created: dict[str, Any] = response.json()
        return created

    @staticmethod
    async def _audits(engine: AsyncEngine, page_id: str) -> list[AuditLog]:
        async with AsyncSession(engine) as session:
            statement = (
                select(AuditLog)
                .where(AuditLog.entity_id == page_id)
                .order_by(AuditLog.created_at, AuditLog.id)
            )
            return list(await session.scalars(statement))

    async def test_create_ignores_system_fields_and_audits(
        self, auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
    ) -> None:
        editor = await make_account("content_manager")
        slug = _slug()
        forged = str(uuid4())

        response = await auth_client.post(
            URL,
            json={
                "slug": slug,
                "title": "  About  ",
                "body": " text ",
                "id": forged,
                "published_at": "2020-01-01T00:00:00Z",
                "created_by": forged,
            },
            headers=editor.headers,
        )

        assert response.status_code == 201, response.text
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["id"] != forged
        assert (body["title"], body["body"], body["status"]) == ("About", "text", "draft")
        assert body["published_at"] is None
        [audit] = await self._audits(db_engine, body["id"])
        assert audit.action == "static_page.created"
        assert audit.actor_user_id == editor.id

    async def test_public_shows_only_published(
        self, auth_client: AsyncClient, make_account: MakeAccount
    ) -> None:
        editor = await make_account("content_manager")
        page = await self._create(auth_client, editor.headers)

        _error(await auth_client.get(f"{PUBLIC_URL}/{page['slug']}"), 404, "NOT_FOUND")

        published = await auth_client.patch(
            f"{URL}/{page['id']}", json={"status": "published"}, headers=editor.headers
        )
        assert published.status_code == 200, published.text
        first_published_at = published.json()["published_at"]
        assert first_published_at is not None

        shown = await auth_client.get(f"{PUBLIC_URL}/{page['slug']}")
        assert shown.status_code == 200
        assert set(shown.json()) == {"slug", "title", "body", "updated_at"}

        for status in ("draft", "published"):
            changed = await auth_client.patch(
                f"{URL}/{page['id']}", json={"status": status}, headers=editor.headers
            )
            assert changed.json()["published_at"] == first_published_at

    @pytest.mark.parametrize("slug", ["unknown-page", "UP", "a"])
    async def test_unknown_or_malformed_slug_is_404(
        self, auth_client: AsyncClient, slug: str
    ) -> None:
        _error(await auth_client.get(f"{PUBLIC_URL}/{slug}"), 404, "NOT_FOUND")

    async def test_raw_html_and_oversized_body_are_400(
        self, auth_client: AsyncClient, make_account: MakeAccount
    ) -> None:
        editor = await make_account("content_manager")
        page = await self._create(auth_client, editor.headers)

        for bad in ("<b>x</b>", "x" * (MAX_PAGE_BODY_LENGTH + 1), "   "):
            body = {"slug": _slug(), "title": "T", "body": bad}
            _error(
                await auth_client.post(URL, json=body, headers=editor.headers),
                400,
                "VALIDATION_ERROR",
            )
            _error(
                await auth_client.patch(
                    f"{URL}/{page['id']}", json={"body": bad}, headers=editor.headers
                ),
                400,
                "VALIDATION_ERROR",
            )

    @pytest.mark.parametrize(
        "body",
        [{}, {"slug": "new-slug-1"}, {"title": None}, {"status": "archived"}, {"nope": 1}],
    )
    async def test_invalid_patch_is_400(
        self, auth_client: AsyncClient, make_account: MakeAccount, body: dict[str, Any]
    ) -> None:
        editor = await make_account("content_manager")
        page = await self._create(auth_client, editor.headers)

        response = await auth_client.patch(f"{URL}/{page['id']}", json=body, headers=editor.headers)

        _error(response, 400, "VALIDATION_ERROR")

    async def test_duplicate_slug_is_409_until_the_page_is_deleted(
        self, auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
    ) -> None:
        editor = await make_account("content_manager")
        page = await self._create(auth_client, editor.headers, slug=_slug())
        body = {"slug": page["slug"], "title": "T", "body": "b"}

        _error(
            await auth_client.post(URL, json=body, headers=editor.headers), 409, "DUPLICATE_SLUG"
        )

        deleted = await auth_client.delete(f"{URL}/{page['id']}", headers=editor.headers)
        assert deleted.status_code == 204
        again = await auth_client.post(URL, json=body, headers=editor.headers)
        assert again.status_code == 201, again.text
        assert [a.action for a in await self._audits(db_engine, page["id"])] == [
            "static_page.created",
            "static_page.deleted",
        ]

    async def test_deleted_page_is_gone_everywhere(
        self, auth_client: AsyncClient, make_account: MakeAccount
    ) -> None:
        editor = await make_account("content_manager")
        page = await self._create(auth_client, editor.headers, status="published")
        await auth_client.delete(f"{URL}/{page['id']}", headers=editor.headers)

        _error(await auth_client.get(f"{PUBLIC_URL}/{page['slug']}"), 404, "NOT_FOUND")
        _error(
            await auth_client.patch(
                f"{URL}/{page['id']}", json={"title": "X"}, headers=editor.headers
            ),
            404,
            "NOT_FOUND",
        )
        _error(
            await auth_client.delete(f"{URL}/{page['id']}", headers=editor.headers),
            404,
            "NOT_FOUND",
        )
        listed = await auth_client.get(URL, headers=editor.headers)
        assert page["id"] not in {item["id"] for item in listed.json()["items"]}

    async def test_unchanged_patch_writes_no_audit(
        self, auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
    ) -> None:
        editor = await make_account("admin")
        page = await self._create(auth_client, editor.headers, title="Same")

        response = await auth_client.patch(
            f"{URL}/{page['id']}", json={"title": "Same"}, headers=editor.headers
        )

        assert response.status_code == 200, response.text
        assert len(await self._audits(db_engine, page["id"])) == 1

    async def test_update_audits_only_the_changed_fields(
        self, auth_client: AsyncClient, make_account: MakeAccount, db_engine: AsyncEngine
    ) -> None:
        editor = await make_account("content_manager")
        page = await self._create(auth_client, editor.headers, title="Old")

        await auth_client.patch(
            f"{URL}/{page['id']}", json={"title": "New", "body": "# Hello"}, headers=editor.headers
        )

        audit = (await self._audits(db_engine, page["id"]))[-1]
        assert audit.action == "static_page.updated"
        assert set(audit.metadata_["diff"]) == {"title"}
        assert audit.metadata_["diff"]["title"]["before"] == "Old"

    async def test_list_filters_by_status_in_slug_order(
        self, auth_client: AsyncClient, make_account: MakeAccount
    ) -> None:
        editor = await make_account("admin")
        prefix = uuid4().hex[:8]
        for suffix, status in (("b", "draft"), ("a", "published"), ("c", "published")):
            await self._create(
                auth_client, editor.headers, slug=f"{prefix}-{suffix}x", status=status
            )

        response = await auth_client.get(
            URL, params={"status": "published", "limit": 100}, headers=editor.headers
        )

        assert response.status_code == 200, response.text
        slugs = [item["slug"] for item in response.json()["items"]]
        assert [slug for slug in slugs if slug.startswith(prefix)] == [
            f"{prefix}-ax",
            f"{prefix}-cx",
        ]
        bad = await auth_client.get(URL, params={"status": "nope"}, headers=editor.headers)
        _error(bad, 400, "VALIDATION_ERROR")

    @pytest.mark.parametrize("role", ["customer", "support"])
    async def test_other_roles_are_403(
        self, auth_client: AsyncClient, make_account: MakeAccount, role: str
    ) -> None:
        account = await make_account(role)

        response = await auth_client.get(URL, headers=account.headers)

        _error(response, 403, "FORBIDDEN")

    async def test_anonymous_is_401(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(URL, json={"slug": _slug(), "title": "T", "body": "b"})

        _error(response, 401, "UNAUTHORIZED")
