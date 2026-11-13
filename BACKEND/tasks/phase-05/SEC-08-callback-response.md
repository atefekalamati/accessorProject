# SEC-08 — Payment callback response: outcome only (SECURITY-REVIEW F4)

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 1h (estimate) · **Deadline:** — · **Dependencies:** SEC-03 · **Level:** HIGH

## Objective
`POST /payments/callback` بدون ورود است. هر کسی که reference درگاه را دارد (در تاریخچه مرورگر هم هست) الان `order_number` و وضعیت سفارش و پرداخت را می‌گیرد. تصمیم کاربر (2026-11-13): پاسخ فقط `{outcome}` باشد. جزئیات سفارش را صفحه نتیجه با token از `GET /orders/{order_number}` می‌خواند (ADR-061).

## PRD reference
«معماری سیستم» ✓، ADR-051، SECURITY-REVIEW F4.

## Acceptance Criteria
- [x] پاسخ 200 callback برای هر outcome دقیقاً `{"outcome": ...}` است، بدون شماره یا وضعیت سفارش (تست برای paid، already_processed، refund_required و failed).
- [x] رفتار callback (verify، اعمال در یک تراکنش، idempotency، metrics، no-store، 400/404/429/503) بدون تغییر است.
- [x] تست‌های موجود و smoke staging وضعیت سفارش را از `GET /orders/{order_number}` با token یا از دیتابیس می‌خوانند.
- [x] FRONTEND.md §۷ قرارداد جدید را دارد: شماره سفارش از init یا `POST /orders` نگه داشته می‌شود و وضعیت با token خوانده می‌شود.
- [x] ADR-061 ثبت شد، F4 در SECURITY-REVIEW.md بسته شد، PLAN.md و PROGRESS.md به‌روز شدند.

## Plan
1. `schemas.CallbackResponse` فقط `outcome` دارد. router فقط `outcome` می‌سازد. `Applied` (داخلی، استفاده در reconciliation و log) دست نمی‌خورد.
2. تست‌ها: `test_payments_callback.py` (پاسخ = `{"outcome": "paid"}` و وضعیت از دیتابیس که از قبل خوانده می‌شود)، تست جدید شکل پاسخ برای چند outcome، `test_purchase_e2e.py` (پاسخ = `{"outcome": ...}`، وضعیت از `GET /orders/{order_number}`).
3. `scripts/smoke.py`: بعد از callback، `GET /orders/{order_number}` با token و بررسی `confirmed`/`paid`.
4. FRONTEND.md §۷، ADR-061، SECURITY-REVIEW F4 → رفع‌شده.

**ریسک‌ها:** شکستن قرارداد frontend (هنوز هیچ کدی در `FRONTEND/` این endpoint را صدا نمی‌زند)؛ شکستن smoke staging در CI (در همین task به‌روز می‌شود)؛ snapshot OpenAPI فاز ۴ فقط حذف operation را رد می‌کند و حذف فیلد پاسخ را نه (تغییر عمدی، در snapshot فاز ۵ ثبت می‌شود).
**Rollback:** revert همین commit؛ نه migration دارد نه داده.
**تست‌های اضافه:** شکل پاسخ برای هر outcome قابل دسترس در تست (کلیدها == `{"outcome"}`).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: تصمیم کاربر: پاسخ فقط `outcome` (گزینه پیشنهادی). plan نوشته شد.
- 2026-11-13: بازبین opus (plan): approve with changes؛ رفع شد: بازتولید docs/api/openapi.json، assert no-store در محافظ شکل پاسخ، جریان refresh سمت client و sessionStorage و fallbackها در FRONTEND.md §۷، ثبت ریسک پذیرفته‌شده در ADR-061.
- 2026-11-13: پیاده‌سازی؛ pytest کامل ۲۳۵۲ سبز، ruff و mypy سبز.
- 2026-11-13: بازبین opus (diff نهایی): approve؛ هیچ یافته blocker یا major نبود؛ دو مورد minor (Log و PROGRESS) انجام شده بود. COMPLETE.
