# DSC-05 — Concurrent usage-cap test (with the internal redeem service)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** DSC-03 · **Level:** HIGH

## Objective
سرویس داخلی redemption که ORD-04 و PAY-03/04 صدا می‌زنند (`redeem`، `confirm`، `release`)، و تست همزمانی که نشان دهد سقف کل و سقف هر کاربر هرگز رد نمی‌شود (D31). مثل رزرو (INV-04) که قبل از سفارش ساخته شد: endpoint عمومی ندارد.

## PRD reference
«کد تخفیف» ✓؛ D31، D32، D34 (ADR-039)؛ ADR-042، ADR-043. تصمیم‌های کم‌اثر: ADR-044.

## Plan (batch DSC-04/DSC-05)
- `app/modules/discounts/redemption.py` (`RedemptionService`؛ همه در تراکنش فراخواننده، بدون commit، مثل `ReservationService`):
  - `redeem(*, code_id, order_id, user_id, phone, amount, subtotal, now)`: `SELECT … FOR UPDATE` ردیف DiscountCode → بررسی دوباره زیر lock با `check_code` (حذف‌شده/غیرفعال/بازه/سقف کل/سقف موبایل/حداقل) → درج redemption `pending` با snapshot `code` و `amount`. رد → `discount_error` (422). سفارشی که redemption زنده دارد → همان را برمی‌گرداند اگر کد یکسان باشد (idempotent)، وگرنه 409 `CONFLICT`.
  - `confirm(order_id, now)`: pending → confirmed؛ confirmed → no-op؛ released → 409 `CONFLICT`.
  - `release(order_id, now)`: pending یا confirmed → released؛ released یا نبود → no-op. ترتیب lock: ردیف کد → ردیف redemption.
- **اصلاحات بازبینی plan (opus؛ جایگزین بندهای بالا):** `confirm`/`release` هرگز raise نمی‌کنند و outcome برمی‌گردانند (`CONFIRMED`، `ALREADY_CONFIRMED`، `RELEASED`، `NONE` / `RELEASED`، `ALREADY_RELEASED`، `NONE`)؛ PAY-03 وقتی commit رزرو EXPIRED است `release` صدا می‌زند نه `confirm` (D32). `confirm`/`release` فقط ردیف redemption را قفل می‌کنند (release فقط شمارش را کم می‌کند؛ بدون چرخه با job انقضا). ترتیب سراسری lock: سبد → advisory سفارش → variant/inventory → ردیف کد → redemption. `redeem` قواعدی را که با آن قیمت‌گذاری شده (`priced_rules`) می‌گیرد و اگر قواعد قفل‌شده فرق کنند 409 `PRICE_CHANGED`؛ ORD-04 می‌تواند با `lock_code` اول قفل کند. هر سفارش حداکثر یک redemption (حتی released) → retry با همان کد، مبلغ و موبایل همان را برمی‌گرداند، وگرنه 409. ورودی‌ها: amount و subtotal int در بازه، amount ≤ subtotal، موبایل E.164؛ ORD-04 وقتی `code_applied=false` است redeem نمی‌کند. `released_at ≥ confirmed_at`.
- تست‌ها (`tests/test_discount_redemption.py`): ۱۰ سفارش همزمان روی کدی با `usage_limit_total=3` → دقیقاً ۳ موفق؛ همزمان با یک موبایل و `usage_limit_per_user=1` → دقیقاً ۱؛ redemption آزادشده جا باز می‌کند؛ redeem تکراری idempotent؛ انتقال‌های confirm/release؛ کد حذف‌شده یا غیرفعال → `invalid`؛ همزمانی redeem با حذف کد → هرگز redemption بعد از حذف.
- ریسک‌ها: oversubscription (FOR UPDATE + شمارش زیر lock؛ تست gather)؛ deadlock (یک ردیف کد در هر redeem؛ ترتیب ثابت)؛ pool تست (engine با pool کافی مثل INV-09).
- Rollback: بدون schema؛ `git revert`.

## Acceptance Criteria
- [x] سقف کل و سقف هر موبایل زیر همزمانی هرگز رد نمی‌شوند (تست).
- [x] redeem/confirm/release با انتقال‌های معتبر و idempotent (تست)؛ قفل ردیف کد قبل از شمارش.
- [x] تعامل با حذف یا غیرفعال‌سازی همزمان کد (تست).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/discounts/redemption.py` (`RedemptionService.lock_code/redeem/confirm/release`، `ConfirmOutcome`، `ReleaseOutcome`). کدی که بعد از قیمت‌گذاری غیرفعال یا حذف شود در `redeem` 409 `PRICE_CHANGED` (`code_changed`) می‌دهد نه 422؛ عمدی است: فراخواننده دوباره قیمت‌گذاری می‌کند و آن‌جا 422 `invalid` می‌گیرد (ADR-044). redeem همزمانِ یک سفارش با دو کد بدون advisory lock سفارش به 409 می‌رسد (savepoint روی unique زنده)، نه 500. تست: `tests/test_discount_redemption.py` (12 تابع تست).
- **Rollback:** بدون schema؛ `git revert`.

## Log
- 2026-10-18: plan (batch ۳ جلسه phase؛ بازبین opus).
- 2026-10-18: بازبینی plan (opus): نیازمند تغییر؛ همه must اعمال شد (outcome به‌جای raise، قفل فقط redemption در confirm/release و ترتیب سراسری lock، `priced_rules` و 409 PRICE_CHANGED، یک redemption برای هر سفارش، بررسی ورودی، `released_at ≥ confirmed_at`). بازبینی diff (opus): PASS با should؛ اعمال شد (409 به‌جای IntegrityError برای redeem همزمان یک سفارش، user_id در replay، تست قطعی صف‌شدن پشت غیرفعال‌سازی، تست ترتیبی آزادسازی جا، تست clamp زمان آزادسازی، مبلغ بیش از سقف). اجرای کامل suite یک بار ۲ ساعت و ۴۱ دقیقه طول کشید با ۱۲ شکست timeout/deadlock در تست‌های نامرتبط؛ علت: اجرای همزمان pytest بازبین‌ها روی همان دیتابیس پایه تست؛ اجرای تنها: ۱۶۵۹ سبز در 2:48. pytest (1659)، ruff، format و mypy سبز. COMPLETE.
