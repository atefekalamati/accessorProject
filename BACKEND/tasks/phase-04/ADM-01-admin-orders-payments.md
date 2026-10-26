# ADM-01 — Admin order list/detail/filter + payments list

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-00, ORD-05 · **Level:** MEDIUM

## Objective
`GET /admin/orders`، `GET /admin/orders/{id}` و `GET /admin/payments`.

## PRD reference
«مدیریت سفارش» ✓؛ D32، D38 (ADR-053).

## Acceptance Criteria
- [ ] فیلترهای وضعیت‌های سه‌گانه (از جمله `refund_required`)، `q` (شماره یا موبایل)، `from`/`to`؛ صفحه‌بندی؛ موبایل ماسک‌شده در فهرست.
- [ ] جزئیات: خطوط، snapshotها، آدرس، پرداخت‌ها (با `failure_reason`)، history با actor.
- [ ] `/admin/payments` با فیلتر `status` و `failure_reason`، بدون `raw_event`.
- [ ] مجوز `orders:read`؛ content_manager و customer → 403؛ `no-store`.

## Implementation Notes
ماژول `app/modules/orders/admin_router.py`؛ helper ماسک موبایل مشترک با ADM-03.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log

