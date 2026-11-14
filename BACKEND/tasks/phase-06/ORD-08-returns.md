# ORD-08 — Return request model + customer API

**Status:** NOT_STARTED · **Priority:** LOW · **Estimate:** 2.5h (estimate) · **Deadline:** — · **Dependencies:** ORD-07 · **Level:** HIGH

## Objective
Schema for returns (complete, so ORD-09/ORD-10 need no further migration) and the customer side: create, list, view and cancel return requests (PRD «مرجوعی» ✓, ADR-063).

## PRD reference
«مرجوعی» ✓; «سفارش‌ها» ✓; ADR-046 (Idempotency-Key), ADR-048 (lock order), ADR-063.

## Acceptance Criteria
- [ ] Migration `20261113_0034` creates `return_requests`, `return_items`, `return_status_history`; downgrade drops them; `_MODELS`, `EXPECTED_TABLES` and revision in `tests/test_database.py` updated; DB CHECKs rejected at DB level (test).
- [ ] `RETURN_WINDOW_DAYS` (int, 1..90, default 7) in `Settings` and `.env.example`.
- [ ] `POST /orders/{order_number}/returns` (Idempotency-Key): only own order (else 404, no idempotency row); `orders.shipment_status = delivered` with a shipment row whose `delivered_at` is set, and `now < delivered_at + window` (else 422); per-line quantity ≤ purchased − live requested (not `rejected`/`cancelled`) checked after the locks (else 422); 201; replay → same body; same key, other body → 422 `IDEMPOTENCY_KEY_REUSED`.
- [ ] `GET /returns` (page/limit, `status`, `sort` newest|oldest; unknown/invalid query → 400) and `GET /returns/{id}` (others' → 404).
- [ ] `POST /returns/{id}/cancel`: only `requested` → `cancelled`; already `cancelled` → 200 unchanged (no audit, no history); other states → 422 `INVALID_STATE_TRANSITION`.
- [ ] `GET /orders/{order_number}` gains `return_deadline` (null unless delivered), `can_return`, and per-line `returnable_quantity`.
- [ ] Audit `return.requested`/`return.cancelled` in the same transaction, only on change, no PII or `note` text; history per transition; all responses `Cache-Control: no-store`.
- [ ] Tests (below) green; ruff, ruff format, mypy green; OpenAPI snapshot regenerated.

## Implementation Notes — plan
**Schema** (`app/db/models/returns.py`, exported in `__init__`, added to `_MODELS`):
- `return_requests`: `id`, `order_id` FK orders RESTRICT, `user_id` FK users RESTRICT (set only from the locked `order.user_id`; ACC-05 anonymizes, never deletes), `status` String(16) CHECK in (`requested`,`approved`,`rejected`,`cancelled`,`received`,`inspected`,`refund_required`,`refunded`,`closed`), `reason` CHECK in (`defective`,`wrong_item`,`not_as_described`,`changed_mind`,`other`), `note` Text NULL (trimmed, 1..1000, CHECK), `reject_reason` Text NULL (1..1000), `decided_by` FK users SET NULL, `decided_at`, `received_at`, `inspected_at`, `refund_amount` BigInteger NULL ≥ 0, `refund_reference` String(`MAX_REFUND_REFERENCE_LENGTH` from payments) NULL unique, not blank, `refunded_at`, `refunded_by` FK users SET NULL, timestamps.
  - CHECKs, mirroring `payments` (payments.py:103-107): `refund_reference`/`refunded_at` all-NULL or all-set, and `status = 'refunded'` ⇔ reference set (`refunded_by` may be NULL only through SET NULL); `status = 'rejected'` ⇒ `reject_reason` NOT NULL; `decided_at` set ⇔ status not in (`requested`,`cancelled`); `received_at` set ⇒ status in (`received`,`inspected`,`refund_required`,`refunded`,`closed`); `inspected_at` set ⇔ status in (`inspected`,`refund_required`,`refunded`,`closed`).
  - Indexes `(user_id, created_at)`, `(order_id)`, `(status, created_at)`.
- `return_items`: `id`, `return_request_id` FK CASCADE, `order_item_id` FK order_items RESTRICT, `quantity` BETWEEN 1 AND `MAX_STOCK_QUANTITY`, `accepted_quantity` NULL CHECK 0..`quantity`, `condition` NULL CHECK in (`sellable`,`damaged`), `refundable` Boolean NULL, `refund_amount` BigInteger NULL ≥ 0, `inspection_note` Text NULL, `inventory_movement_id` FK inventory_movements RESTRICT NULL (the restock trace; ORD-09); CHECKs: `condition`, `accepted_quantity` and `refundable` all-NULL (not inspected) or all-set; `refundable IS NOT TRUE ⇒ COALESCE(refund_amount,0) = 0`; `inventory_movement_id` only when `condition = 'sellable'`. UNIQUE (`return_request_id`, `order_item_id`), UNIQUE `inventory_movement_id`; index `order_item_id`.
- `return_status_history`: `id`, `return_request_id` FK CASCADE, `old_status` NULL, `new_status` (both valid-status CHECK), CHECK `old_status IS NULL OR old_status <> new_status`, `actor_user_id` FK users SET NULL, `created_at`; index `(return_request_id, created_at)`.
- Not soft-deletable; requests are never deleted.

**Module** `app/modules/returns/` (`router.py`, `service.py`, `repository.py`, `schemas.py`, `state.py`), mounted in `app/api/v1/router.py`.
- Body: `{items: [{order_item_id, quantity}] (1..50, unique ids → 400), reason, note?}`, `extra="forbid"`, strict int quantity. Any client amount/status field → 400. `note` is plain text: trimmed, control characters except newline → 400, blank → 400; stored as is (JSON output, no HTML rendering here).
- Customer response whitelist: `id`, `order_number`, `status`, `reason`, `note`, `reject_reason` (only when `rejected`, deliberate clarification, recorded in DECISIONS), items (`order_item_id`, `product_title`, `variant_label`, `quantity`, `accepted_quantity`, `refund_amount`), request `refund_amount`, timestamps, history (`status`, `created_at`). Never: actor ids, `refund_reference`, `inspection_note`, `condition`, `inventory_movement_id`.
- **Create transaction** (ADR-048): authentication (401) → query/headers (400) → idempotency key lock (scope `returns.create`; hash of `order_number` + body with items sorted by `order_item_id`) → ownership pre-check (404, no row stored) → order advisory lock → order row `FOR UPDATE` with `user_id` → shipment row read → live requested sum per `order_item_id` **after** the locks → insert request, items, history (`None → requested`), audit, idempotency complete. Errors: `item_not_in_order`, `quantity_exceeds_returnable` (details per item), `order_not_delivered` (also when the shipment row is missing or `delivered_at` is NULL; never `updated_at`), `return_window_closed`: all 422. 4xx never stores the key.
- **Cancel**: ownership check, then the return row `FOR UPDATE` only. Safe: create never locks return rows, so there is no cycle, and cancel only frees quantity. **Global order for ORD-09/10 (documented in `state.py`):** order advisory → order row → return row → inventory → …. Staff transitions that touch inventory or money must not copy cancel's shorter path.
- `state.py`: pure transition table (unit-tested), reused by ORD-09/10.
- `can_return` = delivered, `now < deadline`, and some line has `returnable_quantity > 0`. Deadline = `delivered_at + RETURN_WINDOW_DAYS` (exclusive). Changing the setting moves existing deadlines (accepted; recorded).
- Note for ACC-05: `ACCOUNT_HAS_ACTIVE_ORDERS` also counts returns in `requested`..`refund_required` (PRD «پروفایل» ✓ already says «مرجوعی باز»). ACC-05 updates the user row only; this path takes FK KEY SHARE on `users`, which does not conflict with a non-key UPDATE.
- PRD fix in the same commit: «مرجوعی» ✓ lists `IDEMPOTENCY_KEY_REUSED` under 409; the code and `POST /orders` use 422 (errors.py:95) → move it to 422.

**Risks**
1. Concurrent requests over-claim a line → order advisory + row lock, cap computed after the locks; concurrency test.
2. Deadlock with callback/expiry/cancel → same lock order (advisory → order row); concurrency test with a callback replay.
3. IDOR → ownership in the query; 404 for others' orders and requests.
4. Migration → new tables only; downgrade drops only them.
5. Leaking staff data → whitelist schema plus a test asserting the hidden fields are absent.

**Rollback**: revert the commit; `alembic downgrade -1` (dev/test only; production is not deployed) drops the three empty tables. No existing table or row changes.

**Extra tests** (`tests/test_returns.py`, integration; 403/429 N/A for customer endpoints):
- Concurrency:
  - two creates over-claiming → one 201, one 422
  - same key ×3 → one row
  - cancel vs cancel → one history row and one audit
  - create vs cancel of an earlier request
  - create vs payment-callback replay on the same order → no deadlock
- Idempotency:
  - replay → identical body
  - other body → 422
  - after a 422, the same key with a fixed body → 201
  - replay after the window closes or after cancel → original 201 body
  - item order in the body does not change the hash
- Window and delivery:
  - just before the deadline → 201; at the deadline → 422
  - not delivered → 422
  - `shipment_status = delivered` with no shipment row or NULL `delivered_at` → 422
- Validation (all 400):
  - `items` 0 or 51
  - quantity 0, negative, bool, float or string
  - duplicate item id
  - invalid or blank `reason`
  - `note` over 1000 characters, whitespace-only, or with control characters
  - extra field (`refund_amount`, `status`)
  - missing Idempotency-Key
  - unknown query, `limit` over the cap, invalid `sort` or `status`
  - malformed `order_number`
- Quantity rules:
  - item of another order → 422
  - quantity freed by a cancelled request → 201
- Auth and ownership:
  - 401 on all four endpoints, before the Idempotency-Key 400
  - another user's order → 404 with no idempotency row
  - another user's request (get or cancel) → 404
- Cancel:
  - `requested` → `cancelled`
  - cancel twice → 200, one history row
  - approved (set in the DB) → 422
- Output and records:
  - hidden fields are absent from the response
  - audit and history rows are written; no `note` text in the audit
  - no-store header on every response
  - `can_return` false in each case: not delivered, window over, all quantity claimed
  - `returnable_quantity` per line
- Migration: up/down; DB CHECKs reject bad rows.
- Unit: state table and deadline helper.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: plan نوشته شد. self-check با REVIEW-CHECKLIST: §۴ (فایل) N/A، §۵ (SD) N/A، §۸ پول فقط ستون است و محاسبه در ORD-10. بازبین مستقل (sonnet): APPROVE WITH CHANGES با ۳ major و ۸ minor؛ همه در plan اعمال شد:
  - `accepted_quantity` و `inventory_movement_id`
  - CHECKهای کامل
  - whitelist پاسخ و `reject_reason`
  - رفع 409→422 در PRD
  - مسیر delivered بدون ردیف
  - ترتیب lock برای ORD-09/10
  - تست‌های بیشتر

  منتظر تأیید کاربر.
