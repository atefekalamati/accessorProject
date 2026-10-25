# PAY-04 — Failure/expiry: release reservation, allow retry; reconciliation

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** PAY-03, INV-06 · **Level:** HIGH

## Objective
شکست پرداخت سفارش را قابل پرداخت نگه دارد؛ job تطبیق، callbackهای گم‌شده و درخواست‌ها و sessionهای رهاشده را با verify درگاه حل کند (ADR-049).

## PRD reference
«پرداخت» ✓؛ ADR-049، ADR-050، ADR-051؛ [M3.5-PLAN.md](../../docs/project/M3.5-PLAN.md).

## Acceptance Criteria
- [x] failure keeps reservation + redemption for retry within TTL (PAY-03)؛ retry بعد از failed → payment جدید.
- [x] reservation expiry cancels the order (ORD-06)؛ expired reservation never consumed (PAY-03).
- [x] `release()` after commit → 409 handled: هیچ مسیری رزرو committed را آزاد نمی‌کند؛ لغو سفارش confirmed → 422 (ORD-06)؛ `tests/test_reservations.py`.
- [x] job تطبیق زیر advisory lock: callback گم‌شده → اعمال؛ ref NULL → `request_lost`؛ PENDING طولانی → `abandoned`؛ درگاه بی‌پاسخ → بدون تغییر و توقف بعد از ۳ بار؛ lockهای مشغول (advisory، ردیف سفارش، سبد) → دور بعد؛ سقف batch و keyset؛ همزمانی با callback → یک اعمال.
- [x] purge رویدادهای قدیمی‌تر از نگهداری (حداکثر ساعتی).
- [x] lifespan: شروع و توقف؛ production بدون درگاه واقعی fail-closed.

## Log
- 2026-10-25: پیاده‌سازی (plan مشترک M3.5).
  - بازبینی diff (opus): PASS WITH CHANGES، بدون deadlock.
  - اعمال شد:
    - توقف دور بعد از ۳ verify بی‌پاسخ.
    - purge ساعتی.
    - تست‌های اضافه: سقف batch، سبد و ردیف سفارش مشغول، بستن request_lost پشت سفارش مشغول، توقف درگاه.
    - ثبت تصمیم‌ها در ADR-051: production بدون درگاه بالا نمی‌آید؛ `abandoned` برای هر سفارش؛ سبد خالی.
  - tx2 ∥ `request_lost` به PAY-05 منتقل شد.
  - pytest (1989)، ruff، format و mypy سبز. COMPLETE.
