# INF-01 — Error code catalog & domain error classes

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-02, ADR-008, ADR-011 · **Level:** HIGH

## Objective
کدهای خطای ماشینی ثابت (مثل `INSUFFICIENT_STOCK`، `PRICE_CHANGED`، `RESERVATION_EXPIRED`، `OTP_RATE_LIMITED`) و زیرکلاس‌های `AppError` برای 400، 401، 403، 404، 409، 422 و 429، همه مستند در OpenAPI. طبق ADR-011، validation → 400 و نقض قانون کسب‌وکار → 422. طبق ADR-008، 410 استفاده نمی‌شود.

## PRD reference
«معماری سیستم» (خطاهای کلیدی)، «هویت و دسترسی»، «موجودی و رزرو»

## Acceptance Criteria
- [x] فهرست کدهای خطا از شش بخش مرجع PRD در یک ماژول واحد تعریف شده است.
- [x] این کلاس‌ها روی `AppError` موجود ساخته شده‌اند: `UnauthorizedError`، `ForbiddenError`، `NotFoundError`، `ConflictError`، `RateLimitedError` (با هدر `Retry-After`).
- [x] `validation_error_handler` کد **400** با `code: VALIDATION_ERROR` برمی‌گرداند (امروز 422 است). کلاس `BusinessRuleError` کد 422 برمی‌گرداند.
- [x] رزرو منقضی: `ConflictError` با `code: RESERVATION_EXPIRED` (409).
- [x] `responses` در `create_app` به‌روز شده است: 400 = validation، 422 = business rule، به‌علاوه 401، 403، 409 و 429.
- [x] شکل پاسخ خطا تغییر نکرده است. تست جدید وضعیت 400 برای ورودی نامعتبر را پوشش می‌دهد، از جمله فیلد مبلغ `Toman` (float، رشته، bool، منفی) که از INF-02 به اینجا منتقل شد.

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
- 2026-09-29: COMPLETE. `ErrorCode` (StrEnum) و `ERROR_STATUS` (منبع واحد code → status) در `app/core/errors.py`. status همیشه از mapping می‌آید و زیرکلاسی که با آن تناقض داشته باشد `ValueError` می‌دهد. `RateLimitedError` هدر `Retry-After` دارد. validation → 400. دو افزوده به درخواست کاربر: تست کامل‌بودن mapping و تست 500 عمومی (بدون traceback و با `request_id` در log). دو اصلاح جانبی: پاسخ 500 هدر `X-Request-ID` دارد، و `alembic/env.py` با `disable_existing_loggers=False` دیگر loggerهای app را خاموش نمی‌کند. اعتبارسنجی: pytest 217 passed (دیتابیس تست موقت)؛ ruff، format و mypy سبز.
