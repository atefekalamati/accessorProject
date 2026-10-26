# AUTH-04 — SMS provider interface + fake

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** — (D9 مانع نیست؛ provider واقعی در OPS-05 اضافه می‌شود) · **Level:** HIGH

## Objective
ارسال OTP پشت یک interface انجام شود تا auth بدون انتخاب provider جلو برود.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [x] `Protocol` `SmsSender` با متد `async send_otp(mobile: str, code: str) -> None` تعریف شده است.
- [x] `FakeSmsSender` برای dev و test کد را در حافظه نگه می‌دارد (تست‌ها کد را از آن می‌خوانند) و کد کامل را log نمی‌کند.
- [x] انتخاب پیاده‌سازی از `Settings` انجام می‌شود. با `OTP_MOCK_ENABLED`، کد ثابت `OTP_MOCK_CODE` استفاده می‌شود. validator فعلی mock را در production رد می‌کند.
- [x] با dependency injection در تست‌ها قابل جایگزینی است.

- [x] (اضافه در تأیید batch) اگر `OTP_MOCK_ENABLED` در production روشن باشد، startup fail می‌شود (fail-closed). تست با env دارد.
- [x] (اضافه در تأیید batch) کد OTP یک رشته ۶ کاراکتری zero-padded است. leading zero تست شده است.

## Implementation Notes
`app/modules/auth/sms.py` (فایل جدید و برنامه‌ریزی‌شده)، `app/core/config.py`.

## Validation
```powershell
python -m pytest
python -m mypy app tests
```

## Log
- 2026-10-06: COMPLETE (batch AUTH-01/03/04).
  - `app/modules/auth/sms.py` شامل این‌هاست:
    - `SmsSender` (Protocol)
    - `FakeSmsSender`: کدها را در `sent` نگه می‌دارد و متد `last_code()` دارد. در log فقط `sms.otp_sent` با موبایل ماسک‌شده ثبت می‌شود.
    - `build_sms_sender(settings)`: بیرون از production، Fake را برمی‌گرداند. در production تا OPS-05 با `RuntimeError` fail-closed می‌شود.
    - dependency `get_sms_sender`: برای هر app یک sender در `app.state` می‌سازد و با `dependency_overrides` قابل جایگزینی است.
  - `generate_otp_code(settings)` در `otp.py`: در حالت mock، `OTP_MOCK_CODE` را برمی‌گرداند. در غیر این صورت `secrets.randbelow(10**6)` را با zero-padding ۶ رقمی برمی‌گرداند.
  - validator موجود mock را در production رد می‌کرد. تست startup از env اضافه شد.
  - هیچ setting جدیدی اضافه نشد.
  - اعتبارسنجی: pytest 403 passed؛ ruff، format و mypy سبز.
