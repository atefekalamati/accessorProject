# ADM-02 — Order status change + shipment tracking + AuditLog

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-01 · **Level:** HIGH

## Objective
تغییر وضعیت ارسال و لغو ادمین طبق state machine، با Shipment و کد رهگیری.

## PRD reference
«مدیریت سفارش» ✓؛ ADR-047، ADR-048، ADR-053.

## Acceptance Criteria
- [ ] migration جدول `shipments` (1:1، `tracking_code`، `shipped_at`، `delivered_at`).
- [ ] `PATCH /admin/orders/{id}/shipment`: انتقال‌های ADR-047؛ `shipped` بدون کد → 400؛ `delivered` → order `completed` در همان تراکنش.
- [ ] `POST /admin/orders/{id}/cancel`: فقط پرداخت‌نشده؛ payment pending → 409؛ reason `admin`؛ آزادسازی رزرو و redemption با `OrderCancellation` موجود.
- [ ] advisory و row lock سفارش طبق ADR-048؛ history و audit؛ تست همزمانی (دو تغییر همزمان و لغو ∥ پرداخت موفق).
- [ ] بازبین opus (وضعیت سفارش، دستور کاربر).

## Implementation Notes
از `state_service` و `cancel.py` موجود استفاده شود؛ سرویس رزرو تغییر نمی‌کند (فقط release موجود صدا زده می‌شود، پس بازبین opus الزامی است).

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log

