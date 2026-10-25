# ORD-03 — POST /checkout/validate

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CART-03, DSC-03, ADDR-02 · **Level:** HIGH

## Objective
بررسی دوباره سبد کاربر واردشده با آدرس و روش ارسال، و برگرداندن quote کامل با `fingerprint` که ORD-04 با آن مقایسه می‌کند (D34، ADR-045).

## PRD reference
«نتیجه سفارش» ✓ (`POST /checkout/validate`)؛ «قیمت و مالیات» ✓؛ ADR-031، ADR-036، ADR-043، ADR-045، ADR-046.

## Plan (batch ORD-03/ORD-05/CAT-17)
- `app/modules/checkout/{schemas,quote,service,router}.py`:
  - بدنه `{address_id, shipping_method_id}` (`extra=forbid`، UUID؛ وگرنه 400). فقط کاربر واردشده (ورود فقط با OTP است، پس موبایل تأییدشده؛ 401).
  - `CheckoutService.build_quote(user_id, address_id, shipping_method_id, now)` بدون باز کردن تراکنش (ORD-04 داخل تراکنش خودش و بعد از lockها صدا می‌زند)؛ `validate` آن را در یک تراکنش read-only اجرا می‌کند. ترتیب بررسی: سبد خالی/ناموجود → 422 `cart_empty`؛ آدرس دیگران یا ناموجود → 404؛ روش ارسال → 422 (`get_selectable`)؛ خط غیرقابل‌فروش (SD rule: محصول/تنوع حذف‌شده، غیرمنتشر، غیرفعال، بی‌قیمت) → 422 با `line_unavailable` و شناسه خطوط؛ موجودی آزاد مؤثر (منهای holdهای منقضی، `stock_levels_of`) کمتر از تعداد → 409 `INSUFFICIENT_STOCK` با variantها؛ کد اعمال‌شده و ردشده → 422 `DISCOUNT_NOT_APPLICABLE` با reason (همان `price_with_code` سبد).
  - قیمت‌گذاری طبق ADR-045: خطوط مرتب با id خط → (کد) → `shipping_basis` → `FlatRateCalculator.quote(rates, ShippingContext(basis, province, city))` → `price_order(..., shipping=amount)`. `price_cart_lines` پارامتر `shipping` می‌گیرد.
  - `quote_fingerprint` خالص (`quote.py`): sha256 روی JSON canonical از fingerprint calculator، **تعداد هر خط** (calculator fingerprint تعداد را ندارد)، `grand_total`، شناسه و مبلغ کد، شناسه روش و مبلغ ارسال.
  - پاسخ: خطوط (id، variant، عنوان، SKU، گزینه‌ها، تعداد، قیمت واحد، اجزا)، جمع‌ها، `discount` (کد و مبلغ یا null)، `shipping` (id، عنوان، هزینه روش، سقف، مبلغ)، `fingerprint`، `currency`، `calculated_at`؛ `Cache-Control: no-store`. بدون نوشتن در DB (بدون lock).
- **ریسک‌ها:** (۱) fingerprint ناقص → تست تغییر هر جزء (قیمت، تعداد، کد، روش، هزینه روش، تنظیمات) fingerprint را عوض کند؛ (۲) ترتیب خطوط → تست shuffle ورودی → خروجی یکسان (ADR-031)؛ (۳) آدرس دیگران → 404؛ (۴) مبلغ از کلاینت → فقط شناسه پذیرفته می‌شود (extra=forbid)؛ (۵) خط حذف‌شده → 422 (SD rule)؛ (۶) موجودی رزروشده دیگران → free مؤثر.
- **Rollback:** `git revert` (بدون schema).
- **تست‌های اضافه:** `tests/test_checkout_validate.py`: 400/401/404/409/422، مرز ارسال رایگان با کد، shuffle، fingerprint، SD rule، no-store.

## Acceptance Criteria
- [x] price/stock/discount/shipping re-checked؛ fingerprint covers discount and shipping (D34).
- [x] SD rule (test)؛ pricing lines in stable order + shuffled input → identical output (ADR-031).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/checkout/{quote,schemas,service,router}.py`؛ `price_cart_lines(shipping=...)` در `app/modules/cart/view.py`. تست: `tests/test_checkout_validate.py`.
- برای ORD-04: `CheckoutService.build_quote(..., locked_code=..., check_stock=False)` داخل تراکنش و بعد از lockها؛ `Quote` همه داده snapshot را دارد؛ `locked_code` باید کد سبد باشد.
- **Rollback:** `git revert`.

## Log
- 2026-10-18: plan (batch ۳ جلسه phase؛ بازبین opus چون مبلغ است).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES؛ اعمال شد: fingerprint هزینه و سقف روش و قواعد کد (type/value/max_amount) را هم می‌پوشاند؛ آدرس دیگران/ناموجود 404 (ADR-047؛ M3.4-PLAN اصلاح شد)؛ `build_quote` یک dataclass داخلی `Quote` برمی‌گرداند (خطوط مرتب، policy، کد + `priced_rules` + usage، روش + rates، آدرس، pricing با ارسال، fingerprint)، کد از پیش قفل‌شده می‌پذیرد و بررسی موجودی بدون lock را می‌تواند رد کند (ORD-04: reserve مرجع است)؛ reason کد در details 422؛ تست تغییر fingerprint با کدی که مرز ارسال رایگان را جابه‌جا می‌کند.
- 2026-10-18: بازبینی diff (opus): PASS WITH CHANGES؛ اعمال شد (تست hold منقضی، 401 قبل از 400، سبد مهمان استفاده نمی‌شود، فقط خطوط ناموجود در details، محصول حذف‌شده، guard کد قفل‌شده = کد سبد، guard ثابت‌ماندن مبلغ کد با ارسال، docstring fingerprint). یک شکست suite (نسخه تنظیمات قیمت بعد از تست برنمی‌گشت) رفع شد. pytest (1846)، ruff، format و mypy سبز. COMPLETE.
