# ACC-01 — Own orders list & detail

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ACC-00, ORD-05 · **Level:** MEDIUM

## Objective
`GET /orders` و `GET /orders/{order_number}` برای مشتری.

## PRD reference
«سفارش‌ها» ✓؛ ADR-050، ADR-053.

## Acceptance Criteria
- [x] فهرست: صفحه‌بندی، `newest`/`oldest`، فیلتر `status`، query ناشناخته → 400؛ فقط سفارش‌های خود کاربر.
- [x] جزئیات: شکل `OrderResponse` + `payments` (بدون داده درگاه) + `history` (بدون actor) + `shipment` (بعد از ADM-02؛ تا آن زمان null) + `payment_deadline`، `can_pay`، `can_cancel`.
- [x] سفارش دیگران یا ناموجود → 404؛ GET چیزی نمی‌نویسد؛ `no-store`.
- [x] تست هر حالت `can_pay`/`can_cancel`، شامل مهلت گذشته.

## Implementation Notes
`app/modules/orders/` (router، schemas، repository). تعداد query ثابت.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: پیاده‌سازی (batch 2).
  - `app/modules/orders/account.py`.
  - `order_fields`/`order_response` مشترک با `POST /orders` شد؛ address از snapshot خوانده می‌شود.
  - تصویر فهرست، تصویر فعلی محصول اولین قلم است (خطوط snapshot تصویر ندارند؛ PRD اصلاح شد).
  - `can_pay`: سفارش `pending_payment` با رزرو active و منقضی‌نشده. `can_cancel`: همان شرط، به‌علاوه payment `unpaid` یا `failed`.
  - history بدون actor برمی‌گردد؛ سه ردیف اولیه یک لحظه دارند و ترتیب نسبی‌شان ثابت نیست.
  - FRONTEND.md و openapi به‌روز شد. Level MEDIUM.
  - pytest (2033)، ruff، format و mypy سبز. COMPLETE.

