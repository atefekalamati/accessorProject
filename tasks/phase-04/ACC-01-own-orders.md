# ACC-01 — Own orders list & detail

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ACC-00, ORD-05 · **Level:** MEDIUM

## Objective
`GET /orders` و `GET /orders/{order_number}` برای مشتری.

## PRD reference
«سفارش‌ها» ✓؛ ADR-050، ADR-053.

## Acceptance Criteria
- [ ] فهرست: صفحه‌بندی، `newest`/`oldest`، فیلتر `status`، query ناشناخته → 400؛ فقط سفارش‌های خود کاربر.
- [ ] جزئیات: شکل `OrderResponse` + `payments` (بدون داده درگاه) + `history` (بدون actor) + `shipment` (بعد از ADM-02؛ تا آن زمان null) + `payment_deadline`، `can_pay`، `can_cancel`.
- [ ] سفارش دیگران یا ناموجود → 404؛ GET چیزی نمی‌نویسد؛ `no-store`.
- [ ] تست هر حالت `can_pay`/`can_cancel`، شامل مهلت گذشته.

## Implementation Notes
`app/modules/orders/` (router، schemas، repository). تعداد query ثابت.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log

