# CART-05 — Cart tests

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CART-02…04 · **Level:** MEDIUM

## Objective
suite تجمیعی سبد مثل CAT-12: نقشه پوشش خطا برای هر endpoint سبد × 400/401/403/404/409/422 با guard، تست شکاف‌ها و یک تست end-to-end مهمان → ورود → سبد کاربر.

## PRD reference
«سبد خرید» ✓، «ورود یا خرید مهمان» ✓؛ ADR-039..041.

## Plan (batch CART-05/DSC-01)
- `tests/test_cart_api.py`: `COVERAGE` برای ۵ route سبد؛ guard تطابق با routeهای واقعی و وجود هر تست نام‌برده. شکاف‌ها: 401/403 برای PATCH و DELETE خط، 400 برای id خراب در DELETE. end-to-end: مهمان دو خط اضافه می‌کند، قیمت تغییر می‌کند، ورود ادغام می‌کند، flag با قیمت قبلی دیده می‌شود، acknowledge پاکش می‌کند.
- Rollback: فقط تست؛ `git revert`.

## Acceptance Criteria
- [x] هر endpoint سبد برای هر وضعیت تست یا توضیح `n/a` دارد؛ guard سبز.
- [x] مالکیت 404 (به تست‌های CART-02 نگاشت شده) و 401/403 برای همه نوشتن‌ها.
- [x] تست end-to-end سبد.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- تست: `tests/test_cart_api.py` (۹ تست).
- **Rollback:** `git revert`.

## Log
- 2026-10-18: plan و پیاده‌سازی (batch ۱ جلسه phase؛ MEDIUM، self-review). pytest (1573)، ruff، format و mypy سبز. COMPLETE.
