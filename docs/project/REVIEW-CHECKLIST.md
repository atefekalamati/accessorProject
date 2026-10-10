# REVIEW-CHECKLIST — بررسی plan و diff هر task

منبع: ADR-001 تا ADR-025 و قوانین CLAUDE.md. هر task با Level HIGH، هم در plan و هم در diff نهایی، در برابر این فهرست بررسی می‌شود: اول خودم، بعد یک subagent بازبین مستقل. نتیجه در Log فایل task ثبت می‌شود. موردی که به task ربط ندارد با «N/A» علامت می‌خورد.

## ۱. همزمانی و تراکنش
- [ ] نوشتن همزمان روی یک منبع با `SELECT … FOR UPDATE` یا `pg_advisory_xact_lock` سریال می‌شود (ADR-016، ADR-017، ADR-019، ADR-025). ترتیب گرفتن lock در همه مسیرها یکسان است.
- [ ] invariantهایی که چند ردیف را درگیر می‌کنند (چرخه، آخرین super_admin، oversell) بعد از گرفتن lock بررسی می‌شوند، نه قبل از آن.
- [ ] برای هر مسیر همزمان یک تست همزمانی وجود دارد (`asyncio.gather` روی دو درخواست).
- [ ] موجودی، سفارش و پرداخت تراکنشی‌اند و row lock دارند؛ oversell ممنوع است (CLAUDE.md §۸).

## ۲. احراز هویت و مجوز
- [ ] اول authorization (401/403)، بعد validation؛ `require_permission` یا `require_any_permission` در dependencies (ADR-018).
- [ ] permissionها از دیتابیس خوانده می‌شوند. نقش، قیمت، موجودی یا هر فیلد سیستمی که کلاینت می‌فرستد نادیده گرفته یا رد می‌شود.
- [ ] مرز مجوز در سطح فیلد، روی فیلدهای ارسال‌شده بررسی می‌شود (ADR-023، ADR-025).
- [ ] مالکیت (سفارش، سبد، آدرس) با `ensure_owner` بررسی می‌شود و منبع دیگران 404 می‌گیرد، نه 403.
- [ ] تغییر نقش فقط توسط super_admin؛ حفاظت از آخرین super_admin (ADR-019).

## ۳. ورودی و allowlist
- [ ] همه request bodyها `extra="forbid"` دارند؛ null برای فیلد NOT NULL → 400.
- [ ] query param، sort و filter فقط از allowlist پذیرفته می‌شوند (`allowed_query_params`، `resolve_sort`)؛ page و limit سقف دارند (INF-03).
- [ ] URLهای ورودی فقط `https` روی hostهای allowlist (`MEDIA_ALLOWED_HOSTS`)، بدون user info و port (ADR-025).
- [ ] slug و SKU با الگوی ثابت بررسی می‌شوند، و DB هم CHECK backstop دارد (ADR-021).
- [ ] validation → 400 `VALIDATION_ERROR`؛ قانون کسب‌وکار → 422؛ تعارض وضعیت → 409 (ADR-011).

## ۴. فایل و رسانه
- [ ] نوع فایل با magic bytes تشخیص داده می‌شود: فقط jpeg، png و webp (ADR-020).
- [ ] سقف اندازه (۵MB) قبل از خواندن کامل اعمال می‌شود. ابعاد قبل از decode کامل بررسی و `Image.MAX_IMAGE_PIXELS` تنظیم می‌شود (ADR-024).
- [ ] فایل re-encode می‌شود: EXIF و metadata حذف و polyglot خنثی می‌شود. نام فایل ذخیره‌شده را سرور می‌سازد.
- [ ] storage پشت interface قرار دارد، با fake برای dev و test (ADR-009).

## ۵. داده و soft delete
- [ ] SD rule: read عمومی رکورد soft-deleted را برنمی‌گرداند (detail → 404) و write ارجاع‌دهنده آن را رد می‌کند (ADR-015).
- [ ] unique روی مدل soft-deletable با partial index `WHERE deleted_at IS NULL` (ADR-015).
- [ ] Product و Variant ارجاع‌شده فقط soft delete می‌شوند. FKهای کاتالوگ `RESTRICT` هستند (ADR-021).
- [ ] تغییر schema فقط با migration جدید. مدل جدید در `__init__`، `_MODELS` و `EXPECTED_TABLES` ثبت می‌شود.

## ۶. Audit و log
- [ ] تغییرات حساس (قیمت، موجودی، وضعیت سفارش، نقش، کد تخفیف، کاتالوگ) با `record_audit` و در همان تراکنش ثبت می‌شوند. تغییری که چیزی را عوض نکند audit ندارد.
- [ ] هیچ secret، OTP، token یا PII خامی در log یا audit نیست. ایمیل ماسک می‌شود و `redact` اعمال می‌شود (INF-06، ADR-018).

## ۷. پاسخ و پیکربندی
- [ ] پاسخ‌های حاوی token، PII یا داده admin هدر `Cache-Control: no-store` دارند (ADR-017، ADR-018، ADR-019).
- [ ] شکل خطا ثابت است: `{"error":{"code","message","details"},"request_id"}`.
- [ ] پیکربندی production fail-closed است: setting ناامن یا گم‌شده در `Settings` با خطا متوقف می‌شود. setting جدید placeholder در `.env.example` دارد.

## ۸. پول و idempotency
- [ ] پول عدد صحیح تومان است و float ندارد. گردکردن یک‌بار و فقط در pricing service انجام می‌شود. تبدیل به ریال فقط در adapter درگاه (ADR-001، ADR-014).
- [ ] قیمت و مبلغ فقط در بک‌اند محاسبه می‌شوند. `OrderItem` snapshot دارد.
- [ ] هر جا retry ممکن است (ایجاد سفارش، callback پرداخت، logout و…) عملیات idempotent است و تست idempotency دارد.

## ۹. تست
- [ ] هر endpoint برای همه مسیرهای مرتبط از 400، 401، 403، 404، 409، 422 و 429 تست دارد.
- [ ] منطق خالص (قیمت، تخفیف، موجودی آزاد، URL) unit test دارد.
- [ ] pytest (با دیتابیس تست)، `ruff check`، `ruff format --check` و `mypy app tests` سبز هستند.
