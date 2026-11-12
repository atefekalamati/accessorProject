# CNT-01 — HomeSection/items + GET /home

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 5h (estimate) · **Deadline:** — · **Dependencies:** CAT-08, CNT-04 · **Level:** MEDIUM

## Objective
مدل سکشن و آیتم صفحه اصلی و `GET /home` با یک پاسخ کامل.

## PRD reference
«صفحه اصلی» ✓؛ D36، D41، D42 (ADR-053).

## Acceptance Criteria
- [x] جدول‌های `home_sections` و `home_section_items` با migration جدید.
- [x] نوع سکشن‌ها: `hero`، `category_grid`، `product_carousel`، `benefits`، `editorial`.
- [x] فقط سکشن فعال در بازه `[starts_at, ends_at)` به ترتیب `display_order`؛ سکشن بدون آیتم عمومی در خروجی نیست.
- [x] منبع carousel: `manual` (اولویت)، `newest`، `best_selling`، `discount`، `category`؛ حداکثر ۲۰ محصول؛ کارت همان کارت لیست.
- [x] SD rule: محصول و دسته حذف‌شده، منتشرنشده یا غیرفعال در خروجی نیست (تست).
- [x] خروجی پیش‌فرض قابل نمایش وقتی هیچ سکشن فعالی نیست؛ خطای یک سکشن کل صفحه را از کار نمی‌اندازد.

## Implementation Notes
`app/db/models/content.py`، `app/modules/content/`. کارت از `ProductService` دوباره استفاده می‌کند.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-11: GET /home: سکشن‌های فعال در بازه به ترتیب display_order؛ carousel با اولویت آیتم دستی و پرکردن از منبع (newest، best_selling، discount، category)، حداکثر ۲۰ با کارت لیست؛ SD rule برای محصول، دسته و صفحه؛ سکشن خالی یا با مقصد غیرعمومی پنهان؛ خطای یک سکشن جداشده؛ چیدمان پیش‌فرض؛ migration 0031. COMPLETE.
