# INV-02 — InventoryMovement + manual stock adjustment

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** INV-01, INF-05 · **Level:** HIGH

## Objective
جدول `inventory_movements` و سرویس داخلی اصلاح دستی موجودی (increase، decrease، correction) با دلیل اجباری، row lock، movement و AuditLog. endpoint آن در INV-08 است. رزرو، commit و release (INV-04..06) از همین helper movement استفاده می‌کنند.

## PRD reference
«موجودی و رزرو» ✓ (InventoryMovement، «تغییر دستی موجودی باید دلیل و AuditLog داشته باشد»)؛ ADR-005، ADR-029. تصمیم‌های کم‌اثر: ADR-034.

## Plan (batch INV-02/PRC-03)
- مدل `InventoryMovement`: `inventory_item_id` (FK RESTRICT)، `movement_type` (CHECK: increase، decrease، reserve، release، commit، correction، return)، `quantity` (> 0، مقدار تغییر)، `total_before/after` و `reserved_before/after` (CHECK بازه ۰..MAX و `reserved ≤ total`)، `reference_type`/`reference_id` (nullable)، `reason` (nullable، ≤ 500)، `created_by` (FK users، SET NULL)، `created_at`. index روی `(inventory_item_id, created_at)`. migration `20261011_0014`؛ ثبت در `__init__`، `_MODELS`، `EXPECTED_TABLES` و revision تست.
- `app/modules/inventory/service.py`: `InventoryService.adjust(actor_id, variant_id, type, quantity, reason)`. variant ناموجود یا حذف‌شده → 404. InventoryItem انبار پیش‌فرض با `INSERT … ON CONFLICT DO NOTHING` و سپس `SELECT … FOR UPDATE` (ایجاد همزمان امن). increase: `total + q ≤ MAX` وگرنه 422. decrease: `total − q ≥ reserved` وگرنه 409 `INSUFFICIENT_STOCK`. correction: total مطلق = q (`0..MAX`)، باید `≥ reserved` (409)؛ correction بدون تغییر → no-op بدون movement و audit. `reason` بعد از trim اجباری (۱..۵۰۰).
- helper `record_movement(session, item, type, quantity, before, after, …)` برای INV-04..06.
- هر تغییر: movement + audit `inventory.adjusted` (before/after total و reserved، type، reason) در همان تراکنش.
- ریسک‌ها: lost update در دو اصلاح همزمان (FOR UPDATE؛ تست gather)؛ ایجاد همزمان InventoryItem (ON CONFLICT؛ تست)؛ total کمتر از reserved (بررسی زیر lock + CHECK backstop)؛ نوع پولی/عددی نادرست (int strict در API بعدی؛ اینجا `_int` guard).
- Rollback: `alembic downgrade -1` فقط جدول جدید را حذف می‌کند (داده movement از دست می‌رود؛ فقط dev)؛ `git revert`.

## Acceptance Criteria
- [x] هر اصلاح یک movement با before/after و یک audit در همان تراکنش دارد؛ no-op هیچ‌کدام را ندارد.
- [x] decrease یا correction زیر reserved → 409؛ بیش از MAX → 422؛ variant ناموجود/حذف‌شده → 404؛ دلیل خالی یا مقدار نامعتبر → خطای validation.
- [x] دو اصلاح همزمان سریال می‌شوند (تست)؛ ایجاد همزمان آیتم یک ردیف می‌سازد (تست).
- [x] migration upgrade/downgrade و تست schema.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/db/models/inventory.py` (`InventoryMovement`، `MovementType`، CHECKهای سازگاری هر نوع، مرجع اجباری برای رزرو و دلیل اجباری برای اصلاح دستی)، migration `20261011_0014`، `app/modules/inventory/repository.py` (variant `FOR SHARE`، ایجاد آیتم با ON CONFLICT و `FOR UPDATE`)، `app/modules/inventory/service.py` (`record_movement`، `InventoryService.adjust`).
- تست: `tests/test_inventory_adjust.py` (۱۸ تست شامل همزمانی و backstopهای DB)؛ teardownهای `conftest` و `test_admin_products` movementها را اول حذف می‌کنند.
- **Rollback:** `alembic downgrade -1` (فقط dev؛ movementها حذف می‌شوند)؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-11: plan (batch INV-02/PRC-03، AUTOPILOT؛ milestoneهای فاز ۲ تأییدشده).
- 2026-10-11: REVIEW-CHECKLIST (خودم): §1، §3، §5، §6، §9 پاس؛ §2 (endpoint در INV-08)، §4، §7، §8 N/A. بازبینی plan: APPROVE WITH CHANGES (quantity = |تغییر|، CHECKهای سازگاری، variant `FOR SHARE`؛ اعمال شد). بازبینی diff: APPROVE WITH CHANGES (ترتیب movement در تست، audit no-op، guard نوع reason، یادداشت ایجاد آیتم، cleanup؛ اعمال شد). pytest (1287)، ruff، format و mypy سبز. COMPLETE.
