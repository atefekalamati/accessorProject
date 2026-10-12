# PRC-02 — Pure pricing function (sale window, discounts, tax, shipping, single rounding)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** INF-02, PRC-01 · **Level:** HIGH

## Objective
یک تابع خالص و unit-testable که از قیمت‌های variant، تعداد، تخفیف کد، تنظیمات مالیات/گردکردن و هزینه ارسال، همه خروجی‌های PRD («قیمت و مالیات» ✓) را می‌سازد. بدون DB و بدون endpoint. مصرف‌کننده‌ها: CAT-07/CAT-08 (قیمت واحد)، CART، ORD-03 (`POST /checkout/validate`)، ORD-04 (snapshot سفارش).

## PRD reference
«قیمت و مالیات» ✓ (قوانین کسب‌وکار، خروجی‌ها، معیار پذیرش: «تست واحد برای محاسبه قیمت، تخفیف، مالیات و گردکردن»)؛ ADR-001، ADR-010، ADR-014، ADR-027؛ CAT-00 ردیف ۵ و ۶.

## Plan (D28 تأیید شد → ADR-031)
- `app/modules/pricing/__init__.py`، `app/modules/pricing/calculator.py`:
  - `unit_price(base, sale, start, end, at) -> UnitPrice` (`original`، `final`، `discount_amount`، `discount_percent` با floor، فقط نمایشی). بازه sale نیمه‌باز `[start, end)`؛ بدون base → `None` (قابل فروش نیست).
  - `price_order(lines, settings, code_discount, shipping, at) -> OrderPricing`: برای هر خط `unit_price`، `quantity`، `line_subtotal`، `product_discount`، `tax`، `final_line_total`؛ جمع‌ها `subtotal`، `product_discount_total`، `discount_code_amount`، `tax_amount`، `shipping_amount`، `grand_total`؛ و `fingerprint` از `price_version` هر خط و `pricing_settings.version` (ADR-027).
  - کد تخفیف به‌صورت ورودی آماده (`percent_bps` یا `fixed_amount`، سقف اختیاری)؛ قواعد اعتبار کد مال DSC است.
- تست: `tests/test_pricing_calculator.py` جدولی: مرز بازه (start، end، end − 1µs)، sale بدون بازه، تخفیف درصدی/ثابت/سقف/بیش از جمع (clamp به 0)، مالیات خاموش/روشن، variant غیرمشمول مالیات، هر سه mode گردکردن با step 1 و 1000، مقادیر بزرگ (10^12 × تعداد)، ورودی float/bool → TypeError، `grand_total == جمع اجزا`.
- **ریسک‌ها:** off-by-one بازه sale؛ float؛ گردکردن بیش از یک‌بار؛ ناسازگاری جمع اجزا با grand_total؛ مبلغ منفی؛ overflow (Python int، ولی BIGINT در snapshot: سقف جمع بررسی می‌شود).
- **Rollback:** بدون schema؛ `git revert`.

## Acceptance Criteria
- [x] `unit_price` با بازه نیمه‌باز، `discount_amount` و `discount_percent` (floor)؛ بدون base → None.
- [x] `price_order` با همه خروجی‌های PRD (subtotal، تخفیف محصول، تخفیف کد، مالیات، ارسال، grand_total، currency، calculated_at، fingerprint) و خطوط با سهم دقیق.
- [x] ADR-031: مبنای مالیات بعد از تخفیف‌ها، ارسال بدون مالیات، هر جزء یک‌بار گرد، grand_total = جمع اجزا، largest-remainder با tie-break ترتیب خطوط.
- [x] guardها: کد ≤ جمع مشمول و سقف، grand_total ≥ 0، BIGINT، نوع‌ها (float/bool/naive/RoundingMode).
- [x] تست invariant روی ۱۵۰۰ سبد تصادفی seedدار با oracle مستقل گردکردن، به‌علاوه ۲۰۰۰ ورودی تصادفی برای `allocate`.
- [x] pytest، ruff، format و mypy سبز.

## Open decision D28 (resolved → ADR-031)
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
- 2026-10-11: کاربر D28 را تأیید کرد (ADR-031) به‌همراه guardها و تست invariant با ≥۱۰۰۰ سبد تصادفی seedدار.
- 2026-10-11: بازبینی plan توسط subagent: APPROVE WITH CHANGES. اعمال شد: fingerprint شامل قیمت اصلی/نهایی و `tax_enabled` (پایان بازه sale → PRICE_CHANGED)، مبلغ ثابت کد گرد نمی‌شود، clamp بعد از گرد به سقف و جمع مشمول، بررسی نوع policy، `code_applied`، `currency`/`calculated_at`، guardهای قیمت/تعداد/بازه، نگاشت OrderItem در docstring و ADR-031. tie-break طبق تصمیم کاربر ترتیب خطوط ماند و قرارداد «ترتیب پایدار» ثبت شد.
- 2026-10-11: بازبینی diff توسط subagent: APPROVE WITH CHANGES، بدون باگ حسابی. اعمال شد: oracle مستقل گردکردن و مالیات در تست تصادفی، صفربودن سهم خطوط نامشمول، کران largest-remainder، پوشش مستقل eligible/سقف برای هر نوع کد، پایداری fingerprint و جمع‌ها با جابه‌جایی خطوط، تست property برای `allocate`، کلید خط فقط `str | UUID`. چک‌لیست: §8 (int تومان، گرد یک‌بار، فقط بک‌اند) و §9 pass؛ بقیه N/A.
- 2026-10-11: COMPLETE. 82 تست واحد؛ pytest 1140 passed؛ ruff، format و mypy سبز.
