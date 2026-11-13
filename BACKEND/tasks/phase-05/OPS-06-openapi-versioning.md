# OPS-06 — OpenAPI export & versioning

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** HANDOFF-01 · **Level:** LOW

## Objective
snapshot نسخه‌دار OpenAPI برای هر فاز و تست ناسازگاری.

## PRD reference
HANDOFF-01 (`docs/api/openapi.json`).

## Acceptance Criteria
- [x] `scripts/export_openapi.py --snapshot NAME` و snapshot `phase-4`.
- [x] تست: هر operation آخرین snapshot هنوز وجود دارد (حذف = شکستن frontend).

## Implementation Notes
`docs/api/versions/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: نسخه‌بندی OpenAPI: export_openapi.py --snapshot phase-N، snapshot ثابت docs/api/versions/openapi-phase-4.json (همان فایل tag phase-4)، تست CI که حذف هر operation آخرین snapshot را رد می‌کند، دستور snapshot در دروازه فاز (.claude/commands/phase.md) و یادداشت FRONTEND.md. COMPLETE.
