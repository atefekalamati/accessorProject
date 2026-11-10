# CNT-02 — Admin home sections CRUD (content_manager)

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CNT-01, AUTH-10 · **Level:** MEDIUM

## Objective
`GET/POST/PATCH/DELETE /admin/home/sections` با `content:manage`.

## PRD reference
«صفحه اصلی» ✓؛ D36، D41 (ADR-053).

## Acceptance Criteria
- [ ] `display_order` بین سکشن‌های حذف‌نشده یکتا؛ تداخل → 409.
- [ ] `starts_at` قبل از `ends_at`، عنوان خالی نباشد → 400.
- [ ] مقصد فقط `product`، `category`، `page`، `none`؛ لینک بیرونی → 400؛ ناموجود → 404؛ غیرقابل‌انتشار → 422.
- [ ] متن آیتم Markdown بدون HTML خام → 400.
- [ ] تغییرات در خروجی `GET /home` اعمال می‌شوند؛ هر تغییر در AuditLog؛ SD rule (تست)؛ customer → 403.

## Implementation Notes
`app/modules/content/`؛ ردیف‌ها زیر قفل نوشته می‌شوند.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
