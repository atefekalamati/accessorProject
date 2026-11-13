# OPS-01 — Metrics + error-tracking adapter

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** OPS-00 · **Level:** MEDIUM

## Objective
endpoint متریک و adapter ردیابی خطا پشت interface.

## PRD reference
«پایش و رخدادها» ✓ (بعد از OPS-00).

## Acceptance Criteria
- [ ] endpoint متریک محافظت‌شده.
- [ ] adapter خطا با پیاده‌سازی log-only برای dev و test.

## Implementation Notes
جزئیات بعد از تأیید OPS-00.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
