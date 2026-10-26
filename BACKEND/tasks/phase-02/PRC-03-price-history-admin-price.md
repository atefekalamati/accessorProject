# PRC-03 — PriceHistory + admin price change

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** PRC-01, INF-05, AUTH-10 · **Level:** HIGH

## Objective
تغییر قیمت تنوع (و محصول تک‌تنوعی) توسط نقش دارای `pricing:update`، با PriceHistory و AuditLog برای هر تغییر، و مشاهده تاریخچه.

## PRD reference
«قیمت و مالیات» ✓ (APIها: `PATCH /admin/product-variants/{id}/price`، `PATCH /admin/products/{id}/price`، `GET /admin/products/{id}/price-history`؛ entity PriceHistory)؛ ADR-027، ADR-030 (ترتیب lock، قیمت فقط اینجا). تصمیم‌ها: ADR-035 (D29 گزینه الف).

## Plan (batch INV-02/PRC-03)
- مدل `PriceHistory`: `product_id`، `variant_id` (composite FK به variant)، `old/new_base_price`، `old/new_sale_price`، `old/new_sale_start_at`، `old/new_sale_end_at`، `changed_by` (SET NULL)، `reason` (nullable، ≤ 500)، `created_at`؛ index `(product_id, created_at)`. migration `20261011_0015`.
- `PATCH /admin/product-variants/{variant_id}/price` با `pricing:update`: بدنه `base_price` (strict، `1..MAX_PRICE_TOMAN`، null ممنوع)، `sale_price` (nullable)، `sale_start_at`، `sale_end_at` (aware)، `reason`؛ حداقل یک فیلد قیمت. فیلدهای سیستمی حذف، کلید ناشناخته → 400. وضعیت نهایی (ادغام با مقدار فعلی) باید `sale ≤ base` و بازه معتبر باشد، وگرنه 400. حذف `sale_price` بازه را هم پاک می‌کند.
- `PATCH /admin/products/{product_id}/price`: همان بدنه؛ فقط وقتی محصول دقیقاً یک تنوع حذف‌نشده دارد، روی آن اعمال می‌شود؛ وگرنه 422 (تغییر دسته‌جمعی قیمت در v1 نیست؛ ADR-034).
- سرویس: lock Product (`FOR UPDATE`) سپس variant (ADR-030). variant یا محصول حذف‌شده/ناموجود → 404. بدون تغییر → 200 بدون history، audit و bump. با تغییر: `price_version += 1`، یک ردیف history، audit `variant.price_changed` در همان تراکنش. پاسخ: قیمت جدید variant (شکل admin).
- `GET /admin/products/{product_id}/price-history` با `pricing:update` یا `catalog:manage`؛ صفحه‌بندی admin، جدیدترین اول، tie-break `id`؛ محصول حذف‌شده هم قابل مشاهده (نمای مدیریت).
- ریسک‌ها: lost update / history ناقص در دو تغییر همزمان (lock؛ تست gather: دو ردیف history زنجیره‌ای)؛ float یا رشته (strict)؛ نشت مجوز (403 برای catalog:manage بدون pricing:update؛ auth قبل از validation)؛ تنوع فعال بدون قیمت (null ممنوع + CHECK).
- Rollback: `alembic downgrade -1` جدول history را حذف می‌کند (فقط dev)؛ `git revert`. قیمت اشتباه با PATCH دوباره برمی‌گردد (history دارد).

## Acceptance Criteria
- [x] هر تغییر قیمت: یک ردیف history و یک audit و `price_version + 1`؛ no-op هیچ‌کدام را ندارد.
- [x] 401، 403 (بدون `pricing:update`)، 400 (float، رشته، null، sale > base، بازه نامعتبر، کلید ناشناخته، بدون فیلد)، 404 (ناموجود/حذف‌شده)، 422 (محصول چندتنوعی) تست شده‌اند.
- [x] دو تغییر همزمان سریال و history زنجیره‌ای است (تست).
- [x] تاریخچه صفحه‌بندی‌شده و مرتب است؛ migration و تست schema.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/db/models/pricing.py` (`PriceHistory` با ستون identity `seq` برای ترتیب قطعی)، migration `20261012_0015`، `app/modules/pricing/{history,price_service,schemas,router,dependencies}.py`، ثبت `prices_router`، history قیمت اولیه در `create_variant` (CAT-11).
- تست: `tests/test_price_changes.py` (۲۹ تست شامل همزمانی و رقابت با حذف variant)؛ سه ردیف جدید در نقشه `COVERAGE`؛ teardownها PriceHistory را اول حذف می‌کنند.
- **Rollback:** `alembic downgrade -1` (فقط dev؛ history حذف می‌شود)؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-11: plan (batch INV-02/PRC-03).
- 2026-10-11: بازبینی plan: APPROVE WITH CHANGES. توقف batch طبق قاعده «ابهام PRD»: معنای `PATCH /admin/products/{id}/price` برای محصول چندتنوعی (D29) از کاربر پرسیده شد. یافته‌های دیگر برای اجرا: ستون‌های BIGINT و CHECK بازه، `new_base_price` NOT NULL، history برای قیمت اولیه در `create_variant` (CAT-11)، 400 برای بدنه نامعتبر و 422 برای تعارض با مقدار ذخیره‌شده، `no-store`، تست رقابت با حذف variant.
- 2026-10-12: D29 = گزینه الف (کاربر). REVIEW-CHECKLIST (خودم): §1، §2، §3، §5، §6، §7، §8، §9 پاس؛ §4 N/A. بازبینی diff: APPROVE WITH CHANGES (ترتیب قطعی history با `seq`، تست‌های no-op audit، history محصول حذف‌شده، 400 endpoint محصول، ثابت مشترک طول دلیل، log بعد از commit؛ اعمال شد). pytest، ruff، format و mypy سبز. COMPLETE.
