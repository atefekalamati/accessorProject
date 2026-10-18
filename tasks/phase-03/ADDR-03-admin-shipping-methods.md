# ADDR-03 — Admin shipping methods

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** ADDR-02, AUTH-10 · **Level:** HIGH

## Objective
CRUD ادمین روش‌های ارسال (`/admin/shipping-methods`) با مجوز جدا و AuditLog برای هر تغییر؛ هزینه ارسال مبلغ پولی است (HIGH).

## PRD reference
«شیوه ارسال» ✓ (APIها و «دسترسی و امنیت»)؛ ADR-045؛ الگوی DSC-04 (ADR-044).

## Plan (batch ADDR-03/ADDR-04)
- مجوز جدید `shipping:manage` فقط در `app/db/seed.py` (admin از `ALL − excluded` و super_admin خودکار می‌گیرند؛ support و content_manager نه). بدون migration؛ seed idempotent در CI/استقرار اجرا می‌شود (`python -m app.db.seed`).
- `app/modules/shipping/admin_schemas.py`: Create (`extra=forbid`، فیلدهای سیستمی `id/created_at/updated_at/deleted_at` حذف و نادیده): `title` trim ۱..۱۰۰، `description` trim ≤۵۰۰ یا null (خالی بعد از trim → 400)، `cost` int strict `0..MAX_PRICE_TOMAN`، `free_shipping_threshold` int strict `1..MAX` یا null، `is_active` StrictBool (پیش‌فرض true)، `display_order` int strict `0..1_000_000`. Update: همه اختیاری، حداقل یک فیلد، null فقط برای `description` و `free_shipping_threshold`. Response: همه ستون‌ها + `created_at`/`updated_at`.
- `app/modules/shipping/admin_service.py`: list (صفحه‌بندی `admin_page_params`، فیلتر `state=active|inactive`، `q` روی عنوان با `escape_like`، ترتیب ثابت `display_order`، `title`، `id` بدون پارامتر sort (بازبینی plan)، حذف‌شده‌ها پنهان)، get، create، update (`with_for_update().execution_options(populate_existing=True)` مانند DSC-04، audit فقط فیلدهای تغییرکرده before/after؛ بدون تغییر → بدون audit)، delete نرم. ناموجود/حذف‌شده → 404. actionها: `shipping_method.created` (after = snapshot کامل)، `updated` (فقط تغییرکرده‌ها)، `deleted` (before شامل title و cost).
- `app/modules/shipping/admin_router.py` + ثبت در `app/api/v1/router.py`؛ `Cache-Control: no-store`؛ مجوز قبل از validation بدنه (الگوی DSC-04).
- تغییر هزینه فقط سفارش‌های بعدی را تحت تأثیر می‌گیرد؛ سفارش snapshot نگه می‌دارد (ADR-045، ORD-01/ORD-04).
- **ریسک‌ها:** (۱) دسترسی ناخواسته (support/content_manager/customer → 403؛ ناشناس → 401؛ تست ماتریس نقش‌ها)؛ (۲) مبلغ نامعتبر (float/str/bool/منفی/بیش از MAX → 400؛ تست جدولی)؛ (۳) فیلد سیستمی از کلاینت (نادیده؛ تست)؛ (۴) تغییر بدون audit (تست هر سه action و فقط فیلدهای تغییرکرده)؛ (۵) روش حذف‌شده هنوز قابل ویرایش (404؛ تست)؛ (۶) PATCH همزمان (row lock + populate_existing؛ تست gather: هر دو 200 و `before` دومی = `after` اولی)؛ (۷) rollout: تا اجرای seed روی DB موجود ادمین 403 می‌گیرد (fail-closed؛ seed idempotent است).
- **Rollback:** `git revert`؛ ردیف مجوز `shipping:manage` در DB بی‌ضرر می‌ماند (حذف دستی اختیاری).
- **تست‌های اضافه:** ماتریس نقش‌ها (support/content_manager بدون `shipping:manage`)؛ 400 برای PATCH خالی، null در فیلدهای NOT NULL، state/query ناشناخته، q خالی؛ 404 برای id ناموجود و DELETE دوم؛ 409/422 در endpointهای ادمین N/A؛ همزمانی PATCH؛ cleanup ردیف‌ها با `created_at >= started` و assertionها فقط با عنوان یکتا؛ audit before/after؛ عدم audit برای PATCH بی‌تغییر؛ اثر روی فهرست عمومی و `get_selectable` (ADDR-04).

## Acceptance Criteria
- [x] GET/POST/PATCH/DELETE `/admin/shipping-methods` با `shipping:manage`.
- [x] هر تغییر در AuditLog (فقط فیلدهای تغییرکرده).
- [x] مسیرهای 400/401/403/404 تست شده‌اند.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/shipping/admin_{schemas,service,router}.py`، مجوز `shipping:manage` در `app/db/seed.py`. تست: `tests/test_admin_shipping.py`.
- استقرار: بعد از deploy، `python -m app.db.seed` لازم است تا admin مجوز جدید را بگیرد (تا آن موقع 403، fail-closed).
- **Rollback:** `git revert`.

## Log
- 2026-10-18: plan (batch ۱ جلسه phase؛ بازبین opus چون مبلغ ارسال است).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES؛ اعمال شد: تست همزمانی با populate_existing، مسیرهای 400/404، ایزوله‌سازی تست، rollout seed، حذف sortهای اضافه، snapshot کامل audit. رد شد: «فیلد سیستمی → 400» (الگوی repo و CLAUDE.md §۸: حذف در `mode=before` و نادیده‌گرفتن).
- 2026-10-18: بازبینی diff (opus): PASS WITH CHANGES؛ اعمال شد (400 برای not-a-uuid در PATCH/DELETE، موارد بیشتر بدنه نامعتبر PATCH، تست همزمانی مستقل از ترتیب، snapshot کامل در audit حذف). pytest (1740)، ruff، format و mypy سبز. COMPLETE.
