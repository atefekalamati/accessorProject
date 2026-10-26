# PAY-06 — End-to-end purchase test

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** PAY-05 · **Level:** HIGH

## Objective
خرید کامل فقط از API عمومی، در pytest و در smoke staging (OPS-08).

## PRD reference
«پرداخت» ✓ (معیار پذیرش: سبد → OTP → checkout → سفارش → پرداخت → commit موجودی)؛ [M3.5-PLAN.md](../../docs/project/M3.5-PLAN.md).

## Acceptance Criteria
- [x] cart → OTP → checkout → order → payment → stock committed (`tests/test_purchase_e2e.py`):
  - مسیر کامل: سبد مهمان → ادغام بعد از ورود → کد تخفیف.
  - redemption confirmed؛ سبد و کد خالی؛ پرداخت یا لغو دوباره 422.
- [x] شکست → retry → موفق (رزرو در این فاصله نگه داشته می‌شود).
- [x] انقضا → refund_required، موجودی دست‌نخورده، سبد باقی.
- [x] smoke staging: stage جدید `purchase` در `scripts/smoke.py`:
  - محصول قابل فروش با API ادمین ساخته می‌شود (تصویر PNG با stdlib).
  - خرید کامل با درگاه fake، و بررسی commit موجودی در تاریخچه.
  - step جدید در CI؛ تنظیمات PAYMENT_* صریح در env staging.
  - یک بار به‌صورت محلی روی uvicorn واقعی اجرا و سبز شد.

## Log
- 2026-10-25: پیاده‌سازی (plan مشترک M3.5).
  - بازبینی (opus): PASS WITH CHANGES.
  - اعمال شد:
    - assertion redemption confirmed.
    - بررسی واقعی commit موجودی در smoke.
    - status قبل از json.
    - PAYMENT_* صریح در CI.
    - ساخت data بدنه در `_call`.
    - ref از path آدرس.
  - `GET /orders/{id}` هنوز وجود ندارد (ACC-01) و وضعیت از پاسخ callback و DB بررسی می‌شود.
  - pytest (2005)، ruff، format و mypy سبز. COMPLETE.
