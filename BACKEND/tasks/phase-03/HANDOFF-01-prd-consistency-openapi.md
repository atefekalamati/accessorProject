# HANDOFF-01 — PRD consistency review + OpenAPI export

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** PAY-06, all Phase 1–3 `-00` · **Level:** HIGH

## Objective
مقایسه کامل PRD با API پیاده‌شده (endpointها، فیلدها، کدهای خطا و وضعیت‌ها). PRD فقط جایی اصلاح می‌شود که با ADR تأییدشده مغایرت دارد. `openapi.json` برای frontend export می‌شود و یادداشت‌های frontend نوشته می‌شوند. سپس دروازه فاز ۳ اجرا می‌شود.

## PRD reference
بخش‌های مرجع و ✓ مربوط به فاز ۱ تا ۳: «معماری سیستم»، «هویت و دسترسی»، «قیمت و مالیات»، «موجودی و رزرو»، «جزئیات محصول»، «دسته‌بندی محصولات»، «محصولات»، «سبد خرید» تا «نتیجه سفارش»، «مدیریت سفارش»، «تخفیف‌ها». بخش قالبی «انبار» فقط یک یادداشت ارجاع گرفت.

## Acceptance Criteria
- [x] PRD با API پیاده‌شده هم‌خوان است: ۴۸ اصلاح در ۱۲ بخش. اصلاح‌ها فقط جایی انجام شد که PRD با ADR مغایرت داشت. یک ردیف در جدول PRD changes ثبت شد.
- [x] `docs/api/openapi.json` با `scripts/export_openapi.py` export شد. `tests/test_api_contract.py` هم‌خوانی آن با کد را بررسی می‌کند.
- [x] یادداشت frontend در `docs/api/FRONTEND.md`:
  - cookieها و CORS
  - refresh به‌صورت single-flight بین تب‌ها (ADR-017)
  - Idempotency-Key
  - کدهای خطا
  - flagهای تغییر قیمت
  - outcomeهای پرداخت
- [x] اصلاح‌های کد:
  - CORS: `Idempotency-Key` در allow_headers و `Retry-After` در expose_headers (تست preflight).
  - `POST /orders`: query ناشناخته بدون token → 401 قبل از 400 (تست).
- [x] تصمیم redirect frontend بعد از درگاه (M3.5-PLAN) در ADR-052 ثبت شد.
- [x] تأیید کاربر برای init دوباره محافظه‌کارانه (PENDING → 409) در ADR-052 ثبت شد.
- [x] تأیید کاربر برای diffهای PRD و return-flow (2026-10-25).
- [x] افزوده کاربر: production بدون `CORS_ORIGINS` صریح در startup شکست می‌خورد (`*` ممنوع، credentials روشن). تست در `tests/test_settings.py`.
- [x] کل suite در CI سبز (run 40230753296: 2013 passed، smoke staging و secret-scan سبز).
- دروازه فاز ۳ (PR، merge توسط کاربر، tag و image `phase-3`) بعد از این task در PROGRESS.md پیگیری می‌شود (ADR-037).

## Implementation Notes
- `app/main.py` (CORS)، `app/modules/orders/router.py`، `scripts/export_openapi.py`، `tests/test_api_contract.py`، `tests/test_orders_create.py`.
- `sources/Project-AK-PRD.md`، `docs/project/DECISIONS.md` (ADR-052 و PRD changes)، `docs/api/`.
- ریسک: CORS رفتار مرورگر را تغییر می‌دهد، ولی فقط مجوز اضافه می‌کند (header مجاز و header قابل‌خواندن) و origin allowlist دست نخورده است. rollback: `git revert`. migration ندارد.

## Validation
```powershell
python scripts/export_openapi.py --check
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-10-25: پیاده‌سازی. ترتیب ۴۰۱ در `POST /orders` (یادداشت PROGRESS) اصلاح شد. bug CORS `Idempotency-Key` در همین بررسی پیدا شد.
  - بازبینی (opus، یک بار با rate limit قطع و از همان‌جا ادامه داده شد): PASS WITH CHANGES، بدون یافته high.
  - اعمال شد:
    - kind رویداد payment.
    - 503 callback در PRD و FRONTEND.
    - متن CSRF.
    - validate فقط ورود می‌خواهد و `MOBILE_NOT_VERIFIED` فقط در `POST /orders` است.
    - شکست ادغام سبد.
    - `imageMediaId` در «صفحه اصلی».
    - pin تنظیمات media در export.
    - PROGRESS.
  - pytest (2009)، ruff، format و mypy سبز. منتظر تأیید کاربر برای diffهای PRD.
- 2026-10-25: کاربر diffهای PRD و return-flow را تأیید کرد و قاعده CORS production را افزود.
  - نام setting همان `CORS_ORIGINS` موجود ماند؛ تغییر نام configهای موجود را می‌شکست.
  - COMPLETE فقط بعد از سبز شدن کل suite در CI.
  - CI اول قرمز شد: تست‌های production در `test_media_processing.py` مقدار `CORS_ORIGINS` را از `.env` محلی می‌خواندند. اصلاح شد: تنظیمات صریح و `_env_file=None` (commit `1c5876d`).
  - CI دوم سبز شد. COMPLETE.
