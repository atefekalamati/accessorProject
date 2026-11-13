# SEC-04 — DB-level append-only audit_logs

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** INF-05 · **Level:** HIGH

## Objective
UPDATE و TRUNCATE روی `audit_logs` در سطح دیتابیس رد شوند (DELETE از FND-04).

## PRD reference
CLAUDE.md §۸ (حذف audit با trigger ممنوع)، «گزارش ممیزی» ✓.

## Acceptance Criteria
- [ ] migration جدید: trigger برای UPDATE (به‌جز SET NULL ستون `actor_user_id` با حذف کاربر) و TRUNCATE؛ همه `ENABLE ALWAYS`.
- [ ] تست integration: UPDATE، DELETE و TRUNCATE رد می‌شوند (SQLSTATE 23000)؛ حذف کاربر سالم می‌ماند.
- [ ] downgrade فقط triggerها را برمی‌دارد.

## Implementation Notes
migration `0033`. ریسک باقی‌مانده: نقش مالک جدول می‌تواند trigger را بردارد؛ تفکیک نقش‌ها در OPS-04.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
