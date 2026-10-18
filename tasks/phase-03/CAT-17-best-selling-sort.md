# CAT-17 — `best_selling` sort for product listing

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 1h (estimate) · **Deadline:** — · **Dependencies:** CAT-07, ORD-01 · **Level:** MEDIUM

## Objective
sort `best_selling` در لیست عمومی محصولات بر اساس تعداد فروش موفق.

## Plan (batch ORD-03/ORD-05/CAT-17)
- `ProductSort.BEST_SELLING` در `app/modules/catalog/product_query.py`: زیرپرسش همبسته `coalesce(sum(order_items.quantity), 0)` از سفارش‌های `payment_status = 'paid'` (سفارش refund_required/لغو شمرده نمی‌شود)، نزولی؛ tie با `id` (tie_breaker موجود `paginate`). index `ix_order_items_product_id` موجود است. allowlist با `resolve_sort` (کلید ناشناخته 400).
- تست `tests/test_products_list.py`: ترتیب با فروش paid، نادیده گرفتن unpaid/refund_required، tie با id، بدون N+1.

## Acceptance Criteria
- [x] sort allowlisted؛ ties by `id`.
- [x] pytest، ruff، format و mypy سبز.

## Log
- 2026-10-18: plan (batch ۳ جلسه phase).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES؛ اعمال شد: «فروش موفق» یک تعریف واحد (`payment_status = 'paid'`؛ helper در `app/modules/orders/sales.py`؛ ADR-047)؛ LEFT JOIN به یک زیرپرسش تجمیعی به‌جای زیرپرسش همبسته؛ tie با id (معیار پذیرش).
- 2026-10-18: `ProductSort.BEST_SELLING` با LEFT JOIN به `units_sold_by_product()` (`app/modules/orders/sales.py`)؛ تست ترتیب paid، نادیده گرفتن unpaid/failed/refund_required، tie با id و صفحه‌بندی بدون تکرار. Level MEDIUM: self-review. pytest (1846)، ruff، format و mypy سبز. COMPLETE.
