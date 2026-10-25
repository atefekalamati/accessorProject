# CART-02 — Add/update/remove cart items with free-stock check (no reservation)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** CART-01, INV-03 · **Level:** HIGH

## Objective
`POST /cart/items`، `PATCH /cart/items/{id}` و `DELETE /cart/items/{id}` برای مهمان (cookie) و کاربر (Bearer)، با بررسی موجودی آزاد مؤثر و بدون رزرو.

## PRD reference
«سبد خرید» ✓ (APIها، قواعد تعداد و SD rule)؛ «موجودی و رزرو» ✓ (افزودن به سبد رزرو نمی‌کند)؛ D30 (ADR-039)؛ ADR-040، ADR-029، ADR-036.

## Plan (batch CART-01/CART-02)
- فایل‌ها: `app/modules/cart/{router.py, schemas.py, service.py, dependencies.py}`؛ ثبت router در `app/api/v1/router.py`.
- هویت (`CartOwner`): header `Authorization` موجود → `get_current_user` (نامعتبر → 401؛ cookie نادیده)؛ وگرنه مهمان با cookie `cart_token` (`parse_cart_token`).
- `POST /cart/items` (201): بدنه `variant_id` (UUID) و `quantity` (int strict، `1..MAX`)، `extra="forbid"`؛ فیلدهای سیستمی/مبلغ (`id`، `cart_id`، `product_id`، `price`، `unit_price`، `final_price`، `total`) حذف و نادیده. مهمان بدون سبد معتبر → سبد جدید و `Set-Cookie`. variant موجود در سبد → تعداد جمع می‌شود.
- `PATCH /cart/items/{item_id}` (200): `quantity` جدید (`1..MAX`؛ صفر → 400، حذف با DELETE). `DELETE /cart/items/{item_id}` (204).
- تراکنش هر نوشتن: lock ردیف cart (`lock_user_cart` یا `find_guest_cart(lock=True)`) → خواندن variant و InventoryItemهای انبار فعال (بدون lock) + نگه‌داشت منقضی (`expired_holds`) → `free_quantity`. هیچ رزرو یا movement ساخته نمی‌شود.
- خطاها (ADR-040): variant ناموجود، حذف‌شده، غیرفعال، بی‌قیمت یا محصول غیرمنتشر/حذف‌شده → 404؛ `is_purchasable=false` → 422؛ تعداد نهایی > آزاد → 409 `INSUFFICIENT_STOCK` **بدون عدد موجودی** (ADR-029)؛ خط ۵۱ → 422؛ خط سبد دیگری یا مهمان بدون سبد → 404.
- انقضای سبد مهمان لغزنده: هر نوشتن `expires_at = now + 30d` و cookie دوباره set می‌شود (هم‌سو با PRD «۳۰ روز بعد از آخرین تغییر»؛ ADR-040 اصلاح می‌شود).
- پاسخ: `{id, variant_id, product_id, quantity}` + `Cache-Control: no-store`. مبالغ و `GET /cart` در CART-03.
- ریسک‌ها: (۱) IDOR خط سبد (شرط `cart_id` در query؛ تست 404 مهمان↔مهمان و کاربر↔کاربر)؛ (۲) race دو افزودن (lock cart؛ تست gather)؛ (۳) نشت عدد موجودی در 409 (تست کلیدها)؛ (۴) ساخت رزرو (تست شمارنده reserved و جدول رزرو)؛ (۵) token در log یا body (فقط cookie؛ تست)؛ (۶) Bearer نامعتبر با cookie معتبر → باید 401 شود نه fallback به مهمان (تست)؛ (۷) هم‌خوانی با موجودی عمومی: نگه‌داشت منقضی آزاد حساب شود، انبار غیرفعال نه (تست).
- Rollback: بدون schema؛ `git revert`.

## Acceptance Criteria
- [x] سه endpoint برای مهمان و کاربر؛ cookie با ویژگی‌های D30؛ سبد کاربر یکتا.
- [x] qty ≤ موجودی آزاد مؤثر؛ افزودن رزرو نمی‌سازد (تست)؛ 409 بدون عدد موجودی.
- [x] SD rule و 404/422 طبق ADR-040 (تست)؛ سقف ۵۰ خط (تست).
- [x] 400 برای بدنه نامعتبر؛ فیلدهای مبلغ نادیده؛ 401 برای Bearer نامعتبر؛ مالکیت 404 (تست).
- [x] افزودن همزمان سریال می‌شود (تست)؛ `no-store`.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/cart/{router,schemas,service,dependencies}.py`؛ `get_optional_user` در `app/modules/auth/dependencies.py` (هر header `Authorization` باید معتبر باشد)؛ `find_user_cart(lock=)` و `item_for_variant` در repository؛ موجودی از `ProductRepository.stock_levels_of` (همان قاعده availability عمومی).
- باگ پیدا و رفع‌شده: `ON CONFLICT` روی partial unique با predicate پارامتری بعد از پنج اجرا (generic plan در asyncpg) شکست می‌خورد؛ predicate متنی شد و تست regression دارد (روی کد قدیم قرمز، روی کد جدید سبز).
- تست: `tests/test_cart_items.py` (20 تابع تست) + یک تست regression در `tests/test_cart_models.py`.
- **Rollback:** بدون schema؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-12: plan (milestone M3.1، batch ۳ جلسه phase، AUTOPILOT).
- 2026-10-12: REVIEW-CHECKLIST (خودم): §1، §2، §3، §5، §7، §9 پاس؛ §4، §6 (سبد عملیات حساس نیست)، §8 N/A. بازبینی plan (subagent): APPROVE WITH CHANGES؛ همه یافته‌ها اعمال شد (token تازه برای سبد بسته، کاهش PATCH بدون بررسی موجودی، 422 `variant_unavailable`، کاربر بدون سبد → 404 بدون ساخت، هر Authorization باید معتبر باشد، تست CSRF text/plain، انقضای لغزنده، ADR-040). بازبینی diff (subagent): APPROVE؛ پیشنهادها اعمال شد (سقف خط قبل از موجودی، تست POST ناموفق مهمان بدون cookie و سبد، تست `not_purchasable`، اتصال ثابت در تست regression). pytest (1499)، ruff، format و mypy سبز. COMPLETE.
