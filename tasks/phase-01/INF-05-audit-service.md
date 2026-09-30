# INF-05 — AuditLog writer service

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** FND-04 · **Level:** MEDIUM

## Objective
یک تابع واحد برای ثبت رخداد حساس در **همان تراکنش** عملیات.

## PRD reference
«هویت و دسترسی» ✓، «قیمت و مالیات» ✓، «موجودی و رزرو» ✓

## Acceptance Criteria
- [x] `record_audit(session, *, actor_id, action, entity_type, entity_id, before, after, request)` پیاده‌سازی شده است.
- [x] `request_id`، IP و diff در `metadata` (JSONB) ذخیره می‌شوند. **پیشنهاد:** بدون migration، چون جدول ستون `request_id` ندارد.
- [x] فیلدهای حساس (token، hash، کد OTP) قبل از ذخیره حذف می‌شوند.
- [x] نام action از قرارداد `<entity>.<verb>` پیروی می‌کند (مثلاً `product.price_changed`).
- [x] rollback عملیات، رکورد audit را هم rollback می‌کند (تست integration).

## Implementation Notes
`app/shared/audit.py` و `tests/test_audit.py` (هر دو فایل جدید و برنامه‌ریزی‌شده). مدل `app/db/models/audit.py` از قبل موجود است.

**پیاده‌سازی‌شده:**
- `record_audit` فقط `add` و `flush` می‌کند و commit نمی‌کند (همان تراکنش caller).
- `metadata = {actor, request_id, diff}`. `actor` برابر `"system"` است اگر `actor_id` خالی باشد، وگرنه `"user"`. diff فقط فیلدهای تغییرکرده را دارد؛ در create یا delete طرف غایب `None` است.
- UUID، datetime، Decimal و Enum به JSON تبدیل می‌شوند؛ نوع ناشناخته → `TypeError`.
- کل metadata با `app.core.redaction.redact` پاک می‌شود؛ `"hash"` به `SENSITIVE_KEY_PARTS` مشترک اضافه شد (روی logها هم اثر دارد) و موبایل در diff mask می‌شود.
- IP از `request.client.host`؛ مقدار غیر IP → `None`. IP واقعی پشت proxy به OPS-04 (trusted-proxy) موکول شد.
- action نامعتبر (`<entity>.<verb>` با حروف کوچک) → `ValueError` (خطای برنامه‌نویس).
- fixtureهای دیتابیس (`database_url`، `migrated_database`، `db_engine`، `db_session`) از `tests/test_database.py` به `tests/conftest.py` منتقل شدند.
- append-only در سطح DB (بلاک UPDATE) → task جدید SEC-04.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
- 2026-09-29: از `tasks/M1-05-audit-service.md` منتقل شد.
- 2026-09-29: COMPLETE. pytest 345 passed و 0 skipped (postgres-test)؛ ruff، format و mypy سبز.
