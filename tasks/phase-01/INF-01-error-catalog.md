# INF-01 — Error code catalog & domain error classes

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-02, ADR-008, ADR-011

## Objective
کدهای خطای ماشینی ثابت (مثل `INSUFFICIENT_STOCK`، `PRICE_CHANGED`، `RESERVATION_EXPIRED`، `OTP_RATE_LIMITED`) و زیرکلاس‌های `AppError` برای 400، 401، 403، 404، 409، 422 و 429، همه مستند در OpenAPI. طبق ADR-011، validation → 400 و نقض قانون کسب‌وکار → 422. طبق ADR-008، 410 استفاده نمی‌شود.

## PRD reference
«معماری سیستم» (خطاهای کلیدی)، «هویت و دسترسی»، «موجودی و رزرو»

## Acceptance Criteria
- [ ] فهرست کدهای خطا از شش بخش مرجع PRD در یک ماژول واحد تعریف شده است.
- [ ] این کلاس‌ها روی `AppError` موجود ساخته شده‌اند: `UnauthorizedError`، `ForbiddenError`، `NotFoundError`، `ConflictError`، `RateLimitedError` (با هدر `Retry-After`).
- [ ] `validation_error_handler` کد **400** با `code: VALIDATION_ERROR` برمی‌گرداند (امروز 422 است). کلاس `BusinessRuleError` کد 422 برمی‌گرداند.
- [ ] رزرو منقضی: `ConflictError` با `code: RESERVATION_EXPIRED` (409).
- [ ] `responses` در `create_app` به‌روز شده است: 400 = validation، 422 = business rule، به‌علاوه 401، 403، 409 و 429.
- [ ] شکل پاسخ خطا تغییر نکرده است. تست جدید وضعیت 400 برای ورودی نامعتبر را پوشش می‌دهد، از جمله فیلد مبلغ `Toman` (float، رشته، bool، منفی) که از INF-02 به اینجا منتقل شد.

## Implementation Notes
`app/core/errors.py`، `app/main.py`، `tests/test_errors.py` (فایل جدید و برنامه‌ریزی‌شده).

## Validation
```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
- 2026-09-29: از `tasks/M1-01-error-catalog.md` منتقل شد.
- 2026-09-29: با ADR-008 و ADR-011 از حالت BLOCKED خارج شد.
