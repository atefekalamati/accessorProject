# SEC-02 — Security headers + request size limit

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** SEC-00 · **Level:** HIGH

## Objective
هدرهای امنیتی و سقف اندازه بدنه درخواست.

## PRD reference
«امنیت» ✓ (بعد از SEC-00).

## Acceptance Criteria
- [x] هدرهای امنیتی روی همه پاسخ‌ها (تست).
- [x] بدنه بزرگ‌تر از سقف → 413 با شکل خطای ثابت؛ آپلود رسانه سقف خودش را دارد.

## Implementation Notes
جزئیات بعد از تأیید SEC-00.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: هدرهای امنیتی روی همه پاسخ‌ها (HSTS فقط production، CSP جدا برای /docs خارج از production)، سقف بدنه ۱MB با 413 PAYLOAD_TOO_LARGE (Content-Length قبل از خواندن، chunked هنگام رسیدن؛ multipart دو برابر سقف آپلود تا ترتیب CAT-05 حفظ شود)، /docs و /redoc و /openapi.json در production خاموش؛ ترتیب middleware تا 413 هم request_id و CORS دارد؛ بازبین مستقل plan و diff را تأیید کرد (یافته‌های minor رفع شد). COMPLETE.
