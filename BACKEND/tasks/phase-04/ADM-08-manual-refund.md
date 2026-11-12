# ADM-08 — Manual refund record (refund_required → refunded)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ADM-01 · **Level:** HIGH

## Objective
ثبت بازپرداخت دستی پرداخت `refund_required` (D35).

## PRD reference
«مدیریت سفارش» ✓؛ D32، D35 (ADR-053).

## Acceptance Criteria
- [x] migration: `refunded` در CHECK وضعیت payments و orders.payment_status؛ ستون‌های `refund_reference` (unique)، `refunded_at`، `refunded_by` با CHECK هم‌خوان.
- [x] `POST /admin/payments/{id}/refund {refund_reference, note?}`: فقط از `refund_required`؛ بازپرداخت کامل (بدون مبلغ در بدنه).
- [x] idempotent: همان reference → 200 بدون نوشتن؛ reference دیگر روی payment refunded → 409؛ reference تکراری روی payment دیگر → 409.
- [x] order payment `refund_required → refunded` در همان تراکنش، فقط با `check_transition` (ADR-047 به‌روز می‌شود)؛ history و audit `payment.refunded`.
- [x] lock: advisory سفارش → ردیف سفارش → ردیف payment (ADR-048)؛ تست همزمانی دو درخواست.
- [x] مجوز جدید `payments:refund` (seed؛ admin و super_admin)؛ بازبین opus.

## Implementation Notes
`app/modules/payments/admin_router.py`؛ «فروش موفق» تغییری نمی‌کند (refunded فروش نیست).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: plan در [M4.2-BATCH4-PLAN.md](../../docs/project/M4.2-BATCH4-PLAN.md).
  - بازبینی plan (opus): APPROVE WITH CHANGES. توقف برای دو تصمیم کاربر؛ هر دو تأیید شد (ADR-054).
- 2026-10-26: پیاده‌سازی.
  - migration `0027`.
  - `RefundService` (`app/modules/payments/refunds.py`).
  - `POST /admin/payments/{id}/refund`.
  - no-op `refunded` در `_decide`؛ `move_payment` برای refunded ممنوع است.
  - انتقال‌های جدید ردیف payment و order payment.
  - فیلدهای refund در پاسخ‌های ادمین.
  - تست‌ها (`tests/test_admin_refunds.py`، ۸ تست، ۳ اجرای پشت هم سبز):
    - مبلغ درگاه و مبلغ ادمین
    - بازگشت `refund_required`
    - انتظار برای همه paymentهای بدهکار
    - duplicate روی سفارش paid بدون تغییر order
    - وضعیت نامعتبر و reference تکراری
    - همزمانی سه حالت
    - callback بعد از بازپرداخت no-op
    - مجوزها
  - deploy: `python -m app.db.seed` برای `payments:refund`.
  - بازبینی diff (opus): PASS WITH CHANGES. اعمال شد:
    - الگوی reference در API و DB یکی شد (C0، DEL، C1، U+2028/2029)، تا ورودی 500 ندهد.
    - `paid_amount = 0` → 422 `nothing_to_refund`.
    - بخش «پرداخت»/«نتیجه سفارش» PRD `refunded` را دارد.
    - یادداشت no-PII برای `note`.
  - موارد INFO ثبت شدند و اقدامی لازم نداشتند:
    - سقف `grand_total` برای مبلغ ادمین، طبق تصمیم کاربر
    - تست super_admin و reopen با mismatch اختیاری‌اند
  - pytest (2059)، ruff، format و mypy سبز. COMPLETE.

