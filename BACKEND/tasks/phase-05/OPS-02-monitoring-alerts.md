# OPS-02 — Monitoring & alerts

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** OPS-01 · **Level:** MEDIUM

## Objective
تعریف هشدارها روی متریک‌ها.

## PRD reference
«پایش و رخدادها» ✓ (بعد از OPS-00).

## Acceptance Criteria
- [ ] هشدارها با آستانه و runbook کوتاه تعریف شدند.

## Implementation Notes
جزئیات بعد از تأیید OPS-00.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
