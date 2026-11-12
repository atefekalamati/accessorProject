# PAY-01 — Payment model + PaymentGateway interface + fake

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** PAY-00, ORD-01, ADR-009 · **Level:** HIGH

## Objective
مدل پرداخت، interface درگاه و fake با state در Postgres؛ تبدیل تومان↔ریال فقط داخل adapter.

## PRD reference
«پرداخت» ✓؛ ADR-001، ADR-009، ADR-049، ADR-051؛ plan مشترک در [M3.5-PLAN.md](../../docs/project/M3.5-PLAN.md).

## Plan
طبق بخش PAY-01 در M3.5-PLAN (تأیید کاربر 2026-10-19).

## Acceptance Criteria
- [x] جدول‌های `payments`، `payment_events` و `fake_gateway_sessions` با migration `20261019_0024`:
  - CHECKهای چرخه عمر: paid ⟹ `paid_at`؛ refund_required ⟹ `paid_at` و reason؛ `paid_amount`؛ ref ⟺ redirect ⟺ expires.
  - یک pending برای هر سفارش و unique (gateway، ref).
- [x] `PaymentGateway` (request، verify، parse_callback، redact_callback). `toman_to_rial`/`rial_to_toman` فقط در `gateways/`.
- [x] redact: کلیدهای allowlist؛ شماره کارت با فاصله یا خط تیره mask می‌شود؛ ref و کد پیگیری نگه داشته می‌شوند.
- [x] fake: state در DB؛ ref ناشناخته → PENDING؛ session منقضی → FAILED و غیرقابل پرداخت.
- [x] fail-closed: `build_payment_gateway` در production خطا می‌دهد (مثل SMS).
- [x] جدول انتقال جدای ردیف payment.
- [x] fake usable in tests (`tests/test_payment_gateway.py`).

## Log
- 2026-10-19: پیاده‌سازی (plan مشترک M3.5، تأیید کاربر).
  - انحراف: fail-closed در build است، نه در Settings؛ با Settings هر config production تا PAY-07 نامعتبر می‌شد و تست‌های production موجود می‌شکستند (بازبین تأیید کرد؛ در ADR-051).
  - بازبینی diff (opus): PASS WITH CHANGES. اعمال شد: regex کارت با جداکننده؛ ستون `paid_amount` و CHECKهای `refund_was_paid` و `expires_with_reference`؛ index رویداد بر اساس ref؛ fake بعد از انقضا قابل پرداخت نیست؛ redact مسیر ref ناشناخته؛ نگه‌داشتن ref عددی؛ تست UPDATEهای چرخه عمر و CHECKهای event. reconciliation رویداد `verify` می‌نویسد.
  - endpoint فقط-dev `fake/{ref}/complete` به PAY-02 (همراه routerها) منتقل شد.
  - container تست به‌خاطر 0024 پیش‌نویس از نو ساخته شد (بدون volume).
  - pytest (1935)، ruff، format و mypy سبز. COMPLETE.
