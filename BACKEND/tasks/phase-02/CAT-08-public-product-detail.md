# CAT-08 — Public product detail GET /products/{slug}

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CAT-00, CAT-04, CAT-05, PRC-02, INV-03 · **Level:** MEDIUM

## Objective
endpoint عمومی جزئیات محصول منتشرشده با تنوع‌های فعال، قیمت محاسبه‌شده در بک‌اند (PRC-02)، وضعیت موجودی (INV-03) و رسانه‌ها، طبق قرارداد PRD.

## PRD reference
«جزئیات محصول» ✓ (خط 1786–1940)؛ ADR-020، ADR-022، ADR-029، ADR-031.

## Acceptance Criteria
- [x] `GET /products/{slug}` بدون احراز هویت؛ slug نامعتبر → 400 قبل از query؛ پارامتر query ناشناخته → 400.
- [x] فقط محصول published و حذف‌نشده؛ draft، archived، soft-deleted و ناموجود → 404 با بدنه یکسان (SD rule).
- [x] قرارداد: `id`، `slug`، `title`، `description`، `published_at`، `breadcrumb`، `attributes`، `options`، `variants` (price، availability، purchasable)، `default_variant_id`، `price_range` (روی final)، `tax_included` (false)، `availability`، `media` (اصلی اول).
- [x] فقط تنوع فعال و حذف‌نشده؛ رسانه تنوع پنهان نمی‌آید.
- [x] قیمت با `unit_price` (بازه نیمه‌باز)؛ `sale_price` خارج از بازه null.
- [x] purchasable = فعال ∧ `is_purchasable` ∧ قیمت ∧ free > 0؛ availability از InventoryItem انبار فعال؛ بدون InventoryItem → out.
- [x] پاسخ بدون عدد موجودی یا فیلد داخلی (تست کلیدها؛ schema صریح).
- [x] دسته پنهان (غیرفعال یا حذف‌شده، یا جد پنهان) از breadcrumb حذف می‌شود و صفحه 200 می‌ماند.
- [x] بدون N+1: تعداد query مستقل از تعداد تنوع و رسانه (تست).
- [x] `Cache-Control: no-store` (قیمت و موجودی هر درخواست تازه).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/catalog/product_service.py` (جدید)، `product_repository.py` (`get_published`، `category_chain`؛ کلاس به `ProductRepository` تغییر نام داد چون admin و عمومی مشترک‌اند)، `schemas.py`، `router.py` (`products_router`)، `dependencies.py`، `app/api/v1/router.py`.
- تست: `tests/test_products_public.py`.
- breadcrumb = بخش قابل‌نمایش زنجیره از ریشه تا اولین دسته پنهان (ADR-022 پیشوندبسته است).
- **Rollback:** بدون schema؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-11: پیاده‌سازی و ۱۳ تست API (قرارداد، SD rule، 400، قیمت، موجودی، breadcrumb، شمارش query). COMPLETE.
