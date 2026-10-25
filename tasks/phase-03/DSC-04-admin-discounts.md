# DSC-04 — Admin discount CRUD + AuditLog

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** DSC-01, AUTH-10, INF-05 · **Level:** HIGH

## Objective
مدیریت کد تخفیف در پنل: لیست، جزئیات با شمارش استفاده، ایجاد، ویرایش و حذف نرم؛ همه با مجوز `discounts:manage` و AuditLog.

## PRD reference
«تخفیف‌ها» ✓ و «کد تخفیف» ✓؛ D31، D33 (ADR-039)؛ ADR-042، ADR-043. تصمیم‌های کم‌اثر: ADR-044.

## Plan (batch DSC-04/DSC-05)
- `app/modules/discounts/{admin_router.py, admin_schemas.py, admin_service.py}`؛ ثبت router.
- `GET /admin/discounts`: صفحه‌بندی، فیلتر `q` (بخشی از کد؛ escape)، `state` (`active` = فعال و در بازه، `scheduled`، `expired`، `inactive`)، sort (`newest` پیش‌فرض، `code`)؛ هر ردیف با `pending_count` و `confirmed_count` (یک query گروهی، بدون N+1). حذف‌شده‌ها نمایش داده نمی‌شوند.
- `GET /admin/discounts/{id}`: جزئیات + شمارش‌ها؛ حذف‌شده → 404.
- `POST /admin/discounts` (201): `code` (نرمال با `normalize_code`؛ شکل بد → 400)، `type`، `value` (percent به basis point ۱..۱۰۰۰۰، هم‌واحد DB و calculator؛ fixed به تومان)، `max_amount`، `min_order_amount`، `starts_at`/`ends_at` (aware)، `usage_limit_total`، `usage_limit_per_user`، `is_active`. int strict؛ قواعد بدنه → 400 (همان CHECKهای DB به‌علاوه max_amount فقط برای percent، per_user ≤ total، starts < ends). کد تکراری بین کدهای زنده → 409 `CONFLICT`. فیلدهای سیستمی (`id`، counts، `created_by`، timestamps، `deleted_at`) نادیده.
- `PATCH /admin/discounts/{id}`: فیلدهای ارسالی؛ `code` و `type` قابل تغییر نیستند (400) تا معنای redemptionهای قبلی ثابت بماند؛ اعتبار ترکیبی با مقادیر ذخیره‌شده → 422. lock ردیف کد `FOR UPDATE` (همان قفل ORD-04/`redeem`، ADR-042). بدون تغییر → 200 بدون audit.
- `DELETE /admin/discounts/{id}` (204): حذف نرم زیر همان lock؛ redemptionهای قبلی دست نمی‌خورند؛ سبدهایی که کد را دارند آن را در خواندن بعدی `invalid` می‌بینند.
- **اصلاحات بازبینی plan (opus):** کاهش سقف زیر شمارش فعلی مجاز است (فقط استفاده‌های بعدی را می‌بندد؛ D31). 422 فقط برای تعارض با مقادیر ذخیره‌شده: بازه starts/ends، per_user ≤ total و max_amount روی کد fixed؛ همه قواعد شکل بدنه 400. کد تکراری: IntegrityError با نام `uq_discount_codes_code` → 409، بقیه دوباره raise. ساخت دوباره متن یک کد حذف‌شده شمارش را از صفر شروع می‌کند (شمارش به‌ازای id). PATCH با `code`/`type` برابر مقدار ذخیره‌شده no-op است (متفاوت → 400). فیلدهای سیستمی قبل از forbid حذف می‌شوند؛ `updated_by` روی تغییر. DELETE دوم → 404. غیرفعال یا حذف‌کردن کد به سفارش‌های pending دست نمی‌زند و confirm آن‌ها موفق است (تست). `now` یک‌بار در هر درخواست؛ q با escape؛ لیست `released_count` هم دارد.
- audit: `discount.created`، `discount.updated` (فقط فیلدهای تغییرکرده)، `discount.deleted`؛ همه در همان تراکنش.
- اول authorization، بعد validation؛ `no-store`؛ allowlist query.
- ریسک‌ها: (۱) کد تکراری همزمان (unique + 409؛ تست)؛ (۲) تغییر کد در حین سفارش (FOR UPDATE مشترک)؛ (۳) واحد درصد اشتباه (basis point در API و DB؛ تست)؛ (۴) دسترسی بدون مجوز (403؛ تست نقش‌ها)؛ (۵) N+1 در لیست (تست).
- Rollback: بدون schema؛ `git revert`.

## Acceptance Criteria
- [x] پنج endpoint با `discounts:manage`؛ 401/403 قبل از validation (تست).
- [x] اعتبارسنجی 400، تعارض ذخیره‌شده 422، تکراری 409، ناموجود/حذف‌شده 404 (تست).
- [x] audit هر تغییر؛ no-op بدون audit (تست).
- [x] شمارش pending/confirmed بدون N+1 (تست)؛ فیلتر state و q (تست).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/discounts/admin_router.py`، `admin_schemas.py` (زمان‌ها به UTC)، `admin_service.py`؛ ثبت در `app/api/v1/router.py`. تست: `tests/test_admin_discounts.py` (12 تابع تست).
- **Rollback:** بدون schema؛ `git revert`.

## Log
- 2026-10-18: plan (batch ۳ جلسه phase؛ بازبین opus).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES؛ اعمال شد (کاهش سقف زیر شمارش مجاز، تقسیم دقیق 400/422، 409 با نام index، code/type برابر no-op، حذف دوم 404، released_count). بازبینی diff (opus): PASS با should؛ اعمال شد (تست ساخت همزمان تکراری، زمان‌ها در UTC، حذف upper اضافه، تست 400 برای query). pytest (1659)، ruff، format و mypy سبز. COMPLETE.
