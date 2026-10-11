# INV-07 — Public GET /products/{id}/availability

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** INV-03, CAT-08 · **Level:** HIGH

## Objective
وضعیت موجودی محصول منتشرشده و تنوع‌های عمومی آن (in/low/out و قابل‌خرید)، بدون عدد موجودی.

## PRD reference
«موجودی و رزرو» ✓ (خط 784–950)؛ ADR-005، ADR-029، ADR-020. تصمیم‌های کم‌اثر: ADR-033.

## Plan (batch PRC-04/PRC-05/INV-07)
- route `GET /products/{product_id}/availability` با `variant_id` اختیاری؛ همان بارگذاری PRC-04 (محصول منتشرشده، تنوع‌های عمومی، InventoryItem انبارهای فعال در یک query).
- پاسخ: `product_id`، `availability` (بهترین وضعیت، ADR-029)، `variants[]` (`variant_id`، `sku`، `availability`، `purchasable`). «حداکثر تعداد قابل خرید» و اعداد موجودی عمومی نیستند (ADR-029، CAT-00 ردیف ۸).
- فقط‌خواندنی و بدون lock (ADR-029: نمایش ممکن است کمی کهنه باشد، فقط در جهت کمتر). `Cache-Control: no-store`.
- ریسک‌ها: نشت عدد موجودی (تست کلیدها)؛ ناهمخوانی با detail (تست برابری)؛ انبار غیرفعال (فقط انبار فعال؛ تست).
- Rollback: بدون schema؛ `git revert`.

## Acceptance Criteria
- [ ] وضعیت و purchasable برابر `GET /products/{slug}` (تست)؛ تنوع بدون InventoryItem → out_of_stock؛ رزرو کامل → out_of_stock؛ low_stock طبق threshold.
- [ ] InventoryItem انبار غیرفعال حساب نمی‌شود (تست).
- [ ] SD rule و 404/400 مثل PRC-04 (تست).
- [ ] بدون عدد موجودی یا فیلد داخلی (تست کلیدها)؛ `Cache-Control: no-store`.
- [ ] بدون N+1 (تعداد query مستقل از تعداد تنوع؛ تست).
- [ ] pytest، ruff، format و mypy سبز.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-11: plan (batch PRC-04/PRC-05/INV-07).
