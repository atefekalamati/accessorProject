# AUTH-06 — POST /api/v1/auth/verify-otp + Session model

**Status:** NOT_STARTED · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** AUTH-05, AUTH-02, ADR-012

## Objective
تأیید OTP، ساخت یا فعال‌سازی کاربر، و صدور access token کوتاه‌عمر و refresh token.

## PRD reference
«هویت و دسترسی» ✓ (Entity Session)

## Acceptance Criteria
- [ ] کد اشتباه `attempt_count` را افزایش می‌دهد. بعد از ۵ تلاش کد باطل می‌شود. کد منقضی یا مصرف‌شده → 401.
- [ ] OTP **یک‌بارمصرف** است: مصرف با update اتمیک با شرط `consumed_at IS NULL` انجام می‌شود، پس دو verify همزمان فقط یکی موفق می‌شود.
- [ ] کاربر جدید با نقش `customer` ساخته می‌شود و `mobile_verified_at` مقدار می‌گیرد. حساب `inactive` یا `blocked` توکن نمی‌گیرد.
- [ ] جدول `sessions` با ستون‌های `user_id`، `refresh_token_hash`، `user_agent`، `ip`، `expires_at`، `revoked_at` و `family_id` ساخته شده است (migration جدید). refresh token **هش‌شده** ذخیره می‌شود.
- [ ] access token یک JWT کوتاه‌عمر است. نقش و permission از claim اعتماد نمی‌شوند و در سرور از دیتابیس خوانده می‌شوند.
- [ ] طبق ADR-012، access token در body برمی‌گردد. refresh token فقط در cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` تحویل داده می‌شود و در body نمی‌آید.
- [ ] token service (ساخت، چرخش، ابطال) مستقل از transport است. خواندن و نوشتن cookie فقط در router انجام می‌شود.

## Implementation Notes
`app/modules/auth/`، `app/db/models/auth.py`، `alembic/versions/`، `app/core/config.py` (TTL توکن‌ها)، `.env.example`.

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
