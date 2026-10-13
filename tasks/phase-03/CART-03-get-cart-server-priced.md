# CART-03 — GET /cart computed server-side with price/stock change flags

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CART-02, PRC-02 · **Level:** HIGH

## Objective
`GET /cart` با مبالغ محاسبه‌شده سرور (تابع خالص قیمت)، flag تغییر قیمت به‌ازای هر خط نسبت به مبنای ذخیره‌شده، و flag وضعیت موجودی؛ به‌علاوه `POST /cart/acknowledge-prices`.

## PRD reference
«سبد خرید» ✓؛ «قیمت و مالیات» ✓ (اعلام تغییر قیمت قبل از پرداخت)؛ ADR-006، ADR-031، ADR-039، ADR-040. تصمیم کاربر (2026-10-12): مبنای per-line؛ ADR-041.

## Plan
- migration `20261012_0018`: `cart_items.seen_unit_price` (BIGINT، CHECK `0..MAX_PRICE_TOMAN`) و `seen_price_version` (INT ≥ 0)، NOT NULL؛ backfill ردیف‌های موجود با قیمت نهایی فعلی variant (همان قاعده بازه sale نیمه‌باز در SQL؛ variant بی‌قیمت → 0). این تغییر schema را کاربر صریحاً تأیید کرد.
- مبنا (تصمیم کاربر): هر نوشتن روی یک خط (افزودن، جمع‌شدن، تغییر تعداد) `seen_*` آن خط را به قیمت نهایی واحد فعلی و `price_version` فعلی می‌برد. `POST /cart/acknowledge-prices` همین کار را برای همه خطوط سبد می‌کند (lock سبد؛ بدون سبد → سبد خالی 200؛ مهمان cookie را تمدید می‌کند). flag فقط UX است؛ امنیت سفارش با fingerprint و 409 در ORD-03/ORD-04 است.
- helper مشترک `variant_price(variant)` در `app/modules/pricing/variants.py` (جایگزین `_variant_price` کاتالوگ، بدون تغییر رفتار).
- `GET /cart` (فقط خواندن، بدون lock و بدون Set-Cookie؛ مهمان یا کاربر بدون سبد → سبد خالی):
  - یک query برای خطوط + variant + product، یک query برای optionها، یک بار `stock_levels_of` برای همه variantها؛ بدون N+1.
  - هر خط: `id`، `variant_id`، `product_id`، `product_title`، `product_slug`، `sku`، `options`، `quantity`، `available` (variant عمومی و قابل‌خرید)، `stock_status` (`ok`، `insufficient`، `out_of_stock`؛ بدون عدد)، `unit_price` (original، final)، `price_changed`، `previous_unit_price` (فقط وقتی تغییر کرده)، و مبالغ خط (`subtotal`، `product_discount`، `code_discount`، `tax`، `total`).
  - خط غیرقابل‌دسترس (`available=false`) در قیمت‌گذاری شرکت نمی‌کند و مبالغش null است؛ خط با موجودی ناکافی قیمت‌گذاری می‌شود و flag می‌خورد.
  - جمع‌ها از `price_order` (تنظیمات از `PricingSettingsRepository.policy()`؛ نبود ردیف → 500 نه، 503؟ → همان خطای داخلی موجود). خطوط به ترتیب id خط به تابع قیمت داده می‌شوند (ADR-031): helper خالص `price_cart_lines` که مرتب می‌کند؛ تست «ورودی به‌هم‌ریخته → خروجی یکسان». `shipping_amount = 0` (ارسال در checkout)؛ کد تخفیف در DSC-03.
  - `Cache-Control: no-store`.
- ریسک‌ها: نشت عدد موجودی (تست کلیدها)؛ N+1 (تست تعداد query)؛ اختلاف قیمت سبد با صفحه محصول (تست برابری با `/products/{id}/pricing`)؛ مبنای اشتباه بعد از sale که شروع یا تمام می‌شود (تست: شروع sale → price_changed با قیمت قبلی)؛ migration backfill (تست upgrade روی ردیف موجود).
- Rollback: `alembic downgrade -1` (فقط dev، ستون‌ها حذف می‌شوند)؛ `git revert`.

## Acceptance Criteria
- [x] `GET /cart` مبالغ سرور، flag قیمت با قیمت قبلی، flag موجودی بدون عدد؛ سبد خالی برای بدون سبد.
- [x] مبنا روی هر نوشتن خط و با `POST /cart/acknowledge-prices` به‌روز می‌شود (تست).
- [x] ترتیب به‌هم‌ریخته خطوط → خروجی یکسان (ADR-031، تست)؛ بدون N+1 (تست).
- [x] مالکیت: هر کس فقط سبد خودش؛ Bearer نامعتبر → 401 (تست).
- [x] migration upgrade/downgrade و backfill (تست)؛ pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/cart/view.py` (`CartView`، `price_cart_lines`)، `service.py` (`is_public`، `is_sellable`، `rebase`، `acknowledge_prices`)، `schemas.py`، `router.py` (`GET /cart`، `POST /cart/acknowledge-prices`)، `app/modules/pricing/variants.py` (`variant_price`، جایگزین helper خصوصی کاتالوگ)؛ migration `20261012_0018`.
- تست: `tests/test_cart_view.py` (۱۴ تست، شامل ترتیب ADR-031، N+1، flag بر اساس قیمت نهایی، مبنای variant بی‌قیمت، نبود تنظیمات → 500، backfill migration).
- **Rollback:** `alembic downgrade -1` (فقط dev)؛ `git revert`.

## Log
- 2026-10-12: plan (batch ۴ جلسه phase؛ تصمیم کاربر روی مبنای per-line و migration).
- 2026-10-12: بازبینی plan (subagent): APPROVE WITH CHANGES؛ همه ۴ مورد must و موارد should اعمال شد (مقایسه فقط قیمت نهایی، مبنا فقط با قیمت موجود، سبد خالی بدون ردیف تنظیمات و نبود ردیف → 500، predicate مشترک `is_sellable`، ADR-041). pytest (1512)، ruff، format و mypy سبز. **commit نشده:** بازبین subagent diff نهایی به‌خاطر محدودیت session API (429) متوقف شد؛ طبق Speed mode بدون آن commit نمی‌شود.
- 2026-10-12: بازبینی diff (subagent، model sonnet طبق قاعده جدید CLAUDE.md): APPROVE WITH CHANGES؛ اعمال شد (حذف N+1 در acknowledge با تست، flag فقط روی خط قابل‌خرید، پوشش محصول draft، یادداشت‌های ADR-041). pytest (1513)، ruff، format و mypy سبز. COMPLETE.
