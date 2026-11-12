# CNT-02 — Admin home sections CRUD (content_manager)

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CNT-01, AUTH-10 · **Level:** MEDIUM

## Objective
`GET/POST/PATCH/DELETE /admin/home/sections` با `content:manage`.

## PRD reference
«صفحه اصلی» ✓؛ D36، D41 (ADR-053).

## Acceptance Criteria
- [x] `display_order` بین سکشن‌های حذف‌نشده یکتا؛ تداخل → 409.
- [x] `starts_at` قبل از `ends_at`، عنوان خالی نباشد → 400.
- [x] مقصد فقط `product`، `category`، `page`، `none`؛ لینک بیرونی → 400؛ ناموجود → 404؛ غیرقابل‌انتشار → 422.
- [x] متن آیتم Markdown بدون HTML خام → 400.
- [x] تغییرات در خروجی `GET /home` اعمال می‌شوند؛ هر تغییر در AuditLog؛ SD rule (تست)؛ customer → 403.

## Implementation Notes
`app/modules/content/`؛ ردیف‌ها زیر قفل نوشته می‌شوند.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-11: CRUD ادمین سکشن‌ها با content:manage: قواعد هر نوع سکشن و پنجره زمانی (400)، مقصد فقط داخلی (لینک بیرونی 400، ناموجود یا حذف‌شده 404، غیرعمومی 422)، محصول، دسته و رسانه آیتم هنگام ذخیره بررسی می‌شوند، display_order تکراری 409 (همزمان هم)، items ارسالی جایگزین می‌شوند، audit با آیتم‌ها؛ اثر روی GET /home تست شد. COMPLETE.
