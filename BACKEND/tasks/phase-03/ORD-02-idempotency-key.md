# ORD-02 — Idempotency-Key infrastructure

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** INF-01 · **Level:** HIGH

## Objective
زیرساخت عمومی `Idempotency-Key` برای `POST /orders` (ORD-04) و بعداً پرداخت: هر کاربر، مهلت ۲۴ ساعت؛ همان کلید + همان بدنه → پاسخ اولیه؛ بدنه متفاوت → 422 (D34).

## PRD reference
«نتیجه سفارش» ✓ (Idempotency-Key، مدل IdempotencyKey)؛ ADR-039 (D34-5)؛ M3.4-PLAN.

## Plan (batch ORD-01/ORD-02)
- مدل `IdempotencyKey` (`app/db/models/idempotency.py`، CreatedAt): `user_id` FK users CASCADE، `scope` (مثل `orders.create`، ≤۶۴)، `key` (≤۲۵۵)، `request_hash` (sha256 hex، CHECK ۶۴ hex)، `response_status` (200..299)، `response_body` JSONB، `expires_at`؛ unique `(user_id, scope, key)`؛ index `expires_at`. migration جدا `20261018_0023` (migration commit‌شده ORD-01 ویرایش نمی‌شود).
- `app/shared/idempotency.py`:
  - `parse_idempotency_key(header)` dependency: نبود یا خالی → 400 `VALIDATION_ERROR` (`field: header.Idempotency-Key`)؛ فقط ASCII قابل چاپ `[\x21-\x7e]`، طول ۱..۲۵۵.
  - `request_hash(body)` خالص: sha256 روی JSON canonical (`sort_keys`، `separators=(",", ":")`، `ensure_ascii=False`) از بدنه parse‌شده (بعد از validation، بدون فیلدهای سیستمی).
  - `IdempotencyService(session)` در تراکنش فراخواننده: `begin(user_id, scope, key, hash, now)` → `pg_advisory_xact_lock` روی hash پایدار `(user, scope, key)` (اول از همه، قبل از lockهای ORD-04)، سپس خواندن ردیف: معتبر + hash برابر → `Replay(status, body)`؛ معتبر + hash متفاوت → 422 `IDEMPOTENCY_KEY_REUSED`؛ منقضی → حذف و `Fresh`؛ نبود → `Fresh`. `complete(user_id, scope, key, hash, status, body, now)` ردیف را با `expires_at = now + 24h` درج می‌کند (در همان تراکنش ثمربخش؛ rollback → بدون ردیف، retry اجرای تازه).
  - فقط پاسخ موفق ذخیره می‌شود؛ خطاها (409 `PRICE_CHANGED`، 409 موجودی) ذخیره نمی‌شوند تا retry بعد از اصلاح ممکن باشد (تصمیم کم‌اثر؛ ADR-046).
  - `purge_expired(session, now, limit)` برای پاک‌سازی (اتصال به job در صورت نیاز بعداً؛ فعلاً فقط تابع + تست).
- تست‌ها `tests/test_idempotency.py`: unit hash (ترتیب کلید، یونیکد)، parse header (نبود، خالی، فاصله، غیر ASCII، ۲۵۶ کاراکتر → 400)؛ integration با router آزمایشی (الگوی `test_auth_permissions`): همان کلید/بدنه → همان پاسخ و یک اثر جانبی؛ بدنه متفاوت → 422؛ کاربر دیگر با همان کلید مستقل؛ منقضی → اجرای تازه؛ خطای handler → ردیف ذخیره نمی‌شود؛ `asyncio.gather` دو درخواست همزمان → یک اجرا و دو پاسخ یکسان.
- **ریسک‌ها:** (۱) اجرای دوباره در همزمانی → advisory lock + تست gather؛ (۲) نشت پاسخ بین کاربران → کلید per-user + تست؛ (۳) hash ناپایدار → canonical JSON + unit test؛ (۴) کلید مسموم با پاسخ خطا → فقط موفق ذخیره می‌شود؛ (۵) PII در پاسخ ذخیره‌شده → فقط پاسخی که خود کاربر دیده، با CASCADE حذف کاربر و انقضای ۲۴ ساعته.
- **اصلاحات بازبینی plan (opus):** کلید advisory `hashtextextended('idem:<scope>:<user>:<key>', 0)` (قرارداد repo؛ برخورد hash فقط انتظار اضافه است، نه خطای درستی). ترتیب سراسری lock در ADR-044 و docstring `redemption.py`: idempotency → سبد → advisory سفارش → inventory → کد → redemption. `request_hash` پارامترهای مسیر را هم می‌پوشاند (`{"path": ..., "body": ...}`). پاسخ replay هم `Cache-Control: no-store` دارد (PII). purge بعداً به job sweep وصل می‌شود (ADR-046).
- **Rollback:** `alembic downgrade -1` (همراه ORD-01)؛ `git revert`.

## Acceptance Criteria
- [x] per-user keys، 24h TTL؛ same key + same body → original response؛ different body → 422 (D34).
- [x] همزمانی → یک اجرا (تست).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/shared/idempotency.py` (`idempotency_key`، `request_hash`، `IdempotencyService`، `replay_response`، `NO_STORE`، `purge_expired_idempotency_keys`)، `app/db/models/idempotency.py`، migration `20261018_0023`، کد خطای `IDEMPOTENCY_KEY_REUSED` (422). تست: `tests/test_idempotency.py` (20 تست).
- **Rollback:** `alembic downgrade -1`؛ `git revert`.

## Log
- 2026-10-18: plan (batch ۲ جلسه phase؛ بازبین opus).
- 2026-10-18: بازبینی plan (opus): APPROVE WITH CHANGES؛ اعمال شد (کلید lock، ترتیب lock، hash مسیر، no-store در replay).
- 2026-10-18: بازبینی diff (opus): PASS WITH CHANGES؛ اعمال شد (guard بدنه JSON در `complete`، `NO_STORE` مشترک، یادداشت ترتیب dependency، `limit` مثبت در purge، ثبت محدودیت replay و purge در ADR-046). رد شد: حذف index `created_at` (الگوی mixin). pytest (1819)، ruff، format و mypy سبز. COMPLETE.
