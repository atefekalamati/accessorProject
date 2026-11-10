# CNT-05 — FAQ

**Status:** COMPLETE · **Priority:** LOW · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** CNT-00 · **Level:** LOW

## Objective
پرسش‌های متداول گروه‌بندی‌شده: `GET /faq` عمومی و CRUD ادمین با `content:manage`.

## PRD reference
«سؤالات متداول» ✓؛ D40 (ADR-053).

## Acceptance Criteria
- [x] جدول `faq_items` با migration جدید.
- [x] خروجی عمومی فقط منتشرشده‌ها، گروه‌بندی‌شده، با ترتیب پایدار `display_order` و id.
- [x] HTML خام در پاسخ → 400.
- [x] ایجاد، ویرایش و حذف نرم در AuditLog؛ customer → 403.

## Implementation Notes
`app/modules/content/`. پاسخ حداکثر ۵٬۰۰۰ کاراکتر (PRD سقفی نگذاشته است).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-10: پرسش‌های متداول: GET /faq گروه‌بندی‌شده با ترتیب پایدار، فقط منتشرشده، CRUD ادمین با content:manage، رد HTML خام، audit؛ migration 0029. COMPLETE.
