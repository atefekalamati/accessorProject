# PRC-04 — Public GET /products/{id}/pricing

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** PRC-02 · **Level:** HIGH

## Objective
قیمت فعلی محصول منتشرشده و تنوع‌های عمومی آن، فقط محاسبه‌شده در بک‌اند با `unit_price` (PRC-02).

## PRD reference
«قیمت و مالیات» ✓ (خط 495–580)؛ ADR-020 (id برای pricing)، ADR-027، ADR-031، ADR-032. تصمیم‌های کم‌اثر: ADR-033.

## Plan (batch PRC-04/PRC-05/INV-07)
- route `GET /products/{product_id}/pricing` در `products_router`، با `variant_id` اختیاری (`allowed_query_params`). id غیر UUID → 400.
- `ProductRepository.get_published_by_id`؛ تنوع‌ها با `public_variants_of` (فعال، قیمت‌دار، حذف‌نشده) — همان مجموعه CAT-07/CAT-08.
- پاسخ: `product_id`، `currency` (TOMAN)، `tax_included` (false)، `calculated_at` (همان `now` محاسبه؛ «timestamp محاسبه» PRD)، `price_range`، `variants[]` (`variant_id`، `sku`، `price` با شکل `VariantPriceOut`). بدون `price_version`، `tax_enabled` یا عدد موجودی.
- محصول draft/archived/حذف‌شده/ناموجود → 404 یکسان؛ `variant_id` که تنوع عمومی همین محصول نیست → 404. `Cache-Control: no-store`.
- ریسک‌ها: نشت فیلد داخلی (schema صریح، تست کلیدها)؛ ناهمخوانی با detail و listing (تست برابری با `GET /products/{slug}`)؛ تنوع حذف‌شده یا غیرفعال (SD rule، تست).
- Rollback: بدون schema؛ `git revert`. تست‌های اضافه: برابری با detail، بازه sale، SD rule.

## Acceptance Criteria
- [x] قیمت‌ها برابر `unit_price` در لحظه درخواست و برابر قیمت‌های `GET /products/{slug}` (تست).
- [x] SD rule: محصول پنهان → 404 یکسان؛ تنوع غیرفعال/حذف‌شده نمی‌آید و با `variant_id` → 404 (تست).
- [x] 400 برای id یا `variant_id` غیر UUID و پارامتر ناشناخته.
- [x] بدون فیلد داخلی (تست کلیدها)؛ `Cache-Control: no-store`.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `product_service.py` (`pricing`، `_public_variants`؛ جزئیات هم حالا از `public_variants_of` استفاده می‌کند تا تعریف «تنوع عمومی» یک‌جا باشد)، `product_repository.py` (`get_published_by_id`)، `router.py`، `schemas.py` (شامل schemaهای INV-07). تست: `tests/test_product_pricing.py` (۹ تست)؛ ردیف جدید در نقشه `COVERAGE` (CAT-12).
- **Rollback:** بدون schema؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-11: plan (batch PRC-04/PRC-05/INV-07؛ تأیید کاربر برای همه milestoneهای باقی‌مانده فاز ۲).
- 2026-10-11: REVIEW-CHECKLIST (خودم): §3، §5، §7، §9 پاس؛ §1، §2، §4، §6، §8 N/A (خواندن عمومی). بازبینی plan توسط subagent: APPROVE WITH CHANGES (ADR-033 اضافه شد). بازبینی diff: APPROVE؛ یافته‌های کم‌اهمیت اعمال شد (تست محصول بدون تنوع عمومی، `calculated_at`، تعریف مشترک تنوع عمومی). pytest (1231+)، ruff، format و mypy سبز. COMPLETE.
