# INV-05 — Commit / release reservation services

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** INV-04, ADR-008, ADR-036 · **Level:** HIGH

## Objective
سرویس داخلی commit و release رزرو (بدون endpoint عمومی؛ مصرف‌کننده‌ها PAY-03، PAY-04 و لغو سفارش). plan مشترک INV-04..06 و بازنگری آن در `INV-04-reservation-reserve.md` (کاربر تأیید کرد 2026-10-12).

## PRD reference
«موجودی و رزرو» ✓ (رزرو، commit با پرداخت موفق، release با شکست/انقضا)؛ ADR-007، ADR-029، ADR-036.

## Plan (اجرایی)
- `ReservationService.commit(reservation_id, *, actor_id=None, now=None) -> CommitResult` و `release(reservation_id, *, reason, actor_id=None, now=None) -> ReleaseResult`، هر دو فقط در تراکنش فراخواننده (مثل reserve؛ بدون تراکنش → `RuntimeError`).
- ترتیب lock (ADR-036): آیتم‌های رزرو بدون lock خوانده می‌شوند (مجموعه آن‌ها بعد از ساخت تغییر نمی‌کند) → inventory_items `FOR UPDATE` با `ORDER BY variant_id, warehouse_id` → ردیف رزرو `FOR UPDATE`. وضعیت فقط بعد از lock بررسی می‌شود.
- رزرو ناموجود → 404 `NOT_FOUND`.
- **commit:**
  - committed → `ALREADY_COMMITTED` (no-op، بدون movement یا audit).
  - released/expired → `EXPIRED` (no-op).
  - active با `expires_at ≤ now` یا آیتمی که قبلاً released شده (آزادسازی تنبل) → آیتم‌های active باقی‌مانده released (movement `release`، reason `expired`)، status expired، audit `reservation.expired` → `EXPIRED`. نتیجه مقدار برگشتی است (نه exception) تا آزادسازی با rollback از بین نرود. `CommitResult.raise_for_expired()` خطای 409 `RESERVATION_EXPIRED` را برای فراخواننده می‌سازد، بعد از commit تراکنش.
  - active و معتبر → برای هر آیتم `total −= q` و `reserved −= q` (یک UPDATE)، آیتم رزرو committed، movement `commit`؛ status committed، `committed_at`؛ audit `reservation.committed` → `COMMITTED`.
- **release:** reason اجباری (trim، 1..500، وگرنه 400).
  - committed → 409 `RESERVATION_ALREADY_CONSUMED` (قبل از هر تغییر).
  - released/expired → `ALREADY_CLOSED` (no-op).
  - active (منقضی یا نه) → آیتم‌های active released (movement `release` با همان reason)، status released، `released_at`، audit `reservation.released` → `RELEASED`.
- تست‌ها (`tests/test_reservations.py`): commit موفق (شمارنده‌ها، movement، audit، invariant)؛ commit دوباره no-op؛ commit در لحظه انقضا و بعد از آن → EXPIRED و موجودی آزاد شده و بعد از commit تراکنش پایدار؛ commit بعد از آزادسازی تنبل جزئی → EXPIRED؛ commit رزرو released → EXPIRED؛ release موفق؛ release دوباره no-op؛ release بعد از commit → 409؛ release رزرو منقضی؛ reason نامعتبر → 400؛ id ناموجود → 404؛ بدون تراکنش → RuntimeError؛ رقابت commit با release (فقط یکی اثر دارد)؛ دو commit همزمان (یک movement)؛ commit منقضی همزمان با reserve سفارش دیگر روی همان آیتم (بدون دوبار آزادسازی)؛ commit چندتنوعی همزمان با reserve معکوس (بدون deadlock)؛ invariant و `total ≥ 0` بعد از هر تست.

### ریسک‌ها
- کسر دوباره شمارنده: وضعیت per-item زیر lock آیتم + partial unique `uq_inventory_movements_reservation_close` (backstop).
- مصرف رزرو منقضی: `expires_at` و وضعیت آیتم‌ها بعد از lock بررسی می‌شوند.
- deadlock: همان ترتیب lock reserve و job؛ ردیف رزرو همیشه آخر.
- rollback شدن آزادسازی منقضی: نتیجه به‌جای exception.

### Rollback
بدون migration. `git revert` همین commit. هنوز هیچ مسیر API آن را صدا نمی‌زند.

## Acceptance Criteria
- [x] commit: idempotent، منقضی → 409 `RESERVATION_EXPIRED` (از طریق نتیجه) با موجودی آزادشده، معتبر → total و reserved در یک UPDATE.
- [x] release: idempotent، بعد از commit → 409 `RESERVATION_ALREADY_CONSUMED`.
- [x] audit `reservation.committed`، `reservation.released`، `reservation.expired`؛ movement برای هر آیتم.
- [x] تست‌های همزمانی: commit/release، commit/commit، commit منقضی/reserve، بدون deadlock؛ invariant.
- [x] pytest، ruff، format و mypy سبز؛ بازبینی plan و diff.

## Implementation Notes
- کد: `app/modules/inventory/reservation.py` (`commit`، `release`، `CommitOutcome`/`CommitResult.raise_for_expired`، `ReleaseOutcome`، `_lock_reservation`، `_close`، `_live_for_order`)؛ `holds.release_item` حالا `actor_id` می‌گیرد.
- اصلاح INV-04 (یافته بازبین): reserve وضعیت active/committed سفارش را در یک read می‌خواند و `_expire` روی رزرو committed → 409 `RESERVATION_ALREADY_CONSUMED` (قبلاً رقابت re-reserve با commit → IntegrityError/500؛ تست بازتولید کرد).
- release اول reason را validate می‌کند (400 قبل از 404؛ validation first).
- تست: `tests/test_reservations.py` (۴۵ مورد، +۲۲)؛ تست رقابت‌ها ۵ بار پشت سر هم سبز.
- تعهد PAY-03/PAY-04 در PLAN ثبت شد: شاخه روی `CommitOutcome`؛ EXPIRED هرگز سفارش را paid نمی‌کند.

## Log
- 2026-10-12: plan اجرایی از plan مشترک INV-04..06 نوشته شد. REVIEW-CHECKLIST (خودم): §1، §5، §6، §8، §9 مرتبط؛ §2، §3 (فقط reason)، §4، §7 N/A (سرویس داخلی).
- 2026-10-12: بازبینی plan: APPROVE WITH CHANGES (`now` بعد از lock، رقابت re-reserve/commit، نتیجه غیرقابل‌سوءاستفاده، ۴ تست اضافه؛ اعمال شد). بازبینی diff: APPROVE بدون تغییر لازم. pytest 1362 passed، ruff، format و mypy سبز. COMPLETE.
