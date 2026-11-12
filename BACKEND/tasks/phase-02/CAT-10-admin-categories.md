# CAT-10 — Admin category CRUD + AuditLog + `categories:edit_content`

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-01, AUTH-10, INF-05 · **Level:** HIGH

## Objective
مدیریت دسته‌بندی در پنل ادمین: لیست، ایجاد، ویرایش و حذف نرم، با AuditLog برای هر تغییر. مجوز `categories:edit_content` به content_manager اجازه می‌دهد فقط فیلدهای محتوایی را ویرایش کند. فیلترهای دسته (`PATCH /admin/categories/{id}/filters`) جزو CAT-09 است.

## PRD reference
«دسته‌بندی محصولات» ✓ (APIهای admin، دسترسی و امنیت، خطاهای 403/404/409)؛ ADR-023؛ ADR-025.

## Acceptance Criteria
- [x] seed: مجوز `categories:edit_content` برای content_manager؛ admin و super_admin آن را از `ALL_PERMISSION_KEYS` می‌گیرند. migration لازم نیست، چون مجوزها فقط از seed idempotent می‌آیند.
- [x] `require_any_permission(*keys)` در `app/modules/auth/dependencies.py`؛ کلید ناشناخته در زمان import خطا می‌دهد.
- [x] `GET /admin/categories`: دسته‌های غیرفعال را نشان می‌دهد و soft-deleted را نه؛ pagination ادمین؛ sort `display_order` یا `newest`؛ هر یک از دو مجوز کافی است.
- [x] `POST /admin/categories` → 201 و `DELETE /admin/categories/{id}` → 204 (حذف نرم)؛ هر دو فقط با `catalog:manage`.
- [x] `PATCH /admin/categories/{id}`: اگر بدنه فقط شامل `title`، `description`، `image_url` و `display_order` باشد، هر یک از دو مجوز کافی است. ارسال هر فیلد دیگری بدون `catalog:manage` → 403 و هیچ تغییری ذخیره نمی‌شود (ADR-023).
- [x] slug تکراری → 409 `DUPLICATE_SLUG`. parent ناموجود یا حذف‌شده → 422. چرخه مستقیم یا غیرمستقیم → 409. عمق بیش از ۵ (شامل زیردرخت جابه‌جاشده) → 422. حذف دسته دارای زیرمجموعه یا محصول → 409. فیلد ناشناخته یا null برای فیلد اجباری → 400.
- [x] `image_url` فقط `https` روی hostهای `MEDIA_ALLOWED_HOSTS`، بدون user info و port؛ وگرنه 400 روی `body.image_url`. تست برای `javascript:`، `http:`، host خارجی و موارد دیگر.
- [x] `category.created`، `category.updated` (فقط فیلدهای تغییرکرده؛ PATCH بدون تغییر audit ندارد) و `category.deleted` در همان تراکنش ثبت می‌شوند.
- [x] همه نوشتن‌ها با advisory lock تراکنشی و `FOR UPDATE` انجام می‌شوند. تست همزمانی: دو جابه‌جایی متقابل یکی 200 و دیگری 409 می‌گیرد.
- [x] `Cache-Control: no-store` روی همه پاسخ‌ها؛ برای درخواست بدون احراز، 401 قبل از validation.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/catalog/{admin_schemas,admin_service,admin_router}.py`، `AdminCategoryRepository` در `app/modules/catalog/repository.py`، و `get_admin_category_service`.
- تنظیمات: `media_allowed_hosts` در `app/core/config.py` و `MEDIA_ALLOWED_HOSTS` در `.env.example`. لیست خالی همه URLها را رد می‌کند.
- تست‌ها: `tests/test_admin_categories.py`، `tests/test_catalog_image_url.py`، و به‌روزرسانی `tests/test_seed.py`، `tests/test_auth_security.py` و `tests/conftest.py`.
- **Rollback:** `git revert` روی commit این task. ردیف grant قبلاً seed‌شده با revert حذف نمی‌شود، ولی بدون endpoint بی‌اثر است. حذف آن فقط با تأیید صریح انجام می‌شود. schema تغییری نکرده است.
- **CAT-05:** `image_url` باید با `media_id` جایگزین شود (ADR-025).

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: COMPLETE (پایان batch CAT-06/CAT-10). pytest 767 passed (74 تست جدید)؛ ruff، format و mypy سبز. تست guard در `test_auth_security.py` برای دیدن POST و DELETE و پر کردن عمومی path parameterها به‌روز شد. PRD: `DELETE /admin/categories/{id}` اضافه شد (ADR-025).
