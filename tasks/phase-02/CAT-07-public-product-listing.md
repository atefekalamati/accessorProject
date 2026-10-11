# CAT-07 — Public product listing GET /products and GET /categories/{slug}/products

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 6h (estimate) · **Deadline:** — · **Dependencies:** CAT-03, INF-03, PRC-02, INV-03 · **Level:** MEDIUM

## Objective
لیست عمومی محصولات منتشرشده با فیلتر allowlist، مرتب‌سازی و صفحه‌بندی سمت بک‌اند. قیمت و موجودی هر کارت در هر درخواست تازه محاسبه می‌شود (PRC-02، INV-03).

## PRD reference
«دسته‌بندی محصولات» ✓ (خط 1287–1580)، «جزئیات محصول» ✓ (`GET /products`، خط 1864)؛ ADR-020، ADR-022، ADR-026، ADR-029، ADR-031. تصمیم‌های کم‌اثر: ADR-032.

## Plan
- `app/shared/pagination.py`: helper مشترک `paginate(session, statement, order_by, params)`: count روی subquery، سپس offset/limit با tie-break قطعی `id`.
- `app/modules/catalog/product_query.py` (جدید): عبارت SQL قیمت نهایی (آینه `unit_price`: بازه نیمه‌باز)، subquery آمار هر محصول روی تنوع‌های فعال، قیمت‌دار و حذف‌نشده (`min_final`، `max_final`، `max_discount_percent`)، و criteriaهای فیلتر.
- `ProductRepository.list_public(...)` و `price_bounds(category_id, now)`؛ `ProductService.list(...)`؛ schemaهای `ProductCard` و `ProductListResponse` (= `Page[ProductCard]`).
- routerها: `GET /products` (با `category_slug` اختیاری) و `GET /categories/{slug}/products`؛ `allowed_query_params`؛ `Cache-Control: no-store`.
- فیلترها: `min_price`، `max_price`، `in_stock`، `has_discount`، `colors`، `sizes`، `materials`، `brands` (پارامتر تکراری) و `attributes=key:value` (تکراری). sortها: `newest` (پیش‌فرض)، `price_asc`، `price_desc` و `discount_desc`.
- `GET /categories/{slug}/filters`: فیلتر `price` (range) با `min` و `max` (طبق ADR-026).
- تست fixture `Catalog` از `test_products_public.py` به `conftest.py` منتقل می‌شود تا مشترک باشد.
- ریسک‌ها: کوئری سنگین (سقف limit و page، سقف تعداد مقدار فیلتر، indexهای موجود `status, published_at` و `category_id`، بدون migration)؛ ناسازگاری عبارت SQL قیمت با `unit_price` (تست مرز بازه sale و تست سازگاری ترتیب با قیمت کارت)؛ تکرار یا جاافتادن ردیف بین صفحه‌ها (tie-break `id` و تست DB)؛ N+1 (تعداد query ثابت، تست).

## Acceptance Criteria
- [x] `GET /products` و `GET /categories/{slug}/products` بدون احراز هویت؛ پارامتر ناشناخته، sort ناشناخته (شامل `best_selling` تا CAT-17)، page/limit خارج از محدوده، `min_price > max_price` و مقدار فیلتر نامعتبر → 400.
- [x] فقط محصول published و حذف‌نشده با حداقل یک تنوع فعال و قیمت‌دار؛ تنوع غیرفعال یا حذف‌شده در قیمت، فیلتر و موجودی حساب نمی‌شود (SD rule، تست).
- [x] دسته پنهان (خودش یا جدش) یا ناموجود → 404؛ محصولات زیرمجموعه‌ها در لیست دسته نمی‌آیند (ADR-026).
- [x] فیلتر ویژگی که در CategoryFilterهای فعال دسته نیست → 422.
- [x] فیلتر قیمت روی قیمت نهایی کارت (کمترین `final_price`)؛ `in_stock` و `has_discount` و فیلترهای گزینه/ویژگی درست (تست).
- [x] sortها درست با tie-break قطعی `id`؛ بدون تکرار یا جاافتادن بین صفحه‌ها و `total` درست (تست DB).
- [x] کارت: `id`، `slug`، `title`، `published_at`، `image_url`، `price` (تنوع ارزان‌تر)، `price_range`، `max_discount_percent`، `availability`، `quick_add_variant_id`؛ بدون عدد موجودی یا فیلد داخلی (تست کلیدها).
- [x] بدون N+1: تعداد query مستقل از تعداد محصول و تنوع (تست).
- [x] فیلتر `price` در `GET /categories/{slug}/filters` با `min` و `max`.
- [x] `Cache-Control: no-store`.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/catalog/product_query.py` (جدید: `final_price`، `public_products`، `price_bounds`)، `product_repository.py` (`list_public`، `public_variants_of`)، `product_service.py` (`list_products`، `ListingRequest`؛ قاعده `_purchasable` با CAT-08 مشترک شد)، `router.py` (`listing_request` و دو route)، `repository.py` و `service.py` (بازه `price` در `/filters`)، `schemas.py` (`ProductCard`)، `app/shared/pagination.py` (`paginate`، `AnySelect`).
- تست: `tests/test_products_list.py` (۳۰ تست)؛ builder `Catalog` به `tests/conftest.py` منتقل شد و `test_products_public.py` از آن import می‌کند.
- **Rollback:** بدون schema و migration؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-11: plan (batch CAT-07/CAT-12، AUTOPILOT: MEDIUM و بدون استثنا).
- 2026-10-11: پیاده‌سازی؛ تصمیم‌های کم‌اثر در ADR-032. pytest (1183 passed)، ruff، format و mypy سبز. COMPLETE.
