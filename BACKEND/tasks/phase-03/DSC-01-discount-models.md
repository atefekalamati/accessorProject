# DSC-01 — DiscountCode & redemption models

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** DSC-00 · **Level:** HIGH

## Objective
جدول‌های `discount_codes` و `discount_redemptions` با قیدهای سازگاری در DB، و helper خالص نرمال‌سازی کد؛ پایه DSC-02..05 و ORD-04.

## PRD reference
«کد تخفیف» ✓ و «تخفیف‌ها» ✓؛ D31، D33، D34 (ADR-039)؛ ADR-014، ADR-031. تصمیم‌های کم‌اثر: ADR-042.

## Plan (batch CART-05/DSC-01)
- `app/db/models/discounts.py` (متن اولیه؛ با «اصلاحات بازبینی plan» پایین جایگزین شده است):
  - `DiscountCode` (SoftDelete + Timestamp): `code` (String 32؛ ذخیره نرمال‌شده = trim + upper؛ CHECK `^[A-Z0-9_-]{3,32}$`؛ partial unique بین ردیف‌های حذف‌نشده)، `type` (`percent` | `fixed`، CHECK)، `value` (BIGINT؛ percent → basis point `1..10000`، fixed → تومان `1..MAX_PRICE_TOMAN`؛ CHECK per type)، `max_amount` (nullable، `1..MAX_PRICE_TOMAN`؛ فقط برای percent معنا دارد، برای fixed → CHECK NULL)، `min_order_amount` (nullable، `0..MAX_PRICE_TOMAN`)، `starts_at`/`ends_at` (nullable، CHECK `starts_at < ends_at`؛ بازه نیمه‌باز)، `usage_limit_total` و `usage_limit_per_user` (nullable، ≥ 1)، `is_active`، `created_by`/`updated_by` (FK users SET NULL). index روی `(is_active, ends_at)` لازم نیست در v1.
  - `DiscountRedemption` (Timestamp): `discount_code_id` (FK RESTRICT)، `order_id` (UUID بدون FK تا ORD-01، مثل رزرو)، `user_id` (FK users SET NULL)، `phone` (E.164 نرمال‌شده، CHECK همان الگوی users؛ کلید سقف هر کاربر)، `amount` (BIGINT، `0..MAX_PRICE_TOMAN`)، `status` (`pending` | `confirmed` | `released`، CHECK)، `confirmed_at`/`released_at` با CHECK سازگاری با status. partial unique: یک redemption زنده (`pending`/`confirmed`) برای هر سفارش. index شمارش: `(discount_code_id, status)` و `(discount_code_id, phone, status)`.
- اصلاحات بازبینی plan (opus): `order_id` NOT NULL (FK در ORD-01 برای رزرو و redemption)؛ partial unique `UNIQUE(order_id) WHERE status IN ('pending','confirmed')`؛ CHECKهای وضعیت: `released_at IS NOT NULL` ⟺ `released`، `confirmed` ⟹ `confirmed_at` موجود، `pending` ⟹ `confirmed_at` خالی (confirmed → released با حفظ `confirmed_at` ممکن است؛ `released_at ≥ confirmed_at`)؛ indexهای شمارش partial روی وضعیت زنده؛ ستون `code` (snapshot متن کد) روی redemption؛ CHECK `usage_limit_per_user ≤ usage_limit_total`؛ CHECK بازه با NULLها؛ `is_active` NOT NULL با پیش‌فرض true؛ `min_order_amount` در `1..MAX`؛ `amount` در `0..MAX` (درصد کوچک ممکن است صفر گرد شود)؛ `carts.discount_code_id` (nullable، FK SET NULL) همین‌جا اضافه می‌شود؛ جدول تلاش‌های ناموفق rate limit مال DSC-03 است (ADR-042)؛ `normalize_code` فقط ASCII (رقم فارسی رد می‌شود) قبل از upper.
- migration `20261018_0019`؛ ثبت در `__init__`، `_MODELS`، `EXPECTED_TABLES` و HEAD_REVISION.
- `app/modules/discounts/codes.py`: `normalize_code(raw) -> str` (trim، upper؛ ValueError برای خالی یا خارج از الگو)؛ unit test.
- بدون endpoint (DSC-03/04).
- ریسک‌ها: (۱) کد تکراری با حروف متفاوت (ذخیره نرمال + CHECK upper + unique)؛ (۲) مبلغ/درصد نامعتبر یا float (CHECK بازه؛ BIGINT)؛ (۳) شمارش سقف اشتباه با redemption آزادشده (status در index و شمارش فقط pending/confirmed؛ قفل در ORD-04 طبق D31)؛ (۴) کلید سقف هر کاربر با user_id به‌جای موبایل (ستون phone اجباری)؛ (۵) حذف کد استفاده‌شده (FK RESTRICT + soft delete).
- Rollback: `alembic downgrade -1` (فقط dev)؛ `git revert`.

## Acceptance Criteria
- [x] همه CHECKها و unique بالا در DB (تست برای هر قید).
- [x] یک redemption زنده برای هر سفارش؛ redemption آزادشده اجازه redemption جدید برای همان سفارش می‌دهد (تست).
- [x] `normalize_code` (unit test)؛ کد با حروف کوچک در DB رد می‌شود.
- [x] migration upgrade/downgrade و تست schema/drift؛ pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/db/models/discounts.py` (`DiscountCode`، `DiscountRedemption`، `DiscountType`، `RedemptionStatus`)، `carts.discount_code_id`، `app/modules/discounts/codes.py` (`normalize_code`)؛ migration `20261018_0019`.
- تست: `tests/test_discount_models.py` (10 تابع تست، ۴۲ مورد با parametrize).
- **Rollback:** `alembic downgrade -1` (فقط dev)؛ `git revert`.

## Log
- 2026-10-18: plan (batch ۱ جلسه phase؛ بدون plan milestone طبق تصمیم کاربر؛ بازبین opus).
- 2026-10-18: REVIEW-CHECKLIST (خودم): §1 (backstop یکتایی و قفل در ORD-04 ثبت شد)، §5، §8، §9 پاس؛ §2، §3، §4، §6، §7 N/A (بدون endpoint). بازبینی plan (opus): APPROVE WITH CHANGES؛ همه اعمال شد (order_id NOT NULL، CHECK وضعیت با confirmed → released، `carts.discount_code_id`، indexهای partial، ASCII قبل از upper، per-user ≤ total، snapshot کد، ADR-042). بازبینی diff (opus): APPROVE؛ پیشنهادها اعمال شد (حذف index تکراری، تست confirmed در unique زنده، match دقیق تست bogo، یادداشت ADR). pytest (1573)، ruff، format و mypy سبز. COMPLETE.
