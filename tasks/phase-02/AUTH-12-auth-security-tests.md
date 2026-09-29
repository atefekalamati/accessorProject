# AUTH-12 — Auth API & security test suite

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** AUTH-05 … AUTH-11

## Objective
پوشش کامل معیارهای پذیرش «هویت و دسترسی» و سناریوهای سوءاستفاده.

## PRD reference
«هویت و دسترسی» ✓ (معیار پذیرش و تست)

## Acceptance Criteria
- [ ] OTP منقضی یا مصرف‌شده دوباره قابل استفاده نیست.
- [ ] درخواست زیاد OTP → 429.
- [ ] verify موفق، access و refresh معتبر صادر می‌کند.
- [ ] logout، refresh token را باطل می‌کند.
- [ ] کاربر بدون نقش مدیریتی به endpointهای `/admin` دسترسی ندارد (403).
- [ ] Admin نمی‌تواند نقش خود یا دیگران را به Super Admin تغییر دهد.
- [ ] Customer فقط اطلاعات خودش را می‌بیند.
- [ ] تغییرات نقش و وضعیت در Audit Log ثبت شده‌اند.
- [ ] OTP و refresh token در دیتابیس به‌صورت plaintext وجود ندارند (بررسی مستقیم جدول).
- [ ] مسیرهای 400، 401، 403، 404، 409، 422 و 429 پوشش داده شده‌اند.
- [ ] cookie refresh ویژگی‌های `HttpOnly`، `Secure`، `SameSite=Strict` و Path درست را دارد و refresh token در body هیچ پاسخی نمی‌آید.

## Implementation Notes
`tests/test_auth_*.py` (فایل‌های جدید و برنامه‌ریزی‌شده).

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
