# ADM-01 — Admin order list/detail/filter + payments list

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** ADM-00, ORD-05 · **Level:** MEDIUM

## Objective
`GET /admin/orders`، `GET /admin/orders/{id}` و `GET /admin/payments`.

## PRD reference
«مدیریت سفارش» ✓؛ D32، D38 (ADR-053).

## Acceptance Criteria
- [x] فیلترهای وضعیت‌های سه‌گانه (از جمله `refund_required`)، `q` (شماره یا موبایل)، `from`/`to`؛ صفحه‌بندی؛ موبایل ماسک‌شده در فهرست.
- [x] جزئیات: خطوط، snapshotها، آدرس، پرداخت‌ها (با `failure_reason`)، history با actor.
- [x] `/admin/payments` با فیلتر `status` و `failure_reason`، بدون `raw_event`.
- [x] مجوز `orders:read`؛ content_manager و customer → 403؛ `no-store`.

## Implementation Notes
ماژول `app/modules/orders/admin_router.py`؛ helper ماسک موبایل مشترک با ADM-03.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: پیاده‌سازی (batch 3).
  - `app/modules/orders/admin.py` و `admin_router.py`؛ helper مشترک `app/shared/search.py` (جست‌وجوی موبایل از admin users جدا شد، و `from`/`to` با timezone).
  - `q` = پیشوند شماره سفارش (بدون حساسیت به حروف) یا ۳ تا ۱۶ رقم موبایل؛ هر چیز دیگر → 400.
  - فهرست موبایل را با `mask_phone` ماسک می‌کند؛ جزئیات موبایل کامل و history با actor و reason دارد.
  - پرداخت‌ها `gateway_reference` دارند و `raw_event` ندارند.
  - مجوز `orders:read`. Level MEDIUM. COMPLETE.

