# AUTH-04 — SMS provider interface + fake

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** — (D9 مانع نیست؛ provider واقعی در OPS-05 اضافه می‌شود) · **Level:** HIGH

## Objective
ارسال OTP پشت یک interface انجام شود تا auth بدون انتخاب provider جلو برود.

## PRD reference
«هویت و دسترسی» ✓

## Acceptance Criteria
- [ ] `Protocol` `SmsSender` با متد `async send_otp(mobile: str, code: str) -> None` تعریف شده است.
- [ ] `FakeSmsSender` برای dev و test کد را در حافظه نگه می‌دارد (تست‌ها کد را از آن می‌خوانند) و کد کامل را log نمی‌کند.
- [ ] انتخاب پیاده‌سازی از `Settings` انجام می‌شود. با `OTP_MOCK_ENABLED`، کد ثابت `OTP_MOCK_CODE` استفاده می‌شود. validator فعلی mock را در production رد می‌کند.
- [ ] با dependency injection در تست‌ها قابل جایگزینی است.

## Implementation Notes
`app/modules/auth/sms.py` (فایل جدید و برنامه‌ریزی‌شده)، `app/core/config.py`.

## Validation
```powershell
python -m pytest
python -m mypy app tests
```

## Log
