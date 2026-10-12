# INV-08 — Admin inventory endpoints (list, patch, reservations, history)

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** INV-02, AUTH-10 · **Level:** HIGH

## Objective
چهار endpoint ادمین موجودی از PRD: لیست موجودی تنوع‌ها با فیلتر کم‌موجود/ناموجود، اصلاح دستی موجودی و حد هشدار یک تنوع، لیست رزروها و تاریخچه movementهای یک تنوع. منطق تغییر موجودی همان `InventoryService.adjust` (INV-02) است.

## PRD reference
«موجودی و رزرو» ✓ (APIها: `GET /admin/inventory`، `PATCH /admin/inventory/{variantId}`، `GET /admin/inventory/reservations`، `GET /admin/inventory/{variantId}/history`؛ دسترسی: Admin با `inventory:update`)؛ ADR-029، ADR-034، ADR-036. تصمیم‌های کم‌اثر: ADR-038.

## Plan (batch INV-08/INV-09/PRC-06)
- فایل‌ها: `app/modules/inventory/{admin_router.py, admin_schemas.py, admin_service.py, admin_repository.py, dependencies.py}`؛ ثبت router در `app/api/v1/router.py`. بدون schema و migration.
- مجوز: خواندن (`GET`ها) با `require_any_permission("inventory:read", "inventory:update")`؛ نوشتن با `inventory:update`. اول authorization، بعد validation. همه پاسخ‌ها `Cache-Control: no-store`.
- `GET /admin/inventory`: یک ردیف برای هر تنوع حذف‌نشده (محصول حذف‌نشده؛ همه وضعیت‌های محصول): `variant_id`، `product_id`، `product_title`، `sku`، `total`، `reserved` (مؤثر، منهای نگه‌داشت منقضی)، `free`، `low_stock_threshold`، `stock_status`، `updated_at`. فقط انبار فعال؛ تنوع بدون InventoryItem → صفر و `out_of_stock`. محاسبه در SQL (aggregate روی inventory_items + `expired_hold_sum`)، تا فیلتر `stock_status` (in_stock، low_stock، out_of_stock) و صفحه‌بندی در DB باشد. query: `page`، `limit`، `q` (sku یا عنوان، trim، خالی → 400)، `product_id`، `stock_status`، `sort` (`sku`، `free_asc`، `free_desc`، `updated`)، tie-break `variant_id`. allowlist برای query.
- `PATCH /admin/inventory/{variant_id}`: بدنه `{adjustment_type?, quantity?, low_stock_threshold?, reason, expected_total?}` با `extra="forbid"` و نوع strict. فیلدهای سیستمی (`total_quantity`، `reserved_quantity`، `free`، `id`، `variant_id`، `product_id`، `warehouse_id`، timestamps) قبل از validation حذف و نادیده گرفته می‌شوند (CLAUDE.md §۸؛ هم‌سو با ADR-030). حداقل یکی از adjustment یا threshold؛ `adjustment_type` و `quantity` با هم؛ `reason` همیشه اجباری. `expected_total` (اختیاری): اگر total زیر lock با آن برابر نبود → 409 `CONFLICT` (محافظ double-submit؛ correction خودش idempotent است). threshold در بازه `0..MAX_STOCK_QUANTITY`. همه در یک تراکنش زیر همان ترتیب lock (variant `FOR SHARE` → item `FOR UPDATE`): threshold تغییر کرده → audit `inventory.threshold_updated` (بدون movement، چون شمارنده نیست)؛ adjustment → همان مسیر `adjust` (movement + audit `inventory.adjusted`). بدون تغییر → 200 بدون audit. پاسخ: همان ردیف لیست. خطاها: 400 validation، 401، 403، 404 variant ناموجود/حذف‌شده، 409 زیر reserved یا `expected_total` نابرابر، 422 بیش از سقف.
- refactor کوچک INV-02: بدنه تراکنش `adjust` به یک متد داخلی (`_adjust_locked`) جدا می‌شود تا PATCH همان منطق را با threshold در یک تراکنش صدا بزند؛ رفتار و تست‌های INV-02 بدون تغییر.
- `GET /admin/inventory/reservations`: `status` (active، expired، committed، released)، `order_id`، `variant_id`، `page`، `limit`. وضعیت نمایشی مستقل از job (ADR-036): active ذخیره‌شده با `expires_at ≤ now` → `expired`؛ فیلتر هم همین تعریف را در SQL دارد. فیلدها: `id`، `order_id`، `user_id`، `status`، `expires_at`، `created_at`، `committed_at`، `released_at`، `items[]` (`variant_id`، `sku`، `quantity`، `status`). ترتیب `created_at desc, id desc`. آیتم‌ها با یک query دوم (بدون N+1).
- `GET /admin/inventory/{variant_id}/history`: movementهای InventoryItemهای تنوع، جدیدترین اول (`created_at desc, id desc`)، صفحه‌بندی: `id`، `movement_type`، `quantity`، `total_before/after`، `reserved_before/after`، `reference_type/id`، `reason`، `created_by`، `created_at`. variant ناموجود → 404؛ variant حذف‌شده → تاریخچه دیده می‌شود (نمای ادمین، مثل price-history ADR-030).
- ریسک‌ها: (۱) نشت یا نادرستی reserved در لیست وقتی job اجرا نشده (کسر نگه‌داشت منقضی در SQL؛ تست برابری با availability عمومی)؛ (۲) دوبار ارسال increase (expected_total؛ تست)؛ (۳) PATCH همزمان (lock موجود INV-02؛ تست gather روی HTTP)؛ (۴) کلاینت total/reserved بفرستد (نادیده؛ تست)؛ (۵) N+1 در لیست رزرو (تست تعداد query)؛ (۶) فیلتر stock_status در SQL با تابع خالص `stock_status` ناهمخوان شود (تست جدولی مقایسه هر ردیف با تابع خالص).
- Rollback: بدون schema؛ `git revert`.

## Acceptance Criteria
- [x] چهار endpoint با مجوز درست (401 بدون token، 403 بدون مجوز موجودی؛ نقش support/content_manager)، authorization قبل از validation.
- [x] لیست: فیلتر stock_status، q، product_id و sort در DB؛ reserved مؤثر با رزرو منقضی sweep‌نشده؛ تنوع بدون آیتم → out_of_stock؛ وضعیت هر ردیف برابر تابع خالص `stock_status` (تست).
- [x] PATCH: adjustment، threshold، هر دو با هم؛ movement و audit؛ no-op بدون audit؛ فیلدهای سیستمی نادیده؛ 400/404/409/422 (تست)؛ PATCH همزمان سریال (تست).
- [x] رزروها: فیلتر status با expired مستقل از job؛ بدون N+1 (تست).
- [x] تاریخچه: ترتیب، صفحه‌بندی، 404 (تست).
- [x] query param ناشناخته → 400؛ `Cache-Control: no-store`.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/inventory/admin_router.py`، `admin_schemas.py`، `admin_service.py`، `admin_repository.py` (aggregate SQL موجودی با `expired_hold_sum` و clamp per item؛ `display_status` رزرو)، `dependencies.py`؛ `InventoryService.apply_update` (در تراکنش فراخواننده) و `_lock_item`/`_adjust_locked` مشترک با `adjust`. `escape_like` از catalog به `app/shared/pagination.py` منتقل شد.
- تست: `tests/test_admin_inventory.py` (۲۲ تست، شامل نقشه COVERAGE چهار endpoint × 400..422 با guard route و نام تست).
- **Rollback:** بدون schema؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-12: فایل task و plan (batch INV-08/INV-09/PRC-06، AUTOPILOT).
- 2026-10-12: REVIEW-CHECKLIST (خودم): §1، §2، §3، §5، §6، §7، §9 پاس؛ §4، §8 N/A. بازبینی plan (subagent): APPROVE WITH CHANGES؛ اعمال شد (وضعیت نمایشی آیتم رزرو، EXISTS برای variant_id، escape در q، پاسخ PATCH زیر همان lock، ثبت expected_total و ریسک ترتیب history در ADR-038). بازبینی diff (subagent): APPROVE WITH CHANGES؛ اعمال شد (تست rollback PATCH ترکیبی، log `inventory.updated`، نام فیلد خطای threshold، یادداشت‌های ADR-038). pytest (1452)، ruff، format و mypy سبز. COMPLETE.
