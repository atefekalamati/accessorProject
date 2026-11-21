# ORD-09 — Admin return review, receipt and inspection; restock only sellable

**Status:** COMPLETE · **Priority:** LOW · **Estimate:** 2.5h (estimate) · **Deadline:** — · **Dependencies:** ORD-08 · **Level:** HIGH

## Objective
Staff side of returns up to inspection: list and view requests, approve or reject, mark received, and inspect each line. Stock goes back only for `sellable` units, once, in the inspect transaction (PRD «مرجوعی» ✓, «موجودی و رزرو» ✓, ADR-063).

## PRD reference
«مرجوعی» ✓; «موجودی و رزرو» ✓ («مرجوعی فقط پس از تأیید سلامت کالا موجودی را افزایش می‌دهد»); ADR-034 (stock lock order), ADR-048, ADR-063.

## Acceptance Criteria
- [x] Permission `returns:manage` (support, admin, super_admin) in `seed.py`; role-matrix test updated.
- [x] `GET /admin/returns` (page/limit, `status`, `sort` newest|oldest; unknown query → 400) and `GET /admin/returns/{id}` (full: `admin_note`, inspection fields, decided/refunded actor ids, history with actor; no customer phone). `Cache-Control: no-store`.
- [x] `POST /admin/returns/{id}/approve` `{admin_note?}`, `/reject` `{reject_reason, admin_note?}`, `/receive` `{admin_note?}`: transitions via `state.check_transition` (else 422 `INVALID_STATE_TRANSITION`); repeating the same transition on a request already in the target state → 200 unchanged (idempotent, no audit/history).
- [x] `POST /admin/returns/{id}/inspect` `{items: [{order_item_id, condition, accepted_quantity, refundable?, note?}], admin_note?}` only from `received`: every line of the request exactly once (else 400); `accepted_quantity` 0..line quantity; `sellable` ⇒ `refundable` true (sending false → 400), `damaged` ⇒ `refundable` required; status → `inspected`, `inspected_at`.
- [x] Restock: for each `sellable` line with `accepted_quantity > 0`, one `InventoryMovement` `return` (+accepted, `reference = ('return', request id)`) on the default warehouse item, stored in `return_items.inventory_movement_id`. Variant soft-deleted → no movement, recorded in the audit as `restock_skipped` (decision in DECISIONS). Total would exceed `MAX_STOCK_QUANTITY` → 422 `stock_limit`, nothing written.
- [x] Audit `return.approved|rejected|received|inspected` in the same transaction (inspected: per line condition, accepted, restocked quantity; no notes, no PII).
- [x] Tests (below); pytest, ruff, ruff format, mypy green; OpenAPI regenerated; SEC-03 registries (admin write audit, ids) updated.

## Implementation Notes — plan
- Module `app/modules/returns/admin_router.py`, `admin_service.py`, `admin_schemas.py`; router mounted under `/admin`.
- **Lock order** (state.py, ADR-048 + ADR-034): order advisory → order row `FOR UPDATE` → return row `FOR UPDATE` → (inspect only) sellable variants `FOR SHARE` sorted by id → their default-warehouse inventory items `FOR UPDATE` ordered by `variant_id` — the same variant/item order as reservation flows, so no cycle with `POST /orders`, expiry or admin stock adjustment. Ownership is not a concern (staff), existence → 404.
- Customer cancel (return row only) vs approve/reject: both read status under the return row lock; one wins, the other gets 422 (or 200 when it is the same target).
- Restock item: existing default item locked; if missing (should not happen: the sale committed from it) it is created like a manual increase (`lock_default_item`).
- The refund amount and `inspected → refund_required | closed` are ORD-10 (it extends inspect in the same transaction); after ORD-09 alone a request rests in `inspected`.
- `reject_reason` 1..1000 trimmed plain text (customer-facing); `admin_note` 1..2000; inspection `note` → `inspection_note` 1..2000; all `extra="forbid"`.

**Risks**
1. Double restock (retry, concurrent inspect) → status check under the return row lock; unique `inventory_movement_id`; concurrency test → one movement.
2. Deadlock with reservation/expiry/admin stock → same global order; concurrency tests against `POST /orders` on the same variant and against admin stock adjustment.
3. Restock of a deleted variant → skipped and audited, never errors (inspection must be recordable).
4. Over-accepting → `accepted_quantity ≤ quantity` in schema and DB CHECK.
5. Permission leak → `returns:manage` on every admin route; 401/403 tests; support can act (PRD).

**Rollback**: revert the commit (no migration; the seed adds one permission row, harmless if left, removable by re-seed). Stock already returned stays as movements (auditable; correct with an admin `correction`).

**Extra tests** (`tests/test_returns_admin.py`):
- each transition happy path + history/audit; invalid transitions 422; same-target repeat 200 without audit
- inspect validation 400s (missing/duplicate/foreign line, accepted > quantity, sellable+refundable false, damaged without refundable, notes blank/too long, extra fields)
- restock: sellable → total +accepted, movement linked, reserved unchanged; damaged → no movement; accepted 0 → no movement; deleted variant → skipped + audit
- concurrency: two inspects → one movement; approve vs customer cancel → one wins; inspect vs `POST /orders` for the same variant and vs admin stock adjust → both finish
- 401/403 (customer, content_manager) on every route; 404 unknown id; list filters/sort/400; detail shows admin fields
- stock_limit 422 leaves nothing written

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: plan نوشته شد و self-check با REVIEW-CHECKLIST انجام شد. §۴ (فایل) N/A است. در §۸ پول ندارد، چون مبلغ در ORD-10 است. بازبین opus روی plan اجرا می‌شود.
- 2026-11-20: پیاده‌سازی شد: `admin_router.py` (شش route با `returns:manage`، no-store)، service و schemaها، seed و ماتریس نقش‌ها، registry audit در SEC-03، و openapi.json بازتولید شد. رفع باگ: approve، `decided_at` را قبل از flush وضعیت می‌نویسد (CHECK `decided_when_decided`).
- 2026-11-20: بازبین opus روی diff اجرا شد. blocker نداشت. یافته‌ها رفع شدند: (۱) هر قلم restock‌شده movement جدای خودش را دارد، حتی وقتی دو قلم variant یکسان دارند. (۲) تست دو قلم با variant یکسان اضافه شد. (۳) تصمیم‌ها در DECISIONS ثبت شدند. (۴) قفل item یکی‌یکی و به ترتیب variant گرفته می‌شود (`lock_default_item`). (۵) تست reject تکراری با دلیل متفاوت اضافه شد. (۶) inspect روی وضعیت غلط با بدنه خراب 422 برمی‌گرداند (پذیرفته شد).
- 2026-11-20: COMPLETE. ۱۴ تست در `tests/test_returns_admin.py`؛ ruff، format و mypy سبز؛ نتیجه suite کامل در commit.
