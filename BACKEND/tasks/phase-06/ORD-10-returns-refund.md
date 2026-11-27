# ORD-10 — Return refund amount and manual refund record

**Status:** COMPLETE · **Priority:** LOW · **Estimate:** 1.5h (estimate) · **Deadline:** — · **Dependencies:** ORD-09 · **Level:** HIGH

## Objective
Inspection computes each line's refund on the server from the order snapshot and moves the request to `refund_required` (amount > 0) or `closed`. Staff with `payments:refund` record the manual refund (`refunded`). The sales report shows return refunds separately (PRD «مرجوعی» ✓, ADR-063 R1).

## PRD reference
«مرجوعی» ✓ (مبلغ بازپرداخت، ثبت بازپرداخت، دسترسی)؛ ADR-001 (Toman integer)، ADR-054 (manual refund)، ADR-063 R1.

## Acceptance Criteria
- [x] Pure `line_refund(final_line_total, purchased, quantity)` in `returns/state.py`: `floor(final_line_total × quantity ÷ purchased)`; `quantity == purchased` → exactly `final_line_total`; 0 → 0; invalid input → `ValueError`. Unit tests (rounding, full line, several requests on one line sum ≤ `final_line_total`).
- [x] Inspect (same transaction as ORD-09): per item `refund_amount = line_refund(..., accepted_quantity if refundable else 0)`, request `refund_amount` = sum; then `inspected → refund_required` (sum > 0) or `→ closed` (sum 0), both in history. Audit `return.inspected` lists per-line refund and the total. Shipping is never refunded.
- [x] `POST /admin/returns/{id}/refund` `{refund_reference, note?}` (`payments:refund`; `extra="forbid"`, so a client `amount` → 400): only from `refund_required` → `refunded` with `refund_reference`, `refunded_at`, `refunded_by`. Same reference again on a refunded request → 200, nothing written. Another reference → 409 `already_refunded`. Reference used on another return or on a payment → 409 `refund_reference_taken` (concurrent duplicate caught by the unique index via savepoint). Other status → 422 `INVALID_STATE_TRANSITION`. Order payment status unchanged. Audit `return.refunded`.
- [x] Customer view shows `refund_amount` and `refunded_at`, never the reference (already in ORD-08 schema; tested).
- [x] Sales report `GET /admin/reports/sales`: new `return_refunds {count, amount}` for requests refunded in the range (Tehran days, by `refunded_at`); `totals` unchanged.
- [x] Role matrix, SEC-03 registry, OpenAPI regenerated; pytest, ruff, format, mypy green.

## Implementation Notes — plan
- Lock order as ORD-09 (`AdminReturnService.lock`): order advisory → order row → return row. Refund locks nothing else (no stock, no payment row).
- `RecordReturnRefundRequest` reuses `RefundReference` and the note shape of ADM-08 (`orders/admin_schemas.py`).
- Report: one extra aggregate query in `ReportRepository` over `return_requests` with `status = 'refunded'` and `refunded_at` in `[_midnight(start), _midnight(end))`.

**Risks**
1. Wrong money (float, rounding twice) → integer-only pure function, one floor per line; tests at the boundaries (1 of 3, 2 of 3, 3 of 3, total 0, total not divisible).
2. Over-refund over several requests → quantity cap from ORD-08 + floor ⇒ Σ ≤ total; property-style unit test over all splits of a small quantity.
3. Double refund record → status check under the return row lock; unique `refund_reference`; concurrency test (two references at once → one 200, one 409).
4. Changing payment/order payment status by mistake → test that both stay `paid`.

**Rollback:** revert the commit (no migration). Recorded refunds stay as rows (auditable).

**Extra tests** (`tests/test_returns_admin.py`): inspect → refund_required with exact amounts, → closed when nothing refundable; refund happy path, idempotent repeat, 409 other reference, 409 taken (return and payment), 422 from inspected/closed, 400 amount field, 403 for support, 404; concurrency; report figures.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-20: plan written, self-checked with REVIEW-CHECKLIST (§۸ money: integer toman, server-side, one rounding per line; §۴ N/A). Decision: the literal PRD formula per request (Σ over several partial requests can be up to a few toman below `final_line_total`; recorded in DECISIONS).
- 2026-11-26: implemented. Opus review of the diff: no blockers. Fixed: ADM-08 now also refuses a reference used on a return (both directions); tests for one reference on two returns at once (unique-index path), across payments and returns, and the 99-of-100 under-refund; nit: return refund only while the order is still `paid` (422 `order_not_paid`). Bug found by tests: `begin_nested()` flushes on entry, so status and every refund field are set before it (CHECK `refund_record_complete`).
- 2026-11-26: user accepted the decisions (formula per request, `amount` → 400, separate `return_refunds`). Requests left in `inspected` by ORD-09 alone would have no amount; none exist outside test databases (nothing deployed from this branch).
- 2026-11-26: COMPLETE. Full suite ۲۴۰۹ green; ruff, format, mypy green; OpenAPI regenerated (additions only).
