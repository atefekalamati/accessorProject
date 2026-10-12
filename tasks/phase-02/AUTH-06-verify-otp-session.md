# AUTH-06 — POST /api/v1/auth/verify-otp + Session model

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** AUTH-05, AUTH-02, ADR-012, SEC-05 · **Level:** HIGH

## Objective
تأیید OTP، ساخت یا فعال‌سازی کاربر، و صدور access token کوتاه‌عمر و refresh token.

## PRD reference
«هویت و دسترسی» ✓ (Entity Session)

## Acceptance Criteria
- [x] کد اشتباه `attempt_count` را افزایش می‌دهد. بعد از ۵ تلاش کد باطل می‌شود. کد منقضی یا مصرف‌شده → 401.
- [x] OTP **یک‌بارمصرف** است: مصرف با update اتمیک با شرط `consumed_at IS NULL` انجام می‌شود، پس دو verify همزمان فقط یکی موفق می‌شود.
- [x] کاربر جدید با نقش `customer` ساخته می‌شود و `mobile_verified_at` مقدار می‌گیرد. حساب `inactive` یا `blocked` توکن نمی‌گیرد.
- [x] جدول `sessions` با ستون‌های `user_id`، `refresh_token_hash`، `user_agent`، `ip`، `expires_at`، `revoked_at` و `family_id` ساخته شده است (migration جدید). refresh token **هش‌شده** ذخیره می‌شود.
- [x] access token یک JWT کوتاه‌عمر است. نقش و permission از claim اعتماد نمی‌شوند و در سرور از دیتابیس خوانده می‌شوند.
- [x] طبق ADR-012، access token در body برمی‌گردد. refresh token فقط در cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` تحویل داده می‌شود و در body نمی‌آید.
- [x] token service (ساخت، چرخش، ابطال) مستقل از transport است. خواندن و نوشتن cookie فقط در router انجام می‌شود.

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
### 2026-10-06 — COMPLETE (batch AUTH-06/07)
- model `UserSession` (جدول `sessions`) و migration `20261006_0004` (ستون‌های `family_id`، `refresh_token_hash` unique با CHECK، `user_agent`، `ip`، `expires_at`، `revoked_at`). `alembic check` هیچ اختلافی بین model و migration نشان نداد.
- `app/modules/auth/tokens.py`: JWT با HS256 ثابت، و refresh تصادفی که هش SHA-256 آن ذخیره می‌شود. `AuthService.verify_otp`: OTP با advisory lock و `FOR UPDATE` قفل و اتمیک مصرف می‌شود. سقف تلاش `OTP_MAX_ATTEMPTS=5` است. ساخت customer، خطای 403 برای حساب غیرفعال، مسدود یا حذف‌شده‌ی مسدود، و audit `auth.login` (ADR-017).
- settingهای جدید: `OTP_MAX_ATTEMPTS`، `ACCESS_TOKEN_TTL_SECONDS=900` و `REFRESH_TOKEN_TTL_DAYS=30`. `JWT_SECRET` از قبل fail-closed بود (الزامی و حداقل ۳۲ کاراکتر در همه محیط‌ها). تست production برای آن اضافه شد.
- تست‌ها: `tests/test_auth_tokens.py` (۱۶ مورد: رد alg دیگر، `none`، کلید دیگر، token منقضی، claim ناقص و typ غلط)، `tests/test_auth_verify_otp.py` (۱۷ مورد: ورود اول، کاربر موجود، ۵ تلاش، کد منقضی و مصرف‌شده، شماره ناشناس، ۴ verify همزمان، inactive و blocked، حذف‌شده و حذف‌شده‌ی مسدود، 400)، و ۲ مورد `JWT_SECRET` در `tests/test_settings.py`.
- یافته: داده تست‌ها (حساب حذف‌شده و حساب جدید با یک شماره) downgrade migration `0002` در session بعدی را می‌شکست. تست‌ها حالا حساب‌های خودشان را پاک می‌کنند (ADR-017، محدودیت شناخته‌شده).
- Validation: pytest 460 passed، ruff، format و mypy سبز.
