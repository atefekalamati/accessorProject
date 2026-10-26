# ADM-06 — Audit log viewer

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** INF-05 · **Level:** MEDIUM

## Objective
`GET /admin/audit-logs` فقط برای super_admin.

## PRD reference
«گزارش ممیزی» ✓.

## Acceptance Criteria
- [x] فیلترهای actor، action (دقیق یا پیشوند)، entity، بازه؛ صفحه‌بندی؛ `created_at desc, id desc`.
- [x] admin → 403؛ هیچ endpoint نوشتنی.

## Implementation Notes
`app/modules/admin/`؛ escape پیشوند action در LIKE.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-26: پیاده‌سازی (batch 3).
  - `GET /admin/audit-logs` فقط برای super_admin (`audit:read`).
  - `action` با نقطه پایانی پیشوند حساب می‌شود (LIKE escape‌شده)؛ وگرنه تطبیق دقیق است.
  - Level MEDIUM. COMPLETE.

