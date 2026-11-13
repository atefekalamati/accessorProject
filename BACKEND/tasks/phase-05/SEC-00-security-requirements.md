# SEC-00 — Rewrite security & acceptance requirements

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
بازنویسی بخش‌های قالبی «امنیت»، «تست و پذیرش» و «حالت‌های رابط» با الزامات دقیق و قابل تست.

## PRD reference
«امنیت»، «تست و پذیرش»، «حالت‌های رابط» (قالبی).

## Acceptance Criteria
- [x] بخش‌ها بازنویسی و ✓ شدند؛ CRUDهای قالبی حذف شدند.
- [x] ردیف PRD changes و تصمیم‌ها در DECISIONS.md.
- [x] تأیید کاربر (تغییر PRD: استثنای AUTOPILOT).

## Implementation Notes
فقط PRD و DECISIONS؛ همراه با OPS-00 در یک پیش‌نویس فرستاده می‌شود.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: بازنویسی «حالت‌های رابط»، «امنیت» و «تست و پذیرش» (همه ✓)؛ endpointهای قالبی حذف شدند؛ کاربر پیش‌نویس و پنج سؤال را بدون تغییر تأیید کرد (ADR-060). COMPLETE.
