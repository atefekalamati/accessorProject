# CNT-04 — Static pages (about, terms, privacy)

**Status:** COMPLETE · **Priority:** LOW · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CNT-00 · **Level:** LOW

## Objective
صفحه ایستا با Markdown و انتشار: `GET /pages/{slug}` عمومی و CRUD ادمین با `content:manage`.

## PRD reference
«درباره برند» ✓، «قوانین و حریم خصوصی» ✓؛ D40 (ADR-053).

## Acceptance Criteria
- [x] جدول `static_pages` با migration جدید؛ slug یکتا بین حذف‌نشده‌ها.
- [x] عمومی فقط منتشرشده؛ پیش‌نویس، حذف‌شده یا ناموجود → 404.
- [x] هر تگ HTML خام → 400؛ متن حداکثر ۵۰٬۰۰۰ کاراکتر.
- [x] slug بعد از ایجاد ثابت است (PATCH با slug → 400)؛ slug تکراری → 409.
- [x] ایجاد، ویرایش و حذف نرم در AuditLog؛ customer → 403.

## Implementation Notes
`app/db/models/content.py`، `app/modules/content/`. متن audit کامل است تا تغییر متن قوانین قابل پیگیری بماند.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-10: صفحه ایستا با Markdown بدون HTML خام: GET /pages/{slug} فقط منتشرشده، CRUD ادمین با content:manage، slug ثابت و 409 تکراری، audit؛ migration 0028. COMPLETE.
