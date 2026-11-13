# SEC-03 — Security review & tests (authz, IDOR, tampering)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** Phase 3 · **Level:** HIGH

## Objective
مرور امنیتی کل API و تست‌های authz، IDOR و دستکاری فیلدهای سیستمی.

## PRD reference
«معماری سیستم» ✓، «هویت و دسترسی» ✓، CLAUDE.md §۸.

## Acceptance Criteria
- [x] یافته‌ها رفع یا با task جدید ثبت شدند.
- [x] تست IDOR و tampering برای هر منبع مالکیت‌دار و هر write ادمین.

## Implementation Notes
بازبین opus (auth و پول).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: مرور امنیتی کل API در برابر REVIEW-CHECKLIST با بازبین opus روی plan و diff؛ هیچ آسیب‌پذیری قابل بهره‌برداری پیدا نشد؛ محافظ‌های خودکار در tests/test_security_review.py (همه schemaهای بدنه در هر سطح بدون فیلد ناشناخته، registry همه idهای مسیر، query و بدنه با تست مالکیت یا SD rule، registry همه writeهای ادمین با action audit به‌صورت literal کد در بسته endpoint، نبود routeهای dev در production، فیلدهای ممتاز /users/me رد، نبود FORWARDED_ALLOW_IPS=*)؛ گزارش و یافته‌ها در docs/project/SECURITY-REVIEW.md؛ F4 → SEC-08 (BLOCKED، تصمیم کاربر)، F5 → OPS-11 (DEFERRED با D13)، F1 تا F3 → OPS-04. COMPLETE.
