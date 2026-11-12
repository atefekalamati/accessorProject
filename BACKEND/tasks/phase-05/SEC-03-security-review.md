# SEC-03 — Security review & tests (authz, IDOR, tampering)

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** Phase 3 · **Level:** HIGH

## Objective
مرور امنیتی کل API و تست‌های authz، IDOR و دستکاری فیلدهای سیستمی.

## PRD reference
«معماری سیستم» ✓، «هویت و دسترسی» ✓، CLAUDE.md §۸.

## Acceptance Criteria
- [ ] یافته‌ها رفع یا با task جدید ثبت شدند.
- [ ] تست IDOR و tampering برای هر منبع مالکیت‌دار و هر write ادمین.

## Implementation Notes
بازبین opus (auth و پول).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
