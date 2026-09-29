# AUTH-05 — POST /api/v1/auth/request-otp with rate limit

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** AUTH-03, AUTH-04, INF-01, INF-06; مسیر طبق ADR-002

## Objective
دریافت شماره موبایل، ساخت و ارسال OTP، با محدودیت نرخ برای هر شماره و هر IP.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [ ] شماره ایران (`09…`، `+989…`، `989…`) به `+989XXXXXXXXX` نرمال می‌شود. شماره نامعتبر → 400 (ADR-011).
- [ ] OTP ۶ رقمی و تصادفی امن (`secrets`) است، **هش‌شده** ذخیره می‌شود و TTL آن `OTP_TTL_SECONDS` (پیش‌فرض 120) است.
- [ ] کدهای مصرف‌نشده قبلی همان شماره باطل می‌شوند.
- [ ] rate limit برای هر شماره و هر IP → **429** با هدر `Retry-After`. شمارش از جدول `otp_codes` در PostgreSQL انجام می‌شود (بدون dependency جدید مثل Redis).
- [ ] پاسخ نشان نمی‌دهد که کاربر وجود دارد یا نه.
- [ ] handler نازک است و منطق در `service.py` قرار دارد.

## Implementation Notes
`app/modules/auth/{router,service,repository,schemas,dependencies}.py` (فایل‌های جدید و برنامه‌ریزی‌شده)، `app/api/v1/router.py`.

## Validation
```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
