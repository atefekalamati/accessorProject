# SEC-02 — Security headers + request size limit

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** SEC-00 · **Level:** HIGH

## Objective
هدرهای امنیتی و سقف اندازه بدنه درخواست.

## PRD reference
«امنیت» ✓ (بعد از SEC-00).

## Acceptance Criteria
- [ ] هدرهای امنیتی روی همه پاسخ‌ها (تست).
- [ ] بدنه بزرگ‌تر از سقف → 413 با شکل خطای ثابت؛ آپلود رسانه سقف خودش را دارد.

## Implementation Notes
جزئیات بعد از تأیید SEC-00.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
