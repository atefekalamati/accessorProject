# AUTH-05 — POST /api/v1/auth/request-otp with rate limit

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** AUTH-03, AUTH-04, INF-01, INF-06; مسیر طبق ADR-002 · **Level:** HIGH

## Objective
دریافت شماره موبایل، ساخت و ارسال OTP، با محدودیت نرخ برای هر شماره و هر IP.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [x] شماره ایران (`09…`، `+989…`، `989…`) به `+989XXXXXXXXX` نرمال می‌شود. شماره نامعتبر → 400 (ADR-011).
- [x] OTP ۶ رقمی و تصادفی امن (`secrets`) است، **هش‌شده** ذخیره می‌شود و TTL آن `OTP_TTL_SECONDS` (پیش‌فرض 120) است.
- [x] کدهای مصرف‌نشده قبلی همان شماره باطل می‌شوند.
- [x] rate limit برای هر شماره و هر IP → **429** با هدر `Retry-After`. شمارش از جدول `otp_codes` در PostgreSQL انجام می‌شود (بدون dependency جدید مثل Redis).
- [x] پاسخ نشان نمی‌دهد که کاربر وجود دارد یا نه.
- [x] handler نازک است و منطق در `service.py` قرار دارد.

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
### 2026-10-06 — COMPLETE (batch AUTH-02/05)
- لایه‌های `app/modules/auth/{schemas,repository,service,dependencies,router}.py` و ثبت در `app/api/v1/router.py`.
- `normalize_phone` حالا پیشوند `98…` را هم می‌پذیرد. `client_ip` در `app/shared/audit.py` public شد.
- settingهای جدید با placeholder در `.env.example`: `OTP_RESEND_COOLDOWN_SECONDS=60`، `OTP_MAX_PER_MOBILE_PER_HOUR=5`، `OTP_MAX_PER_IP_PER_HOUR=60`، `OTP_MAX_GLOBAL_PER_HOUR=500` (ADR-016).
- body با `extra="forbid"` است و فیلد اضافه 400 می‌دهد. پاسخ 200 به شکل `{expires_in_seconds, resend_after_seconds}` است و جدول users خوانده نمی‌شود.
- تست‌ها: `tests/test_auth_request_otp.py` (۱۷ مورد) شامل نرمال‌سازی و hash، کد تصادفی، 400، ابطال کد قبلی، cooldown، per-mobile، per-IP، پنجره، سقف سراسری همراه لاگ WARNING، و پنهان‌ماندن وجود کاربر.
- Validation: pytest 426 passed، ruff، format و mypy سبز.
