# PRC-05 — Pricing settings (super_admin only)

**Status:** NOT_STARTED · **Priority:** MEDIUM · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** PRC-01, AUTH-10 · **Level:** HIGH

## Objective
`GET` و `PATCH /admin/pricing/settings` برای مالیات و گردکردن، فقط با `pricing_settings:update` (در v1 فقط super_admin، D2).

## PRD reference
«قیمت و مالیات» ✓ (APIها، PricingSetting، دسترسی)؛ ADR-004، ADR-014، ADR-027، ADR-031. تصمیم‌های کم‌اثر: ADR-033.

## Plan (batch PRC-04/PRC-05/INV-07)
- ماژول `app/modules/pricing/`: `schemas.py`، `repository.py`، `service.py`، `dependencies.py`، `router.py`؛ ثبت در `app/api/v1/router.py`.
- هر دو endpoint با `require_permission("pricing_settings:update")` (اول 401/403، بعد validation).
- PATCH: `tax_enabled` (StrictBool)، `default_tax_rate_bps` (StrictInt، `0..MAX_TAX_RATE_BPS`)، `rounding_mode` (`RoundingMode`)، `rounding_step` (StrictInt، `1..MAX_ROUNDING_STEP`). فیلدهای سیستمی (`id`، `currency`، `version`، `updated_by`، `updated_at`، `singleton`) حذف و نادیده گرفته می‌شوند؛ کلید ناشناخته، null، float یا بدنه خالی → 400.
- سرویس: ردیف singleton با `FOR UPDATE`؛ نبود ردیف → 404. بدون تغییر → 200 بدون audit و بدون bump. با تغییر: `version += 1`، `updated_by`، audit `pricing.settings_updated` (before/after فیلدهای تغییرکرده) در همان تراکنش. `Cache-Control: no-store`.
- ریسک‌ها: lost update در دو PATCH همزمان (row lock؛ تست gather: version دو واحد بالا می‌رود)؛ نقش غیرمجاز (تست 403 برای admin، content_manager، customer)؛ float یا مقدار خارج از بازه (Strict + CHECK backstop)؛ تغییر بدون bump نسخه (fingerprint ADR-027 قیمت تغییرکرده را تشخیص نمی‌دهد؛ تست).
- Rollback: بدون migration؛ `git revert`. اگر تنظیمات اشتباه ذخیره شد، با PATCH برمی‌گردد (audit دارد).

## Acceptance Criteria
- [ ] 401 بدون token، 403 برای هر نقش بدون `pricing_settings:update`، روی GET و PATCH.
- [ ] 400 برای کلید ناشناخته، null، float، bool رشته‌ای، بازه نامعتبر و بدنه خالی؛ فیلد سیستمی نادیده گرفته می‌شود.
- [ ] تغییر → `version` +1، `updated_by`، audit با before/after؛ بدون تغییر → بدون audit و bump.
- [ ] دو PATCH همزمان سریال می‌شوند (تست).
- [ ] نبود ردیف → 404 (تست).
- [ ] pytest، ruff، format و mypy سبز.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-11: plan (batch PRC-04/PRC-05/INV-07).
