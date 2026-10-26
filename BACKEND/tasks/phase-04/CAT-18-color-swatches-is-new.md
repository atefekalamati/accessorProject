# CAT-18 — Color swatches + is_new in product summaries

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ACC-00 · **Level:** MEDIUM

## Objective
نمونه رنگ (hex) و نشان «جدید» در خلاصه محصول، طبق طراحی storefront E (D42).

## PRD reference
«دسته‌بندی محصولات» ✓ (کارت)، «صفحه اصلی» ✓؛ ADR-032، ADR-053.

## Acceptance Criteria
- [x] migration `variant_options.hex` (nullable؛ فقط `option_key = 'color'`؛ CHECK `^#[0-9A-F]{6}$`). ورودی lowercase نرمال می‌شود؛ مقدار نامعتبر → 400.
- [x] API ادمین تنوع (ایجاد و ویرایش) `options.color` را به‌همراه `color_hex` اختیاری می‌پذیرد. hex روی کلید غیر color → 400.
- [x] کارت `GET /products` و `GET /categories/{slug}/products`: `color_swatches` = تا ۵ رنگ متمایز از تنوع‌های عمومی به ترتیب `display_order`، هر کدام `{value, hex}` (`hex` null مجاز).
- [x] `is_new` = `created_at` در `PRODUCT_NEW_DAYS` روز اخیر (Settings، پیش‌فرض ۳۰، placeholder در `.env.example`).
- [x] جزئیات محصول (`GET /products/{slug}`) در `variants[].options` و `options` هم hex دارد.
- [x] تعداد query لیست ثابت می‌ماند (بدون N+1). تست‌ها: سقف ۵، ترتیب، تنوع غیرعمومی، مرز ۳۰ روز.
- [x] `EXPECTED_TABLES`/revision در `tests/test_database.py`؛ `openapi.json` دوباره export شود.

## Implementation Notes
`app/db/models/catalog.py`، migration جدید، `app/modules/catalog/` (schemas، repository لیست، admin variant)، `app/core/config.py`. CAT-07/CAT-08 helper مشترک کارت را دارند و `/home` (CNT-01) همان کارت را استفاده می‌کند.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: پیاده‌سازی (batch 2).
  - migration `20261026_0025`.
  - `VariantOptions.color_hex`: فقط همراه `color` مجاز است؛ lowercase پذیرفته و upper ذخیره می‌شود.
  - options کامل فرستاده می‌شود، پس نفرستادن `color_hex` آن را پاک می‌کند. تغییر فقط hex هم update و audit دارد.
  - `color_swatches` در کارت (حداکثر ۵) و در جزئیات (بدون سقف) آمده؛ `color_hex` روی هر تنوع جزئیات؛ `is_new` روی کارت و جزئیات.
  - یک query اضافه در لیست (`colors_of`)؛ تعداد query ثابت است (تست).
  - `PRODUCT_NEW_DAYS` در Settings و `.env.example`. `openapi.json` دوباره export شد.
  - Level MEDIUM: بازبین subagent لازم نیست.
  - در همین batch، repo به monorepo تبدیل شد: commit `ebcfbd5`، `BACKEND/` و `FRONTEND/`، CI سبز. `name: atk` در compose تا volumeهای موجود حفظ شوند.
  - pytest (2026)، ruff، format و mypy سبز. COMPLETE.

