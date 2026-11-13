# OPS-01 — Metrics + error-tracking adapter

**Status:** COMPLETE · **Priority:** MEDIUM · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** OPS-00 · **Level:** MEDIUM

## Objective
endpoint متریک و adapter ردیابی خطا پشت interface.

## PRD reference
«پایش و رخدادها» ✓ (بعد از OPS-00).

## Acceptance Criteria
- [x] endpoint متریک محافظت‌شده.
- [x] adapter خطا با پیاده‌سازی log-only برای dev و test.

## Implementation Notes
جزئیات بعد از تأیید OPS-00.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: GET /metrics با فرمت Prometheus و بدون dependency جدید، محافظت با METRICS_TOKEN (بدون token یا با token نادرست 404، بیرون از OpenAPI)؛ شمار و مدت درخواست به تفکیک الگوی route (بدون id یا PII)، شمار 429، نتیجه callback پرداخت، زمان آخرین موفقیت job تطبیق و sweep، database_up و payments_refund_required_open؛ ErrorReporter با پیاده‌سازی log-only که هر 500 را یک بار با request_id و نوع خطا (بدون متن) می‌گیرد و خرابی خودش 500 را تغییر نمی‌دهد. COMPLETE.
