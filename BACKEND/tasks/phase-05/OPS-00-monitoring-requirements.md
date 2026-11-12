# OPS-00 — Rewrite monitoring & incidents requirements

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 1h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
بازنویسی بخش قالبی «پایش و رخدادها».

## PRD reference
«پایش و رخدادها» (قالبی).

## Acceptance Criteria
- [ ] بخش بازنویسی و ✓ شد.
- [ ] ردیف PRD changes.
- [ ] تأیید کاربر.

## Implementation Notes
همراه با SEC-00 در یک پیش‌نویس.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
