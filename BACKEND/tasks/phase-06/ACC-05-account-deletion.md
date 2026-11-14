# ACC-05 — Account deletion: anonymization migration + service (D37)

**Status:** NOT_STARTED · **Priority:** LOW · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** DSC-06 · ORD-08 · **Level:** HIGH

## Objective
مشتری حساب خود را حذف می‌کند. هویت ناشناس می‌شود، ولی سفارش و پرداخت برای حسابداری می‌مانند.

## PRD reference
«پروفایل» ✓ (D37)؛ «هویت و دسترسی» ✓؛ ADR-015، ADR-046، ADR-059، ADR-062.

## Acceptance Criteria
- [x] پیش‌نویس را کاربر تأیید کرد (A1، A3؛ A2 با تغییر: HMAC → DSC-06).
- [x] «پروفایل» ✓ و D37 در DECISIONS به‌روز شد (ADR-063).
- [ ] migration: `users.phone` nullable فقط برای حساب حذف‌شده؛ snapshotهای سفارش ناشناس‌پذیر.
- [ ] سرویس ناشناس‌سازی در یک تراکنش طبق PRD «پروفایل» ✓؛ تست نبود PII.
- [ ] پیش‌شرط‌ها 409 `ACCOUNT_HAS_ACTIVE_ORDERS` و 422 `STAFF_ACCOUNT`.

## Implementation Notes — تأییدشده (ADR-063؛ متن نهایی در PRD «مرجوعی» ✓)
سیاست کاربر (ADR-062): نام، موبایل و آدرس‌ها ناشناس می‌شوند و موبایل برای ثبت‌نام دوباره آزاد می‌شود. سفارش و پرداخت می‌مانند، ولی از هویت جدا می‌شوند. audit می‌ماند و نشست‌ها باطل می‌شوند.
- **تأیید با OTP:** `POST /users/me/deletion/request-otp` (کاربر واردشده؛ کد به موبایل خودش؛ همان سقف‌های OTP و 429) و سپس `POST /users/me/deletion` با `{code}`.
  - OTP یک ستون `purpose` می‌گیرد (`login` یا `account_delete`، با migration)، تا کد ورود برای حذف قابل استفاده نباشد و برعکس.
  - موفق → 204 و پاک‌شدن cookie refresh.
- **پیش‌شرط (→ 409 `ACCOUNT_HAS_ACTIVE_ORDERS`):** حذف رد می‌شود اگر کاربر یکی از این‌ها را داشته باشد:
  - سفارش `pending_payment`
  - سفارش `confirmed` که هنوز `delivered` نشده
  - payment در وضعیت `pending` یا `refund_required`
  - مرجوعی باز (بعد از ORD-08)
- حساب کارمند (هر نقشی غیر از customer) → 422 `STAFF_ACCOUNT`. اول super_admin باید نقش‌ها را بردارد.
- **در یک تراکنش** (با lock ردیف user):
  - user: `deleted_at` و status `deleted`؛ `phone`، `first_name`، `last_name`، `email` و `mobile_verified_at` → NULL. migration: `phone` nullable با CHECK «فقط حساب حذف‌شده بی‌موبایل است». partial unique ADR-015 بدون تغییر.
  - addresses: حذف کامل ردیف‌ها. FK `RESTRICT` است و سفارش‌ها از `order_addresses` snapshot می‌خوانند، نه از addresses.
  - refresh tokenها revoke، سبد و آیتم‌هایش حذف، OTPهای همان موبایل حذف.
  - سفارش‌ها: `user_id` به همان ردیف ناشناس اشاره می‌کند (FK `RESTRICT` می‌ماند). مبالغ، اقلام و payments دست نمی‌خورند.
  - audit `user.deleted` بدون PII. audit logهای قبلی دست نمی‌خورند (ADR-059).
- ثبت‌نام دوباره با همان موبایل یک حساب تازه می‌سازد که سفارش‌های قبلی را نمی‌بیند. حساب حذف‌شده نمی‌تواند وارد شود.
- **A1 — snapshot هویت در سفارش:** `orders.phone` و در `order_addresses` فیلدهای `recipient_name`، `phone`، `address_line` و `postal_code`.
  - (پیشنهاد) ناشناس شوند: NULL یا مقدار ثابت «حذف‌شده». استان و شهر، اقلام و مبالغ می‌مانند. پنل ادمین این‌ها را «حذف‌شده» نشان می‌دهد.
  - (جایگزین) دست‌نخورده بمانند برای اختلاف ارسال یا فاکتور.
- **A2 — موبایل در `discount_redemptions`** (کلید سقف استفاده per-mobile، D31).
  - (پیشنهاد) ناشناس شود. نتیجه: بعد از حذف و ثبت‌نام دوباره، کد «یک‌بار برای هر مشتری» دوباره قابل استفاده است. ریسک کم است، چون حذف خودش پیش‌شرط سخت دارد.
  - (جایگزین) HMAC موبایل با secret نگه داشته شود تا سقف حفظ شود، ولی شبه‌هویت باقی می‌ماند.
- **A3 — پیام‌های تماس** متصل به همین user (`contact_messages.user_id`).
  - (پیشنهاد) نام، موبایل و ایمیل آن‌ها ناشناس شوند و متن پیام بماند. پیام‌های مهمان به حساب متصل نیستند و دست نمی‌خورند.
- شکستن (حدود 5h): ACC-05 migration و سرویس ناشناس‌سازی (3h)، ACC-06 OTP با `purpose` و endpointها و تست‌ها (2h).
- تست‌ها:
  - هر پیش‌شرط 409/422
  - OTP اشتباه، منقضی یا از نوع `login` رد می‌شود
  - ثبت‌نام دوباره با همان موبایل
  - سفارش قبلی برای حساب جدید دیده نمی‌شود و جزئیاتش 404 است
  - هیچ PII در ردیف‌ها و audit باقی نمی‌ماند
  - refresh قدیمی → 401
  - گزارش‌های فروش ادمین بعد از حذف تغییر نمی‌کنند

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: سیاست D37 را کاربر تعیین کرد (ADR-062). پیش‌نویس جزئیات منتظر تأیید است.
- 2026-11-13: کاربر تأیید کرد (A2 با HMAC → DSC-06). شکسته شد: ACC-05 (3h) و ACC-06 (OTP و endpointها، 2h). A2 دیگر بخشی از این task نیست.
