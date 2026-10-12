# INV-09 — Concurrency test: no oversell

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** INV-04 · **Level:** HIGH

## Objective
تست همزمانی جامع که نشان دهد خریداران موازی، همراه با commit، release، job انقضا و اصلاح دستی، هرگز موجودی را منفی یا بیش از موجودی واقعی فروخته نمی‌کنند و دفتر movementها با شمارنده‌ها سازگار می‌ماند. فقط تست؛ بدون تغییر کد تولید (مگر باگی پیدا شود → توقف و گزارش).

## PRD reference
«موجودی و رزرو» ✓ (معیار پذیرش: «خرید همزمان چند کاربر نباید باعث منفی‌شدن موجودی شود»، «تست همزمانی برای جلوگیری از oversell»)؛ ADR-029، ADR-034، ADR-036.

## Plan (batch INV-08/INV-09/PRC-06)
- فایل جدید `tests/test_inventory_oversell.py` (integration). تست‌های جفتی موجود در `test_reservations.py` می‌مانند؛ این فایل سناریوهای چندتایی و invariantها را اضافه می‌کند.
- helper `assert_ledger_consistent(variant_ids)`: برای هر InventoryItem: `0 ≤ reserved ≤ total`؛ `reserved == Σ` آیتم‌های رزرو active؛ دفتر movement با deltaهای علامت‌دار دقیق (مستقل از ترتیب، چون `created_at` دو movement یک تراکنش ممکن است برابر باشد): `total = Σ(+increase/return, −decrease, −commit, ± (after − before) correction)` از شروع صفر برای آیتمی که با اصلاح دستی پر شده، `reserved = Σ(+reserve, −release, −commit)`؛ و هر movement با `before`/`after` خودش سازگار است. (بازبینی plan، یافته ۵)
- سناریوها (هر کدام با `asyncio.gather` روی اتصال‌های جدا، seed ثابت برای ترتیب؛ engine اختصاصی با `pool_size=25` که در پایان dispose می‌شود؛ HTTP حداکثر ۱۵ درخواست همزمان به‌خاطر pool برنامه):
  1. N=20 خریدار، هر کدام ۱ واحد، موجودی 7 → دقیقاً 7 رزرو موفق، 13 تا `INSUFFICIENT_STOCK`، free = 0.
  2. خریداران چندتنوعی با lineهای همپوشان و ترتیب‌های مختلف (3 تنوع) → بدون deadlock، all-or-nothing، invariantها.
  3. ترکیب: reserve‌ها + commit و release رزروهای قبلی + decrease و increase دستی + `sweep_expired_reservations` روی رزروهای منقضی، همه همزمان، چند دور → invariantها بعد از هر دور. یک ساعت: رزروهای «منقضی» با `now` گذشته ساخته می‌شوند و بقیه با ساعت واقعی؛ هر نتیجه معتبر پذیرفته می‌شود (EXPIRED یا committed، skip در sweep) و تعداد sweep assert نمی‌شود.
  4. HTTP: چند `PATCH /admin/inventory/{id}` همزمان (decrease) با reserve‌های همزمان → total هرگز زیر reserved نمی‌رود (به INV-08 وابسته است؛ بعد از آن).
- ریسک‌ها: تست flaky (اتصال‌های جدا، بدون sleep؛ تکرار سناریو ۱ در چند دور)؛ کندی suite (اندازه‌های کوچک، هدف < 10s برای فایل)؛ pool اتصال (حداکثر 20 تراکنش همزمان، engine با pool کافی در fixture).
- Rollback: فقط تست؛ `git revert`.

## Acceptance Criteria
- [x] خریداران موازی هرگز بیش از موجودی رزرو یا commit نمی‌کنند (تست ۱ و ۲).
- [x] ترکیب همزمان reserve/commit/release/sweep/اصلاح دستی invariantها را حفظ می‌کند (تست ۳).
- [x] اصلاح دستی HTTP همزمان با reserve oversell نمی‌کند (تست ۴).
- [x] دفتر movement با شمارنده‌ها سازگار است (helper).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- تست: `tests/test_inventory_oversell.py` (۴ تست، ~11s): ۲۰ خریدار تک‌واحدی روی موجودی ۷ (سه دور)؛ ۱۸ سبد چندتنوعی با ترتیب lock متقاطع؛ چهار دور ترکیبی reserve/commit/release/اصلاح دستی/sweep؛ PATCH ادمین همزمان با خریداران. engine اختصاصی `pool_size=25`.
- invariantها: `0 ≤ reserved ≤ total`، `reserved == Σ` آیتم‌های active، جمع deltaهای علامت‌دار دفتر = تغییر شمارنده‌ها (مستقل از ترتیب)، شکل هر movement (quantity = |delta| و فقط شمارنده درست)، commit رزرو زنده همیشه COMMITTED، `commit + decrease ≤ initial + increase`.
- بدون تغییر کد تولید؛ هیچ باگی پیدا نشد. ۵ اجرای پیاپی سبز.
- **Rollback:** فقط تست؛ `git revert`.

## Validation
```powershell
python -m pytest -q   # با TEST_DATABASE_URL
python -m ruff check .; python -m ruff format --check .; python -m mypy app tests
```

## Log
- 2026-10-12: فایل task و plan (batch INV-08/INV-09/PRC-06، AUTOPILOT).
- 2026-10-12: REVIEW-CHECKLIST (خودم): §1، §9 هدف task؛ بقیه N/A (فقط تست). بازبینی plan (subagent): APPROVE WITH CHANGES؛ یافته‌های ۵، ۷، ۸ اعمال شد (دفتر با delta به‌جای ترتیب زمانی، یک ساعت، pool اختصاصی).
- 2026-10-12: بازبینی diff (subagent): APPROVE WITH CHANGES؛ اعمال شد (commit رزرو زنده فقط COMMITTED، بررسی شکل هر movement، کد خطای 409 در PATCH، حداقل یک سبد موفق، کران commit + decrease). pytest سبز. COMPLETE.
