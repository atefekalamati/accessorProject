# ORD-05 — Order state machine (order/payment/shipment)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ORD-01 · **Level:** HIGH

## Objective
انتقال‌های مجاز سه وضعیت مستقل سفارش، با ثبت تاریخچه و audit؛ انتقال نامعتبر → 422 `INVALID_STATE_TRANSITION`. بدون endpoint (لغو مشتری در ORD-04/06، پرداخت در PAY، ادمین در فاز ۴).

## PRD reference
«نتیجه سفارش» ✓ (سه وضعیت)؛ ADR-039 (D32، D34)؛ ADR-046.

## Plan (batch ORD-03/ORD-05/CAT-17)
- `app/modules/orders/state.py` (خالص): جدول‌ها
  - order: `pending_payment → confirmed | cancelled`، `confirmed → completed`.
  - payment: `unpaid → pending`، `pending → paid | failed | refund_required`، `failed → pending`.
  - shipment: `not_shipped → preparing → shipped → delivered`.
  - guardهای بین فیلدها (`check_transition(snapshot, field, new)`): order→confirmed فقط با payment `paid`؛ order→completed فقط با shipment `delivered`؛ order→cancelled فقط وقتی payment `paid` نیست؛ payment→pending/paid فقط با order `pending_payment`؛ payment→refund_required فقط با order `cancelled` (D32)؛ shipment→preparing فقط با order `confirmed`. cancel بدون reason → ValueError (برنامه‌نویسی)، reason با `CancelReason`.
- `app/modules/orders/state_service.py`: `OrderStateService(session).transition(order_id, field, new_status, *, actor_user_id, reason=None, cancel_reason=None, request=None)` در تراکنش فراخواننده؛ ردیف سفارش `FOR UPDATE` + `populate_existing`، بررسی، اعمال، ردیف `order_status_history`، audit `order.status_changed` (field، before، after، reason؛ actor null = system)؛ سفارش ناموجود → 404؛ نامعتبر → 422 با `details` (`field`، `from`، `to`). همان وضعیت → 422 (no-op مجاز نیست).
- ترتیب lock (ADR-047): ردیف سفارش بلافاصله بعد از advisory سفارش و قبل از inventory؛ مسیر انقضا (INV-06/ORD-06) که سفارش را لغو می‌کند باید اول ردیف سفارش را قفل کند (یادداشت برای ORD-04/06).
- **ریسک‌ها:** (۱) انتقال غیرمجاز → تست جدولی همه جفت‌ها × سه فیلد؛ (۲) رقابت دو انتقال → تست همزمانی (دو cancel → یکی موفق، دیگری 422)؛ (۳) تاریخچه/audit جاافتاده → تست؛ (۴) deadlock با مسیر انقضا → ترتیب lock مستند.
- **Rollback:** `git revert` (بدون schema).

## Acceptance Criteria
- [x] invalid transitions → 422 (تست جدولی).
- [x] تاریخچه و audit برای هر انتقال؛ همزمانی (تست).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/orders/state.py` (جدول و guardها)، `app/modules/orders/state_service.py` (`OrderStateService.transition` → `Transition`). تست: `tests/test_order_state.py`.
- همان وضعیت → 422 با type `same_status` (لغو تکراری قابل تشخیص). منبع actor سیستمی در `reason`.
- **Rollback:** `git revert`.

## Log
- 2026-10-18: plan (batch ۳ جلسه phase؛ بازبین opus چون وضعیت پرداخت).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES؛ اعمال شد: ADR-047 نوشته شد (ترتیب lock: ردیف سفارش قبل از inventory؛ job انقضا در ORD-06 باید اول ردیف سفارش را با `SKIP LOCKED` + `lock_timeout` قفل کند)؛ payment: `failed → paid` (با order pending_payment) و `failed → refund_required` (با order cancelled) اضافه شد؛ PAY-03 قبل از refund_required سفارش را لغو می‌کند؛ `cancel_reason` فقط برای انتقال به cancelled و جدا از `reason` آزاد (≤۵۰۰). همان وضعیت 422 می‌ماند؛ لغو idempotent در ORD-04/06 تصمیم‌گیری می‌شود.
- 2026-10-18: بازبینی diff (opus): PASS WITH CHANGES؛ اعمال شد (تست همزمانی قطعی با lock نگه‌داشته و انتظار روی pg_locks، assert تعداد audit، نتیجه `Transition` با old/new، trim کردن reason، type `same_status`، تست actor کاربر، docstring دو انتقال در یک تراکنش). pytest (1846)، ruff، format و mypy سبز. COMPLETE.
