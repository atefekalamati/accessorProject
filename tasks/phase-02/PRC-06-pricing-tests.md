# PRC-06 — Pricing tests (unit table + tamper API)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** PRC-02…05 · **Level:** HIGH

## Objective
suite تجمیعی قیمت، مثل AUTH-12 و CAT-12: نقشه قاعده → تست برای ADR-014، ADR-027، ADR-031، ADR-033 و ADR-035، تست‌های invariant جدولی برای تابع خالص، و تست‌های دست‌کاری (tamper) که نشان دهند مبلغ، قیمت یا فیلد سیستمی ارسالی از کلاینت هرگز اثر ندارد. فقط تست؛ کد تولید فقط اگر شکافی پیدا شود (→ توقف و گزارش اگر خارج از plan باشد).

## PRD reference
«قیمت و مالیات» ✓؛ CLAUDE.md §۸ (قیمت فقط در بک‌اند، پول int تومان، گردکردن یک‌بار)؛ ADR-001، ADR-014، ADR-027، ADR-031، ADR-033، ADR-035.

## Plan (batch INV-08/INV-09/PRC-06)
- فایل جدید `tests/test_pricing_security.py`؛ docstring هر تست `<ADR>.<rule>`. نقشه قاعده → تست (قواعدی که قبلاً پوشش دارند به تست موجود اشاره می‌کنند) در بخش Implementation Notes همین فایل.
- unit (بدون DB، `price_order`/`unit_price`): فقط شکاف‌ها؛ حلقه seeded موجود (`test_invariants_over_seeded_random_carts`) تکرار نمی‌شود و در نقشه ارجاع داده می‌شود. اضافه: جایگشت ترتیب lineها → خروجی یکسان (ADR-031)؛ همه خروجی‌ها `int` و نه bool؛ گردکردن فقط روی بخش‌های محاسبه‌شده (تخفیف درصدی و مالیات) طبق `rounding_step`/mode و هرگز روی قیمت واحد، تخفیف مبلغ ثابت یا هزینه ارسال (`grand_total` لازم نیست مضرب step باشد، ADR-031)؛ float، bool، رشته و منفی در ورودی → خطا. (بازبینی plan، یافته‌های ۱ و ۲)
- tamper API (integration):
  - `GET /products/{id}/pricing` با query ناشناخته (`price`، `unit_price`، `tax`) → 400؛ پاسخ از DB.
  - `PATCH /admin/product-variants/{id}` با `base_price`/`sale_price`/`price_version` → قیمت تغییر نمی‌کند (ADR-030).
  - `PATCH /admin/product-variants/{id}/price`: فیلدهای سیستمی (`price_version`، `tax_enabled`) نادیده؛ مبالغ محاسبه‌شده (`unit_price`، `final_price`، `grand_total`، `discount_amount`) کلید ناشناخته‌اند → 400 بدون تغییر؛ float یا رشته برای قیمت → 400.
  - `POST /admin/products/{id}/variants` با هر فیلد قیمت (حتی null) بدون `pricing:update` → 403؛ بدنه نامعتبر قبل از آن 400 (ADR-030).
  - `PATCH /admin/pricing/settings` با `version`، `currency` → نادیده؛ float برای `default_tax_rate_bps` → 400.
  - لیست و جزئیات عمومی محصول: قیمت برابر `/pricing` (یک منبع حقیقت).
- tamper‌هایی که قبلاً تست دارند (settings، PATCH تنوع) فقط در نقشه با نام تست موجود ارجاع داده می‌شوند و guard وجود هر تست نام‌برده را بررسی می‌کند.
- ریسک‌ها: تکرار تست‌های موجود (فقط شکاف‌ها و نقشه)؛ کندی (unit بدون DB).
- Rollback: فقط تست؛ `git revert`.

## Acceptance Criteria
- [x] نقشه قاعده → تست برای ADRهای قیمت کامل است و هر تست نام‌برده وجود دارد (guard مثل CAT-12).
- [x] تست‌های invariant جدولی تابع خالص سبز.
- [x] هر فیلد مبلغ/قیمت/سیستمی ارسالی از کلاینت در endpointهای قیمت نادیده یا رد می‌شود (تست).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- تست: `tests/test_pricing_security.py`. نقشه `RULES` (۳۲ قاعده `<ADR>.<rule>` → `module::test`) با دو guard: هر تست نام‌برده وجود دارد، و هر تست این فایل در نقشه آمده است. شکاف‌های پوشش‌داده‌شده: خروجی‌ها `int` خالص (۲۰۰ سبد seeded)، ترتیب ورودی بی‌اثر بر جمع‌ها و fingerprint، قیمت واحد/تخفیف ثابت/ارسال هرگز گرد نمی‌شوند (هر mode)، مبلغ کلاینت در query `/pricing` → 400، قیمت لیست = `/pricing`، مبالغ محاسبه‌شده در تغییر قیمت → 400.
- بدون تغییر کد تولید.
- **Rollback:** فقط تست؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-12: فایل task و plan (batch INV-08/INV-09/PRC-06، AUTOPILOT).
- 2026-10-12: REVIEW-CHECKLIST (خودم): §2، §8، §9 هدف task؛ بقیه N/A. بازبینی plan (subagent): APPROVE WITH CHANGES؛ یافته‌های ۱ تا ۴ اعمال شد (invariant گردکردن طبق ADR-031، بدون حلقه seeded دوم، 403 قطعی، ارجاع به تست‌های موجود).
- 2026-10-12: بازبینی diff (subagent): APPROVE WITH CHANGES؛ اعمال شد (حذف مقایسه بی‌اثر، assert کلیدی قیمت واحد، ورودی‌های بیشتر در نقشه، توضیح پوشش جزئی، plan هم‌سو با رفتار 400). pytest سبز. COMPLETE.
