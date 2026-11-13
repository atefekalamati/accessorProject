# SEC-01 — Global rate limiting

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** SEC-00 · **Level:** HIGH

## Objective
سقف درخواست سراسری برای endpointهای عمومی و حساس طبق SEC-00.

## PRD reference
«امنیت» ✓ (بعد از SEC-00).

## Acceptance Criteria
- [x] سقف‌ها طبق PRD؛ عبور از سقف → 429 `RATE_LIMITED` با `Retry-After`.
- [x] پشت proxy به OPS-04 نیاز دارد (DEFERRED)؛ تا آن موقع قابل تنظیم.
- [x] تست سقف و همزمانی.

## Implementation Notes
جزئیات بعد از تأیید SEC-00.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-13: سقف سراسری درخواست در حافظه پروسه: ۳۰۰ در دقیقه برای هر IP روی /api/v1 (IPv6 به‌ازای /64؛ OPTIONS، health و ready معاف) و ۶۰۰ برای هر ادمین با token معتبر؛ 429 RATE_LIMITED با Retry-After، request_id، CORS و هدرهای امنیتی؛ کلیدها محدود (LRU)؛ قابل تنظیم؛ بازبین مستقل plan و diff را تأیید کرد؛ ریسک IP مشترک پشت proxy در ADR-060 و OPS-04 ثبت شد. COMPLETE.
