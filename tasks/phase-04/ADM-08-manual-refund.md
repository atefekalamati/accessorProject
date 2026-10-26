# ADM-08 — Manual refund record (refund_required → refunded)

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ADM-01 · **Level:** HIGH

## Objective
ثبت بازپرداخت دستی پرداخت `refund_required` (D35).

## PRD reference
«مدیریت سفارش» ✓؛ D32، D35 (ADR-053).

## Acceptance Criteria
- [ ] migration: `refunded` در CHECK وضعیت payments و orders.payment_status؛ ستون‌های `refund_reference` (unique)، `refunded_at`، `refunded_by` با CHECK هم‌خوان.
- [ ] `POST /admin/payments/{id}/refund {refund_reference, note?}`: فقط از `refund_required`؛ بازپرداخت کامل (بدون مبلغ در بدنه).
- [ ] idempotent: همان reference → 200 بدون نوشتن؛ reference دیگر روی payment refunded → 409؛ reference تکراری روی payment دیگر → 409.
- [ ] order payment `refund_required → refunded` در همان تراکنش، فقط با `check_transition` (ADR-047 به‌روز می‌شود)؛ history و audit `payment.refunded`.
- [ ] lock: advisory سفارش → ردیف سفارش → ردیف payment (ADR-048)؛ تست همزمانی دو درخواست.
- [ ] مجوز جدید `payments:refund` (seed؛ admin و super_admin)؛ بازبین opus.

## Implementation Notes
`app/modules/payments/admin_router.py`؛ «فروش موفق» تغییری نمی‌کند (refunded فروش نیست).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log

