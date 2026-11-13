# مرور امنیتی SEC-03 — 2026-11-13

دامنه: کل API در برابر [REVIEW-CHECKLIST.md](REVIEW-CHECKLIST.md) و قوانین CLAUDE.md §۸، در `feat/phase-5-release` بعد از OPS-02.

روش:
- مرور کد و تست‌ها.
- بازبین مستقل opus.
- محافظ‌های خودکار جدید در `tests/test_security_review.py`. هر route، فیلد id یا write ادمین جدیدی که طبقه‌بندی نشده باشد، این تست را می‌شکند.

**نتیجه:** هیچ آسیب‌پذیری قابل بهره‌برداری پیدا نشد. یک نشت اطلاعات کوچک (F4) به تصمیم کاربر نیاز دارد. سه ریسک استقرار به OPS-04 و OPS-11 (DEFERRED) سپرده شدند.

## شواهد، به ترتیب فهرست بازبینی

### ۱. همزمانی و تراکنش
- رزرو، سفارش و پرداخت: lock ردیف و ترتیب سراسری lock (ADR-048).
- تست‌های رقابت در `test_orders_create.py`، `test_payments_abuse.py` و `test_inventory_*`.
- سقف‌های موضعی (OTP، کد تخفیف، تماس) زیر advisory lock هستند.

### ۲. احراز هویت و مجوز
- **JWT:** فقط HS256، claimهای الزامی و بررسی `typ` (`auth/tokens.py`). هر درخواست وضعیت session، کاربر و مجوزها را از دیتابیس می‌خواند.
- **refresh:** چرخشی است. استفاده دوباره کل خانواده session را باطل می‌کند و کاربر مسدود را رد می‌کند.
- **OTP:** پنج تلاش و سقف‌های موبایل، IP و سراسری. یک خطای واحد `OTP_INVALID` برمی‌گردد، پس امکان شمارش کاربران نیست.
- **ماتریس نقش:** ۵ نقش × همه routeهای ادمین (`test_admin_role_matrix.py`). آخرین super_admin محافظت می‌شود.
- **مالکیت (IDOR):** همه idهای مسیر، query و بدنه routeهای غیرادمین (هر نام `id`، `*_id` یا `*_ids`، در هر سطح schema) در `PATH_PARAMETERS`، `QUERY_IDS` و `BODY_IDS` ثبت شده‌اند و هر کدام به تست مالکیت یا SD rule خودش ارجاع می‌دهد. شاهد اصلی `test_account_ownership.py` است.

### ۳. ورودی و allowlist
- همه schemaهای بدنه JSON، در همه سطح‌ها، `additionalProperties: false` دارند (تست sweep). فیلدهای سیستمی کلاینت حذف یا رد می‌شوند.
- فیلدهای ممتاز روی `/users/me` → 400 (`roles`، `status`، `phone`، `permissions`).
- مبلغ کلاینت در query یا تغییر قیمت → 400 (`test_pricing_security.py`).
- هیچ SQL خامی با ورودی کاربر نیست. تنها f-stringها `int(lock_timeout_ms)` هستند.

### ۴. فایل و رسانه
- magic bytes، سقف اندازه قبل از خواندن، سقف پیکسل، re-encode و حذف EXIF (`shared/media.py`).
- storage پشت interface قرار دارد (OPS-10).

### ۵. داده و soft delete
- SD rule در read و write ارجاع‌دهنده رعایت می‌شود (تست‌های ارجاع‌شده در `BODY_IDS`).
- audit فقط-افزودنی در سطح دیتابیس است (SEC-04).

### ۶. Audit و log
- هر write ادمین در `AUDITED_ADMIN_WRITES` به action خودش نگاشت شده است. route جدید بدون این نگاشت تست را می‌شکند. action باید یک literal در کد (نه کامنت یا docstring) در بسته همان endpoint باشد. استثنا در `AUDIT_PACKAGES` ثبت می‌شود.
- مشاهده مشتری audit `customer.viewed` دارد.
- redaction موبایل و secretها در log فعال است. پیام خطای 500 به کاربر داده نمی‌شود، و `ErrorReporter` فقط نوع خطا را ثبت می‌کند.

### ۷. پاسخ و پیکربندی
- `no-store` روی پاسخ‌های token، داده شخصی و ادمین وجود دارد (تست‌های auth و ماژول‌ها).
- هدرهای امنیتی، سقف بدنه و خاموشی `/docs` در production (SEC-02). سقف سراسری درخواست (SEC-01).
- production fail-closed است: درگاه و SMS fake ساخته نمی‌شوند، storage حافظه‌ای رد می‌شود، و CORS wildcard و mock OTP ممنوع‌اند. routeهای dev و درگاه fake در production mount نمی‌شوند.

### ۸. پول و idempotency
- مبلغ فقط سمت سرور محاسبه می‌شود، به‌صورت عدد صحیح تومان، و ریال فقط در adapter.
- callback پرداخت: مبلغ verify == مبلغ payment == `grand_total`.
- Idempotency-Key به‌ازای کاربر و scope، با hash بدنه.

## یافته‌ها

| # | یافته | شدت | وضعیت |
|---|---|---|---|
| F1 | پشت reverse proxy، سقف‌های per-IP برای همه کاربران مشترک می‌شوند و IP در audit همان proxy است | متوسط (استقرار) | OPS-04، DEFERRED (ADR-043، ADR-060) |
| F2 | نقش دیتابیس برنامه مالک جدول‌هاست و می‌تواند triggerهای audit را بردارد | متوسط (استقرار) | OPS-04، DEFERRED (ADR-059) |
| F3 | اگر استقرار `FORWARDED_ALLOW_IPS=*` بگذارد، `X-Forwarded-For` جعل‌پذیر می‌شود و سقف IP و IP در audit دور زده می‌شوند | متوسط (استقرار) | الان هیچ‌جا تنظیم نشده و تست جلوی آن را می‌گیرد. پیکربندی درست proxy در OPS-04 |
| F4 | `POST /payments/callback` بدون ورود است و به هر کسی که reference درگاه را دارد (در تاریخچه مرورگر هم هست) `order_number` و وضعیت سفارش و پرداخت را برمی‌گرداند | کم (نشت اطلاعات) | **SEC-08، منتظر تصمیم کاربر**: پاسخ فقط `outcome` باشد (تغییر قرارداد frontend، ADR-051)، یا ریسک پذیرفته شود |
| F5 | staging (`ENVIRONMENT=staging`) routeهای dev، درگاه fake و OTP mock دارد. برای staging یک‌بارمصرف CI درست است، ولی برای سرور staging ماندگار نه | کم (استقرار) | OPS-11، DEFERRED با D13 |
| F6 | پاسخ 500 هدرهای امنیتی و CORS ندارد | کم | پذیرفته (ADR-060) |
