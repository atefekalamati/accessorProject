# ADM-02 — Order status change + shipment tracking + AuditLog

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-01 · **Level:** HIGH

## Objective
تغییر وضعیت ارسال و لغو ادمین طبق state machine، با Shipment و کد رهگیری.

## PRD reference
«مدیریت سفارش» ✓؛ ADR-047، ADR-048، ADR-053.

## Acceptance Criteria
- [x] migration جدول `shipments` (1:1، `tracking_code`، `shipped_at`، `delivered_at`).
- [x] `PATCH /admin/orders/{id}/shipment`: انتقال‌های ADR-047؛ `shipped` بدون کد → 400؛ `delivered` → order `completed` در همان تراکنش.
- [x] `POST /admin/orders/{id}/cancel`: فقط پرداخت‌نشده؛ payment pending → 409؛ reason `admin`؛ آزادسازی رزرو و redemption با `OrderCancellation` موجود.
- [x] advisory و row lock سفارش طبق ADR-048؛ history و audit؛ تست همزمانی (دو تغییر همزمان و لغو ∥ پرداخت موفق).
- [x] بازبین opus (وضعیت سفارش، دستور کاربر).

## Implementation Notes
از `state_service` و `cancel.py` موجود استفاده شود؛ سرویس رزرو تغییر نمی‌کند (فقط release موجود صدا زده می‌شود، پس بازبین opus الزامی است).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: پیاده‌سازی (batch 4). plan: [M4.2-BATCH4-PLAN.md](../../docs/project/M4.2-BATCH4-PLAN.md).
  - migration `20261026_0026` (shipments، 1:1).
  - `PATCH /admin/orders/{id}/shipment`: advisory → ردیف سفارش → transition؛ `delivered` → order `completed` در همان تراکنش؛ audit `shipment.updated`.
  - `POST /admin/orders/{id}/cancel`: همان `OrderService.cancel` با `requested_reason=admin`.
  - shipment در جزئیات مشتری و ادمین آمد.
  - بازبینی plan (opus): APPROVE WITH CHANGES، اعمال شد.
  - بازبینی diff (opus): PASS WITH CHANGES. همه ۶ یافته اعمال شد:
    - تست رقابت لغو ادمین ∥ پرداخت موفق دیرهنگام (۵ اجرای پشت هم سبز)
    - الگوی کاراکتر چاپی برای کد رهگیری (NUL و newline → 400)
    - assertionهای قوی‌تر در تست همزمانی
    - `status` در audit `shipment.updated`
    - انتقال `shipment_of` به `orders/shipments.py`
    - `RuntimeError` وقتی ردیف shipment وجود ندارد
  - بازبینی دوم (opus) بعد از یک rate limit: PASS.
  - backlog: اصلاح کد رهگیری بعد از shipped.
  - pytest (2050)، ruff، format و mypy سبز. COMPLETE.

