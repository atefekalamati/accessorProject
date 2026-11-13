# پیش‌نویس SEC-00 و OPS-00 — نیازمندی‌های فاز ۵ (منتظر تأیید؛ PRD هنوز ویرایش نشده)

این پیش‌نویس چهار بخش قالبی PRD را با الزامات قابل تست جایگزین می‌کند. هر چهار بخش امروز متن یکسان قالبی دارند و endpointهای قالبی آن‌ها، مثل `GET /security` و `POST /monitoring`، حذف می‌شوند. بعد از تأیید، PRD ویرایش و ✓ می‌شود، ردیف «PRD changes» و ADR ثبت می‌شود، و SEC-01، SEC-02، OPS-01 و OPS-02 طبق همین متن اجرا می‌شوند.

## ۱. «امنیت» ✓ (SEC-00 → SEC-01..04)

**موجود (فقط جمع‌بندی):**
- OTP و refresh token هش‌شده، refresh فقط در cookie امن (ADR-012).
- RBAC از دیتابیس؛ بررسی مالکیت با 404.
- رد فیلدهای سیستمی ارسالی کلاینت؛ redaction در log.
- audit فقط-افزودنی (SEC-04، ADR-059).
- rate limit موضعی برای OTP، کد تخفیف، callback و فرم تماس.

**جدید:**
- **سقف سراسری درخواست (SEC-01):**
  - برای هر IP: ۳۰۰ درخواست در دقیقه روی `/api/v1` (به‌جز `/health` و `/ready`).
  - برای هر کاربر واردشده روی `/admin/*`: ۶۰۰ در دقیقه.
  - همه سقف‌ها از طریق `Settings` قابل تنظیم‌اند.
  - عبور از سقف → 429 `RATE_LIMITED` با `Retry-After`.
  - سقف‌های موضعی موجود سر جایشان می‌مانند.
  - پشت proxy به OPS-04 نیاز دارد (DEFERRED).
- **هدرهای امنیتی (SEC-02)، روی همه پاسخ‌ها:**
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: no-referrer`
  - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` (API فقط JSON برمی‌گرداند)
  - `Permissions-Policy` خالی
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`، فقط در production
- **سقف اندازه بدنه (SEC-02):**
  - پیش‌فرض ۱MB.
  - آپلود رسانه سقف ۵MB خودش را دارد (ADR-024) و callback سقف ۸KB.
  - بیشتر از سقف → 413 با کد جدید `PAYLOAD_TOO_LARGE`، با همان شکل ثابت خطا.
- **مستندات API در production:** `/docs`، `/redoc` و `/openapi.json` خاموش می‌شوند. فایل export در `docs/api/` همچنان مرجع frontend است.
- **مرور امنیتی (SEC-03):**
  - هر endpoint در برابر REVIEW-CHECKLIST بررسی می‌شود.
  - تست IDOR برای هر منبع مالکیت‌دار.
  - تست mass-assignment برای هر write: هر فیلد سیستمی رد یا نادیده گرفته می‌شود.
  - تست tampering قیمت و مبلغ.
  - هر یافته یا رفع می‌شود یا task جدید می‌گیرد.

## ۲. «تست و پذیرش» ✓ (SEC-00)

**معیار آماده بودن نسخه (release readiness)، که دروازه هر فاز همین را بررسی می‌کند:**
- CI سبز: lint، format، mypy strict، suite کامل با PostgreSQL و بدون هیچ تست skip‌شده.
- staging smoke سبز: migrate و seed روی دیتابیس خالی، ورود OTP، write ادمین، خرید end-to-end.
- چرخه migration بالا، پایین، بالا سبز.
- بدون حذف operation از آخرین snapshot OpenAPI (OPS-06).
- تست‌های امنیتی SEC-03 سبز.

**پوشش لازم** همان قواعد CLAUDE.md §۷ است:
- unit برای منطق خالص
- API برای 400، 401، 403، 404، 409، 422 و 429
- همزمانی موجودی
- idempotency سفارش و callback
- یک خرید end-to-end

endpoint ندارد.

## ۳. «حالت‌های رابط» ✓ (SEC-00)

Loading، Empty، Error و Success حالت‌های frontend هستند. سهم بک‌اند تضمین‌های قابل تست زیر است:
- **Empty:** فهرست خالی 200 با `items: []` است، نه 404. منبع ناموجود، پنهان یا مال دیگران → 404.
- **Error:**
  - شکل ثابت `{"error":{"code","message","details"},"request_id"}`.
  - کاتالوگ کدها در OpenAPI و `FRONTEND.md`.
  - 429 همیشه `Retry-After` دارد.
  - 503 یعنی سرویس بیرونی یا دیتابیس در دسترس نیست و تلاش دوباره مجاز است.
- **Success:** پاسخ write منبع کامل را برمی‌گرداند، یا 204 برای حذف.
- `request_id` در هر پاسخ و هر خطاست و برای پیگیری پشتیبانی کافی است.

endpoint ندارد.

## ۴. «پایش و رخدادها» ✓ (OPS-00 → OPS-01، OPS-02، OPS-03)

**log:**
- log ساختاریافته JSON با `request_id`، بدون PII و secret (موجود).
- هر 5xx با `logger.exception` و `request_id` ثبت می‌شود.

**متریک (OPS-01):**
- `GET /metrics` با فرمت متنی Prometheus، بدون dependency جدید.
- محتوا:
  - شمار و مدت درخواست به تفکیک route الگو و status
  - شمار 429
  - نتیجه‌های callback پرداخت
  - تعداد `refund_required` باز
  - آخرین اجرای موفق job تطبیق پرداخت و sweep رزرو
  - آمادگی دیتابیس
- محافظت با `METRICS_TOKEN` (bearer)؛ بدون آن → 404.

**ردیابی خطا (OPS-01):**
- interface `ErrorReporter` با پیاده‌سازی log-only برای dev و test.
- provider واقعی (مثل Sentry) همراه D13 موکول است.

**هشدار (OPS-02):** قواعد هشدار به‌صورت فایل قاعده Prometheus در repo، به‌همراه runbook کوتاه برای هر هشدار:
- نرخ 5xx
- 503 درگاه
- عقب افتادن job تطبیق یا sweep
- `refund_required` باز بیشتر از ۲۴ ساعت
- خطای readiness

اجرای واقعی‌اش به محیط production (D13) بستگی دارد.

**پشتیبان (OPS-03):**
- `pg_dump` روزانه با فرمت custom و نگهداری ۱۴ روز.
- runbook بازیابی.
- تمرین بازیابی روی دیتابیس یک‌بارمصرف (هرگز volume واقعی).

endpointهای قالبی `/monitoring` حذف می‌شوند.

## سؤال‌ها (امنیت و scope)

1. **محل نگهداری شمارنده سقف سراسری:**
   - (الف) حافظه هر پروسه، بدون dependency جدید. سقف per-instance است و با چند instance دقیق نیست. **پیشنهاد من.**
   - (ب) Redis، که زیرساخت و dependency جدید است.
2. **محافظت `/metrics`:** با `METRICS_TOKEN` (پیشنهاد من)، یا فقط شبکه داخلی بدون token؟
3. **مستندات API در production:** `/docs` و `/openapi.json` خاموش شوند؟ (پیشنهاد: بله)
4. **سقف بدنه:** ۱MB پیش‌فرض درست است؟
5. **ردیابی خطا:** interface با پیاده‌سازی log-only الان، و provider واقعی همراه D13 موکول؟ (پیشنهاد: بله)
