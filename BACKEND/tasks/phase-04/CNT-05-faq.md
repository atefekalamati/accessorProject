# CNT-05 — FAQ

**Status:** NOT_STARTED · **Priority:** LOW · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** CNT-00 · **Level:** LOW

## Objective
پرسش‌های متداول گروه‌بندی‌شده: `GET /faq` عمومی و CRUD ادمین با `content:manage`.

## PRD reference
«سؤالات متداول» ✓؛ D40 (ADR-053).

## Acceptance Criteria
- [ ] جدول `faq_items` با migration جدید.
- [ ] خروجی عمومی فقط منتشرشده‌ها، گروه‌بندی‌شده، با ترتیب پایدار `display_order` و id.
- [ ] HTML خام در پاسخ → 400.
- [ ] ایجاد، ویرایش و حذف نرم در AuditLog؛ customer → 403.

## Implementation Notes
`app/modules/content/`. پاسخ حداکثر ۵٬۰۰۰ کاراکتر (PRD سقفی نگذاشته است).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
