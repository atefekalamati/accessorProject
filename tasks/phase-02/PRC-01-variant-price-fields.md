# PRC-01 — Variant price fields + PricingSetting

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-03, INF-02 · **Level:** HIGH

## Objective
فیلدهای قیمت روی ProductVariant و جدول singleton `pricing_settings` (مالیات خاموش) با migration. بدون endpoint: تغییر قیمت در PRC-03، نمایش قیمت در PRC-04، تنظیمات در PRC-05، و قیمت اولیه در CAT-11 انجام می‌شود.

## PRD reference
«قیمت و مالیات» ✓ (Entityهای ProductVariant و PricingSetting؛ اعتبارسنجی basePrice و salePrice)؛ «محصولات» ✓ (تنوع بدون قیمت معتبر نمی‌تواند فعال باشد)؛ ADR-001، ADR-010، ADR-014، ADR-027؛ M2.2-PLAN.md (جلو آورده شد).

## Acceptance Criteria
- [x] ستون‌های `base_price` و `sale_price` (BIGINT تومان، nullable)، `sale_start_at` و `sale_end_at`، `tax_enabled` (پیش‌فرض false) و `price_version` (پیش‌فرض 0).
- [x] CHECKها: `1 ≤ base ≤ 10^12`؛ `1 ≤ sale ≤ base` و sale بدون base ممنوع؛ `start < end`؛ بازه فقط با sale؛ `price_version ≥ 0`؛ تنوع فعال باید base داشته باشد.
- [x] `pricing_settings`: یک ردیف singleton که migration درج می‌کند، با مقادیر TOMAN، مالیات خاموش، نرخ 0 bps، `nearest` و step 1، `version` برابر 1، و `updated_by` با `SET NULL`. همه مقادیر CHECK دارند و ردیف دوم رد می‌شود.
- [x] migration: variant فعال بدون قیمت غیرفعال و تعداد آن log می‌شود. اگر محصول published باشد، migration با خطا متوقف می‌شود. downgrade و upgrade دوباره id ثابت را درج می‌کنند، بدون ردیف تکراری.
- [x] ثابت‌ها در `app/shared/money.py` (`MAX_PRICE_TOMAN`، `MAX_TAX_RATE_BPS`، `MAX_ROUNDING_STEP`). CHECK حالت گردکردن از `RoundingMode` ساخته می‌شود.
- [x] export، `_MODELS`، `EXPECTED_TABLES` و `HEAD_REVISION` به‌روز شدند. `compare_metadata` بدون تفاوت است.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/db/models/catalog.py`، `app/db/models/pricing.py`، `app/shared/money.py`، `alembic/versions/20261010_0011_add_variant_prices_and_pricing_settings.py`.
- تست: `tests/test_pricing_models.py`. به‌روزرسانی `tests/test_catalog_models.py` (مجموعه ستون‌ها)، `tests/test_category_filters.py` (تنوع فعال حالا قیمت لازم دارد) و `tests/test_database.py`.
- **Rollback:** `alembic downgrade -1` قیمت‌ها و تنظیمات را حذف می‌کند و روی دیتابیس واقعی فقط با تأیید صریح اجرا می‌شود. `is_active` برنمی‌گردد. بعد از آن `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-10: بازبینی plan توسط subagent مستقل: APPROVE WITH CHANGES، بدون blocker. ۱۰ یافته اعمال شد: RAISE برای محصول published، `pricing_settings.version`، ثابت‌ها، ADR-027، تست‌های مرزی و round-trip، و تأیید §5 و §7 چک‌لیست.
- 2026-10-10: بازبینی diff نهایی توسط همان subagent: APPROVE WITH CHANGES. اعمال شد: یک تست flaky (دو `utc_now()` در بازه خالی → یک `NOW` مشترک)، log سطح INFO وقتی چیزی غیرفعال نشده، و نام‌گذاری literalهای migration. یادداشت `ge=1, le=MAX_PRICE_TOMAN` برای CAT-11 و PRC-03 در ADR-027 ثبت است.
- 2026-10-10: COMPLETE. pytest 822 passed (32 تست جدید)؛ ruff، format و mypy سبز.
