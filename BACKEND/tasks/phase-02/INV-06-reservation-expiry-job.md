# INV-06 — Reservation expiry job

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** INV-05, ADR-036 · **Level:** HIGH

## Objective
پاک‌سازی دوره‌ای رزروهای منقضی: آزادسازی آیتم‌های باقی‌مانده و بستن رزرو با status expired. درستی به job وابسته نیست (ADR-036)؛ job فقط شمارنده‌ها و وضعیت را هم‌سو می‌کند. plan مشترک INV-04..06 و بازنگری آن در `INV-04-reservation-reserve.md` (کاربر تأیید کرد 2026-10-12).

## PRD reference
«موجودی و رزرو» ✓ (آزادسازی خودکار رزرو منقضی)؛ ADR-007، ADR-036.

## Plan (اجرایی)
- `app/modules/inventory/jobs.py`:
  - `sweep_expired_reservations(engine, *, now=None, batch_size=100, max_batches=50) -> SweepResult(ran, expired, skipped)`.
  - یک اجراکننده: `pg_try_advisory_lock(JOB_LOCK_NAMESPACE, 1)` روی یک اتصال جدا که تا پایان sweep نگه داشته می‌شود (session-level، در `finally` آزاد). اگر گرفته نشد → `ran=False`.
  - انتخاب: `status='active' AND expires_at <= now ORDER BY expires_at, id LIMIT batch_size` با keyset `(expires_at, id) > cursor`، تا رزروی که رد شده (قفل) loop بی‌پایان نسازد. سقف `max_batches`.
  - هر رزرو در تراکنش جدا (ADR-036): `ReservationService.expire(reservation_id, now)` → آیتم‌ها `FOR UPDATE` به ترتیب `variant_id, warehouse_id` (همان ترتیب commit/release) → ردیف رزرو `FOR UPDATE SKIP LOCKED`. اگر قفل نشد، یا دیگر active نیست، یا `expires_at > now` → رد (skipped). وگرنه آیتم‌های active باقی‌مانده released (movement `release`، reason `expired`)، status expired، audit `reservation.expired` با actor=system (actor_id None).
  - `now` هر رزرو بعد از lock از `utc_now()` (یا مقدار تزریقی تست).
  - خطای یک رزرو log می‌شود و sweep ادامه می‌دهد (تراکنش همان رزرو rollback).
- اجرا:
  - setting جدید `RESERVATION_SWEEP_SECONDS` (int، پیش‌فرض 60، `0..3600`، صفر = خاموش) در `Settings` و `.env.example`. fixture تست `settings` آن را صفر می‌کند.
  - lifespan برنامه: اگر > 0، یک `asyncio.Task` که هر بازه sweep را اجرا می‌کند (اول sleep). هر exception log می‌شود و loop ادامه می‌دهد. در shutdown، task cancel و منتظر پایان می‌شود.
  - دستی: `python -m app.modules.inventory.jobs` یک sweep با `get_settings()`.
  - بدون dependency جدید و بدون migration (index `(status, expires_at)` از INV-04 هست).
- تست‌ها (`tests/test_reservation_jobs.py`): رزروهای منقضی expired و آزاد می‌شوند، فعال‌ها دست نمی‌خورند؛ رزرو نیمه‌آزادشده (تنبل) بسته می‌شود بدون movement دوم؛ audit با actor system؛ batch کوچک (batch_size=2 با ۵ رزرو)؛ رزرو قفل‌شده (FOR UPDATE در تراکنش دیگر) رد می‌شود و sweep تمام می‌شود؛ advisory lock گرفته‌شده توسط دیگری → `ran=False`؛ دو sweep همزمان → هر رزرو فقط یک‌بار expired (یک audit، یک movement برای هر آیتم)؛ رقابت commit با job (commit با `now` معتبر، job با `now` بعد از انقضا): یا COMMITTED و job رد می‌کند، یا expired و commit `EXPIRED` — هرگز هر دو؛ رقابت release با job؛ loop در lifespan با بازه کوتاه شروع و در shutdown بسته می‌شود؛ setting نامعتبر (منفی) → خطای Settings؛ invariant بعد از هر تست.

### ریسک‌ها
- دوبار آزادسازی: وضعیت per-item زیر lock آیتم + partial unique movement (backstop).
- deadlock: همان ترتیب lock؛ ردیف رزرو با SKIP LOCKED.
- loop بی‌پایان یا sweep بلند: keyset cursor + `max_batches`.
- چند instance: advisory lock + SKIP LOCKED.
- task پس‌زمینه که بی‌صدا می‌میرد: هر دور try/except با log؛ تست lifespan.

### Rollback
بدون migration. `RESERVATION_SWEEP_SECONDS=0` job را خاموش می‌کند؛ `git revert`.

## Acceptance Criteria
- [x] رزروهای منقضی expired و آیتم‌هایشان آزاد می‌شوند؛ فعال‌ها دست نمی‌خورند؛ audit با actor=system.
- [x] SKIP LOCKED، `lock_timeout` و advisory lock: commit/release در حال اجرا منتظر می‌ماند یا رد می‌شود؛ دو job همزمان یک رزرو را دو بار آزاد نمی‌کنند.
- [x] رقابت commit با job: هرگز هر دو.
- [x] setting `RESERVATION_SWEEP_SECONDS` (صفر = خاموش)، loop در lifespan، اجرای دستی.
- [x] pytest، ruff، format و mypy سبز؛ بازبینی plan و diff.

## Implementation Notes
- کد: `app/modules/inventory/jobs.py` (`sweep_expired_reservations`، `SweepResult(ran, expired, skipped, failed)`، `run_sweeper`، `__main__`)، `ReservationService.expire` و `_lock_reservation(skip_locked)` در `reservation.py`، lifespan در `app/main.py`، `reservation_sweep_seconds` در `Settings` و `.env.example`، fixture `settings` با صفر.
- تغییرات بازبین plan: advisory lock تراکنشی (بدون نشت)؛ `lock_timeout` برای هر رزرو و 55P03 = skipped؛ `expire` هرگز برای وضعیت exception نمی‌دهد؛ تست‌ها فقط روی شناسه‌های خودشان؛ تست‌های `expire` همزمان و job در برابر release.
- تغییرات بازبین diff: poll قفل محدود به دیتابیس همین worker (از طریق `pg_stat_activity`، چون waitهای transactionid در `pg_locks` دیتابیس ندارند)؛ `idle_in_transaction_session_timeout = 0` روی guard؛ `batch_size`/`max_batches` < 1 → `ValueError`.
- تست: `tests/test_reservation_jobs.py` (۱۹ مورد).

## Log
- 2026-10-12: plan اجرایی از plan مشترک INV-04..06. REVIEW-CHECKLIST (خودم): §1، §6، §7 (setting جدید)، §8، §9 مرتبط؛ §2، §3، §4 N/A؛ §5 بدون schema.
- 2026-10-12: بازبینی plan: APPROVE WITH CHANGES (۴ مورد، اعمال شد). بازبینی diff: APPROVE WITH CHANGES (۱ مورد لازم: محدودکردن poll قفل؛ اعمال شد، به‌علاوه دو مورد اختیاری). pytest 1381 passed، ruff، format و mypy سبز. COMPLETE.
