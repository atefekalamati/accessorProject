# PRC-02 — Pure pricing function (sale window, discounts, tax, shipping, single rounding)

**Status:** BLOCKED (D28) · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** INF-02, PRC-01 · **Level:** HIGH

## Objective
یک تابع خالص و unit-testable که از قیمت‌های variant، تعداد، تخفیف کد، تنظیمات مالیات/گردکردن و هزینه ارسال، همه خروجی‌های PRD («قیمت و مالیات» ✓) را می‌سازد. بدون DB و بدون endpoint. مصرف‌کننده‌ها: CAT-07/CAT-08 (قیمت واحد)، CART، ORD-03 (`POST /checkout/validate`)، ORD-04 (snapshot سفارش).

## PRD reference
«قیمت و مالیات» ✓ (قوانین کسب‌وکار، خروجی‌ها، معیار پذیرش: «تست واحد برای محاسبه قیمت، تخفیف، مالیات و گردکردن»)؛ ADR-001، ADR-010، ADR-014، ADR-027؛ CAT-00 ردیف ۵ و ۶.

## Plan (منتظر D28)
- `app/modules/pricing/__init__.py`، `app/modules/pricing/calculator.py`:
  - `unit_price(base, sale, start, end, at) -> UnitPrice` (`original`، `final`، `discount_amount`، `discount_percent` با floor، فقط نمایشی). بازه sale نیمه‌باز `[start, end)`؛ بدون base → `None` (قابل فروش نیست).
  - `price_order(lines, settings, code_discount, shipping, at) -> OrderPricing`: برای هر خط `unit_price`، `quantity`، `line_subtotal`، `product_discount`، `tax`، `final_line_total`؛ جمع‌ها `subtotal`، `product_discount_total`، `discount_code_amount`، `tax_amount`، `shipping_amount`، `grand_total`؛ و `fingerprint` از `price_version` هر خط و `pricing_settings.version` (ADR-027).
  - کد تخفیف به‌صورت ورودی آماده (`percent_bps` یا `fixed_amount`، سقف اختیاری)؛ قواعد اعتبار کد مال DSC است.
- تست: `tests/test_pricing_calculator.py` جدولی: مرز بازه (start، end، end − 1µs)، sale بدون بازه، تخفیف درصدی/ثابت/سقف/بیش از جمع (clamp به 0)، مالیات خاموش/روشن، variant غیرمشمول مالیات، هر سه mode گردکردن با step 1 و 1000، مقادیر بزرگ (10^12 × تعداد)، ورودی float/bool → TypeError، `grand_total == جمع اجزا`.
- **ریسک‌ها:** off-by-one بازه sale؛ float؛ گردکردن بیش از یک‌بار؛ ناسازگاری جمع اجزا با grand_total؛ مبلغ منفی؛ overflow (Python int، ولی BIGINT در snapshot: سقف جمع بررسی می‌شود).
- **Rollback:** بدون schema؛ `git revert`.

## Open decision D28 (پول؛ PRD مشخص نکرده)
1. **مبنای مالیات:** پیشنهاد: مالیات روی خطوط مشمول بعد از تخفیف محصول و بعد از سهم تخفیف کد (تقسیم تناسبی روی خطوط)؛ هزینه ارسال مشمول مالیات نیست.
2. **مرحله گردکردن:** پیشنهاد: همه اجزا تا انتها کسر دقیق (`Fraction`) می‌مانند و فقط اجزای غیرصحیح (تخفیف کد و مالیات) یک‌بار در مرحله پایانی با mode/step گرد می‌شوند. `grand_total` = جمع اجزای گردشده، تا اجزا دقیقاً با مبلغ پرداخت جمع شوند. جایگزین: فقط `grand_total` گرد شود و اختلاف گرد در یک جزء جذب شود.
3. **سهم هر خط (برای OrderItem.discountAmount و taxAmount):** پیشنهاد: تقسیم با روش largest-remainder تا جمع خطوط دقیقاً برابر جمع کل باشد.

## Validation
```powershell
python -m pytest -q tests/test_pricing_calculator.py
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-11: plan نوشته شد. توقف AUTOPILOT: مبنای مالیات، تقسیم تخفیف کد و مرحله گردکردن در PRD مشخص نیست و به پول مربوط است (CLAUDE.md §۱۱، پروتکل ۸). D28 باز شد.
