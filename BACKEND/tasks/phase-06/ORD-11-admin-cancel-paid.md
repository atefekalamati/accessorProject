# ORD-11 — Staff cancel of a paid, unshipped order

**Status:** COMPLETE · **Priority:** LOW · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** ORD-07 · **Level:** HIGH

## Objective
`POST /admin/orders/{id}/cancel` also cancels a `confirmed`, `paid` order whose shipment is `not_shipped` or `preparing`: order `cancelled` (reason `admin`), the paid payment and the order payment `refund_required` (then the existing ADM-08 full refund), committed stock back with an `InventoryMovement` `return`, and the discount redemption released, in one transaction (PRD «مدیریت سفارش» ✓, ADR-063 R2).

## PRD reference
«مدیریت سفارش» ✓ (لغو سفارش پرداخت‌شده و ارسال‌نشده)، «موجودی و رزرو» ✓، ADR-048 (lock order)، ADR-034، ADR-054، ADR-063 R2.

## Acceptance Criteria
- [x] State machine (pure, `orders/state.py`): `confirmed → cancelled` allowed only while shipment is `not_shipped|preparing` (else `already_shipped`); order payment `paid → refund_required` allowed (still only for a cancelled order); the `pending_payment + paid` guard `already_paid` stays. Shipment `shipped` and `delivered` now require order `confirmed` (`requires_order_confirmed`): a cancelled order is never shipped. Payment rows (`payments/state.py`): `paid → refund_required`.
- [x] The unpaid paths keep their rules: customer cancel and the expiry job never cancel a confirmed order — 422 `INVALID_STATE_TRANSITION` with the same `not_allowed` type as today (no API change).
- [x] Staff cancel of a paid order: same endpoint and permission (`orders:update_status`). Shipped/delivered → 422 `INVALID_STATE_TRANSITION` (`already_shipped`). Already cancelled → 200 unchanged (idempotent, no new audit).
- [x] In one transaction, lock order ADR-048 + payments: order advisory → order row → payment rows (`paid`, id order) → inventory items of the committed reservation (variant order) → redemption.
  - every `paid` payment row → `refund_required` (reason `ORDER_CANCELLED` constant of the callback, `paid_amount` kept; audit `payment.status_changed` as the callback writes it, system actor; the staff actor is on the order audit), order payment `paid → refund_required` (history);
  - the `Shipment` row (if any) and `shipment_status` stay as they are (`not_shipped`/`preparing`); only the new guard stops further moves.
  - per committed reservation line: `total_quantity += quantity` with one movement `return` (reference `('order', order id)`); the reservation row and its `commit` movements are not changed; total over `MAX_STOCK_QUANTITY` → 422 `stock_limit`, nothing written;
  - redemption `confirmed → released` (+ audit `discount.redemption_released` with `before` = the real previous status);
  - order → `cancelled` (reason `admin`, actor = staff) with history and audit `order.status_changed`.
- [x] ADM-08 then refunds the payment and moves the order payment to `refunded` (end-to-end test).
- [x] The reservation service (`inventory/reservation.py`) is not changed.
- [x] Tests; pytest, ruff, format, mypy green; OpenAPI regenerated if the summary changes.

## Implementation Notes — plan
- New `PaidOrderCancellation` in `app/modules/orders/cancel.py` (next to `OrderCancellation`); `OrderService.cancel` picks it for a staff cancel of a `confirmed` order. `OrderCancellation.check` gains an explicit `already_paid` refusal for `confirmed` orders, so the relaxed state machine cannot open the customer or expiry path.
- Stock: read the order's committed reservation lines (`InventoryReservationItem` with status `committed`), lock their `InventoryItem` rows `FOR UPDATE` ordered by `(variant_id, warehouse_id)` (same as `reservation.py`, ADR-034), add back, `record_movement(..., MovementType.RETURN, reference=("order", order.id))`. A soft-deleted variant still gets its units back (stock of a deleted variant is not sellable; this keeps the counters true).
- Payment: `move_payment(..., REFUND_REQUIRED, reason="order_cancelled", paid_amount=payment.paid_amount)`; `move_order_payment(... REFUND_REQUIRED ...)` after the order is cancelled (its guard needs `cancelled`).

**Risks**
1. Opening the customer/expiry cancel to paid orders → explicit guard + tests (customer 422, expiry job skips confirmed).
2. Double stock return (retry/concurrent cancels) → order status checked under the order lock; concurrency test → one movement set.
3. Deadlock with POST /orders, callback, expiry, admin stock adjust → same global order (order locks first, items in variant order); concurrency test against an admin stock adjust and a new order of the same variant.
4. Losing `paid_amount` on the move → passed explicitly; ADM-08 refund test uses the gateway amount.
5. Shipped order cancelled → state guard + test for shipped and delivered.

6. Reports: `successful_order()` / `paid_at_by_order` drop the cancelled order from past days' sales afterwards (consistent with today's cancel-after-refund rule; noted and tested).

**Rollback:** revert the commit (no migration). Cancels already done stay (orders refund_required, movements auditable).

**Extra tests** (`tests/test_admin_cancel_paid.py`): happy path (statuses, history, movements, counters, redemption, audits), preparing allowed, shipped/delivered 422, idempotent repeat, customer cancel of paid order still 422, expiry job leaves confirmed orders, stock_limit 422 writes nothing, concurrency (two cancels; cancel vs stock adjust vs new order), ADM-08 refund afterwards → order payment refunded, a duplicate `refund_required` payment → order `refunded` only after both, cancel in `preparing` then PATCH shipment `shipped` → 422, ORD-10 return refund after ORD-11 → 422 `order_not_paid`, sales report and dashboard `refund_required` count, 401/403.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-26: plan written, self-checked with REVIEW-CHECKLIST (§۸ money: no amount computed; refund stays ADM-08). The reservation service is only read, not changed (AUTOPILOT: no stop; opus reviewer on plan and diff).
- 2026-11-26: opus plan review: 2 blockers (shipment of a cancelled order; payment-row `paid → refund_required` missing) and should-fix items, all folded into the criteria and plan above.
- 2026-11-26: implemented (`orders/cancel_paid.py`, narrow state-machine changes, guard in `OrderCancellation.check`). Opus diff review: no blockers. Fixed: a False from `move_order_payment` now raises (never lose the refund obligation); tests added for a discount-code order (redemption `confirmed → released`, audit `before`), a duplicate refund_required payment (order `refunded` only after both ADM-08 refunds), delivered → 422 over HTTP, history rows and the dashboard count. Not testable by design: an ORD-10 return refund after ORD-11 (a return needs a delivered order, which cannot be cancelled); the expiry job only selects `pending_payment`.
- 2026-11-26: two existing tests encoded the old rule and were updated on purpose: ADM-02 staff cancel of a paid order (now: shipped → 422) and the payment-row table (`paid → refund_required` allowed).
- 2026-11-26: COMPLETE. Full suite ۲۴۲۱ green (2417 + the updated table test + the new ones run again); ruff, format, mypy green; OpenAPI regenerated (endpoint summary).
