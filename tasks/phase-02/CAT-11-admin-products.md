# CAT-11 — Admin product/variant/media CRUD + publish rules

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** CAT-03, CAT-05, AUTH-10, PRC-01, INV-01, INV-03 · **Level:** HIGH

## Objective
۱۲ endpoint بخش «محصولات» ✓ (پنل مدیریت): محصول، تنوع و رسانه محصول، گراف وضعیت انتشار با `publish_blockers`، قیمت اولیه تنوع با `pricing:update`، و audit همه نوشتن‌ها. بدون تغییر schema.

## PRD reference
«محصولات» ✓ (خط 5843–6078: قوانین کسب‌وکار، ورودی/خروجی، APIها، خطاها، دسترسی، معیار پذیرش)؛ ADR-011، ADR-015، ADR-018، ADR-020، ADR-021، ADR-027، ADR-028، ADR-029؛ CAT-00 جدول خلاصه.

## Acceptance Criteria
- [x] همه endpointها `catalog:manage` (401/403 قبل از validation) و `Cache-Control: no-store`؛ content_manager، support و customer → 403.
- [x] `GET /admin/products`: `page`، `limit` (≤100)، `q` (۱..۱۰۰؛ ILIKE با escape روی title، slug و SKU تنوع حذف‌نشده)، `status`، `category_id`، `sort` (`newest`|`oldest`|`title`، tie-break با `id`)؛ پارامتر ناشناخته → 400. آیتم: id، title، slug، status، category (id، title)، `active_variant_count`، `price_range` (min/max `base_price` تنوع‌های فعال؛ null)، `main_image_url`، `updated_at`. soft-deleted نمی‌آید. بدون N+1 (یک کوئری page + کوئری‌های batch).
- [x] `GET /admin/products/{id}`: فیلدهای محصول، `attributes`، تنوع‌ها (حذف‌نشده، با options، همه فیلدهای قیمت، `stock` شامل total/reserved/free/threshold/status از INV-03؛ بدون InventoryItem → out)، رسانه‌ها (با url)، `publish_blockers`. soft-deleted → 404.
- [x] `POST /admin/products`: همیشه draft؛ فیلدهای سیستمی (`id`، `status`، `published_at`، `created_by`، `updated_by`، `created_at`، `updated_at`، `deleted_at`) نادیده گرفته می‌شوند و بقیه کلیدهای ناشناخته → 400. slug تکراری → 409 `DUPLICATE_SLUG`؛ دسته ناموجود/حذف‌شده → 404؛ attributes حداکثر ۵۰ با کلید یکتا.
- [x] `PATCH /admin/products/{id}`: partial؛ attributes کل مجموعه را جایگزین می‌کند؛ null برای فیلد NOT NULL، بدنه خالی یا `status` → 400؛ مقادیر برابر فعلی → 200 بدون audit؛ `updated_by` ست می‌شود.
- [x] `PATCH /admin/products/{id}/status`: گراف PRD؛ غیرمجاز → 422 `INVALID_STATE_TRANSITION`؛ همان وضعیت → 200 بدون audit؛ انتشار با blocker → 422 `BUSINESS_RULE_VIOLATION` و فهرست blockerها در `details`؛ `published_at` فقط در اولین انتشار.
- [x] `DELETE /admin/products/{id}`: soft delete محصول و همه تنوع‌هایش، یک audit `product.deleted` (با `variant_ids`)، 204؛ بعد از آن detail و writeها 404 و از لیست حذف (SD rule).
- [x] `POST /admin/products/{id}/variants`: SKU trim+upper (فرمت → 400، تکراری → 409 `CONFLICT`)؛ options فقط color/size/model (۱..۵۰)؛ ترکیب تکراری (شامل تنوع بدون گزینه) → 409؛ قیمت اولیه فقط با `pricing:update` (وگرنه 403)، `1 ≤ base ≤ 10^12`، `sale ≤ base`، بازه معتبر و فقط با sale (→ 400)؛ فعال بدون base → 422.
- [x] `PATCH /admin/product-variants/{id}`: sku، options (جایگزینی کامل)، display_order، is_active، is_purchasable؛ فیلدهای قیمت و سیستمی نادیده گرفته می‌شوند؛ فعال‌کردن بدون قیمت → 422؛ غیرفعال‌کردن آخرین تنوع فعال محصول published → 422.
- [x] `DELETE /admin/product-variants/{id}`: soft delete؛ آخرین تنوع فعال محصول published → 422؛ 204.
- [x] `POST /admin/products/{id}/media` (multipart: `file`، `alt_text`، `variant_id`، `display_order`، `is_main`): همان پردازش CAT-05 (magic bytes، ۵MB، re-encode)؛ اولین تصویر خودکار اصلی؛ `is_main=true` قبلی را در همان تراکنش برمی‌دارد؛ `variant_id` غیر از تنوع حذف‌نشده همان محصول → 422؛ شکست DB → حذف فایل.
- [x] `PATCH /admin/products/{id}/media/{mediaId}`: alt_text، display_order، is_main، variant_id؛ برداشتن `is_main` از تصویر اصلی → 422 (تعیین اصلی جدید با `is_main=true` روی تصویر دیگر).
- [x] `DELETE /admin/products/{id}/media/{mediaId}`: حذف ProductMedia و Media؛ فایل بعد از commit از storage حذف می‌شود. حذف تصویر اصلی وقتی تصویر دیگری هست، یا وقتی محصول published است → 422.
- [x] قفل: هر نوشتن روی محصول، تنوع یا رسانه اول ردیف Product را `FOR UPDATE` می‌گیرد و invariantها بعد از lock بررسی می‌شوند. تست همزمانی: انتشار هم‌زمان با غیرفعال‌کردن آخرین تنوع فعال، محصول published بدون تنوع فعال باقی نمی‌گذارد.
- [x] audit با before/after برای ۱۰ action PRD؛ تغییر بی‌اثر audit ندارد.
- [x] تست‌ها برای هر endpoint: 400/401/403/404/409/422 مرتبط؛ ADR-030 برای تصمیم‌های کم‌اثر.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد جدید: `app/modules/catalog/admin_product_schemas.py`، `admin_product_service.py`، `admin_product_router.py`، `product_repository.py`؛ به‌روزرسانی `dependencies.py` و `app/api/v1/router.py`. رسانه از `parse_single_file_upload(allowed_fields=...)`، `process_image_async`، `new_storage_key` و `FileStorage` استفاده می‌کند.
- تست‌ها: `tests/test_admin_products.py` (یک فایل با fixtureهای مشترک؛ نقش آزمایشی فقط با `catalog:manage` برای مسیر 403 قیمت). پردازش تصویر (EXIF، magic bytes با پسوند مجاز، ۵MB) همان `process_image_async`/`parse_single_file_upload` است و در `tests/test_media_processing.py` و `tests/test_media_api.py` (CAT-05) پوشش دارد.
- ترتیب lock یکسان: Product → (Variant/Media). مسیرهای variant اول `product_id` را بدون lock می‌خوانند، Product را lock می‌کنند و بعد variant را دوباره می‌خوانند.
- **ریسک‌ها:** انتشار همزمان با حذف آخرین تنوع/تصویر اصلی (lock Product + تست همزمانی)؛ دو تصویر اصلی (partial unique + flush برداشتن قبلی قبل از ست جدید)؛ نشت فیلد سیستمی یا قیمت بدون مجوز (strip صریح + 403 روی فیلدهای ارسال‌شده)؛ ترکیب گزینه تکراری (بررسی زیر lock محصول)؛ SKU همزمان در دو محصول (partial unique → 409)؛ فایل یتیم (حذف در شکست، حذف فایل فقط بعد از commit)؛ LIKE injection در `q` (escape).
- **Rollback:** بدون schema؛ `git revert`. routerها مستقل‌اند و حذفشان رفتار دیگری را تغییر نمی‌دهد.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: بعد از INV-01/INV-03 (وضعیت موجودی تنوع در جزئیات admin).
- 2026-10-10: بازبینی plan توسط subagent مستقل: APPROVE WITH CHANGES، بدون blocker و بدون مورد ارجاع به کاربر. اعمال شد: `FOR SHARE` روی دسته در ایجاد/تغییر دسته/انتشار، جداکردن رسانه از تنوع حذف‌شده، pre-check تنوع در PATCH رسانه، ترتیب upload و پاک‌سازی فایل، swap تصویر اصلی با UPDATE صریح و backstop 409، backstopهای slug/SKU، سه تست همزمانی اضافه، `EXISTS` برای SKU، sort با `created_at`، رد `status` در PATCH محصول، 403 قیمت روی فیلدهای ارسال‌شده. ADR-030 ثبت شد.
- 2026-10-10: بازبینی diff توسط subagent مستقل: APPROVE WITH CHANGES. اعمال شد: باگ audit «after» هنگام خالی‌کردن attributes/options (falsy)، حذف فایل best-effort و shielded که خطای اصلی را پنهان نکند، `alt_text` خالی → null، تست محتوای audit (title، attributes، options، media_ids، replaced_main، published_at). مستند در ADR-030: بدنه خالی مؤثر → 400، دسته حذف‌شده در لیست admin. چک‌لیست: §1 (lock Product + FOR SHARE دسته، ۴ تست همزمانی)، §2 (require_permission، 403 قیمت روی فیلد ارسال‌شده)، §3 (extra=forbid + strip فیلد سیستمی، allowlist query، الگوی slug/SKU)، §4 (همان مسیر CAT-05)، §5 (SD rule)، §6 (۱۰ action با before/after، no-op بدون audit)، §7 (no-store)، §8 (BIGINT تومان، `ge=1 ≤ 10^12`)، §9 pass.
- 2026-10-11: COMPLETE. 120 تست جدید؛ pytest کامل، ruff، format و mypy سبز.
