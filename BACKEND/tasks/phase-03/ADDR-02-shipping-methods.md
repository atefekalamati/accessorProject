# ADDR-02 — ShippingMethod + shipping calculator interface

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ADDR-00, INF-02 · **Level:** HIGH

## Objective
جدول روش‌های ارسال، محاسبه‌گر هزینه ارسال پشت interface (پیاده‌سازی v1: هزینه ثابت + سقف ارسال رایگان) و `GET /shipping-methods` عمومی. ORD-03/ORD-04 هزینه را از همین محاسبه‌گر می‌گیرند و به `price_order(shipping=...)` می‌دهند.

## PRD reference
«شیوه ارسال» ✓؛ D33، D34 (ADR-039)؛ ADR-031 (هزینه ارسال گرد نمی‌شود و مالیات ندارد). تصمیم‌های کم‌اثر: ADR-045.

## Plan (batch ADDR-01/ADDR-02)
- مدل `ShippingMethod` (`app/db/models/shipping.py`؛ SoftDelete + Timestamp): `title` (۱..۱۰۰، trim)، `description` (nullable، ≤ ۵۰۰)، `cost` (BIGINT، `0..MAX_PRICE_TOMAN`؛ صفر = همیشه رایگان)، `free_shipping_threshold` (nullable، `1..MAX`)، `is_active`، `display_order` (≥ 0). migration `20261018_0021`؛ ثبت در `__init__`، `_MODELS`، `EXPECTED_TABLES`.
- `app/modules/shipping/calculator.py` (خالص، بدون DB):
  - `ShippingRates` (frozen: `cost`، `free_shipping_threshold`) و `rates_of(method)`.
  - `ShippingCalculator` (Protocol): `quote(rates, context: ShippingContext) -> int` (به‌جای `basis` تنها؛ context استان و شهر را برای قیمت منطقه‌ای بعدی دارد — بازبینی plan).
  - `FlatRateCalculator`: `0` اگر سقف تعریف شده و `basis ≥ threshold`؛ وگرنه `cost`. ورودی int strict (bool/float → TypeError، منفی → ValueError).
  - `shipping_basis(pricing: OrderPricing) -> int` = `subtotal − product_discount_total − discount_code_amount` (بعد از همه تخفیف‌ها، قبل از مالیات، بدون ارسال؛ D34). ADR-045: مبنای حداقل کد تخفیف (ADR-043) با این فرق دارد.
  - `get_shipping_calculator()` dependency (v1 فقط flat؛ منطقه‌ای بعداً، D33).
- `GET /shipping-methods` (عمومی): روش‌های فعال و حذف‌نشده به ترتیب `display_order`، سپس `title`، id؛ فیلدها `id`، `title`، `description`، `cost`، `free_shipping_threshold`. allowlist query بدون پارامتر. محاسبه هزینه برای سبد فعلاً نه (ORD-03).
- بدون endpoint ادمین (ADDR-03).
- ریسک‌ها: (۱) مبنای اشتباه سقف رایگان (تابع واحد `shipping_basis` + تست جدولی با کد تخفیف و sale)؛ (۲) گردکردن یا مالیات روی ارسال (فقط عدد صحیح از جدول؛ تست با calculator که grand_total = … + shipping)؛ (۳) روش غیرفعال/حذف‌شده در checkout (فهرست عمومی فقط فعال؛ ORD-03 باید 422 بدهد — یادداشت)؛ (۴) مبلغ از کلاینت (فقط id روش پذیرفته می‌شود، ORD-03).
- Rollback: `alembic downgrade -1` (فقط dev)؛ `git revert`.

## Acceptance Criteria
- [x] مدل و migration با CHECKها (تست قیدها و drift).
- [x] محاسبه‌گر خالص: مرز سقف (برابر → رایگان)، بدون سقف، هزینه صفر، ورودی نامعتبر (تست جدولی)؛ `shipping_basis` با تخفیف محصول و کد.
- [x] `GET /shipping-methods` فقط فعال‌ها با ترتیب ثابت؛ query ناشناخته 400 (تست).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/db/models/shipping.py`، migration `20261018_0021`، `app/modules/shipping/{calculator,repository,router}.py` (`FlatRateCalculator`، `ShippingContext`، `shipping_basis`، `get_selectable` با 422 یکسان). تست: `tests/test_shipping.py` (10 تابع تست).
- برای ORD-03: fingerprint quote باید fingerprint قیمت، شناسه و مبلغ کد، و شناسه و مبلغ ارسال را بپوشاند (D34، ADR-045).
- **Rollback:** `alembic downgrade -1` (فقط dev)؛ `git revert`.

## Log
- 2026-10-18: plan (batch ۴ جلسه phase؛ بازبین opus چون مبلغ ارسال است).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES؛ اعمال شد (ADR-045، ترتیب قیمت‌گذاری بدون دور، تست بدون گردکردن و مالیات، `ShippingContext`، اعتبارسنجی rates، `get_selectable` مشترک، CHECKهای بیشتر، تست‌های مرز مبنا و endpoint). بازبینی diff (opus): PASS؛ اعمال شد (تست اعتبارسنجی context و سقف، حذف بندهای طول تکراری CHECK، تست همزمانی پیش‌فرض آدرس، یادداشت snapshot روش در ADR-045). pytest (1705)، ruff، format و mypy سبز. COMPLETE.
