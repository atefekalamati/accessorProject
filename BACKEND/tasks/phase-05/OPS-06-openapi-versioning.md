# OPS-06 — OpenAPI export & versioning

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** HANDOFF-01 · **Level:** LOW

## Objective
snapshot نسخه‌دار OpenAPI برای هر فاز و تست ناسازگاری.

## PRD reference
HANDOFF-01 (`docs/api/openapi.json`).

## Acceptance Criteria
- [ ] `scripts/export_openapi.py --snapshot NAME` و snapshot `phase-4`.
- [ ] تست: هر operation آخرین snapshot هنوز وجود دارد (حذف = شکستن frontend).

## Implementation Notes
`docs/api/versions/`.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
