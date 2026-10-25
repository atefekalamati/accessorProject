# DSC-02 — Pure discount validation/calculation

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** DSC-01, PRC-02 · **Level:** HIGH

## Objective
تابع خالص که تصمیم می‌گیرد یک کد برای یک سبد/سفارش قابل اعمال است یا نه (و چرا)، و قواعد کد را به `CodeDiscount` ماشین‌حساب تبدیل می‌کند. مبلغ تخفیف فقط در `price_order` (ADR-031) محاسبه می‌شود.

## PRD reference
«کد تخفیف» ✓؛ D31، D33 (ADR-039)؛ ADR-031، ADR-042. تصمیم‌های کم‌اثر: ADR-043.

## Plan (batch DSC-02/DSC-03)
- `app/modules/discounts/rules.py` (بدون DB):
  - `CodeRules` (frozen dataclass از ردیف: type، value، max_amount، min_order_amount، starts_at، ends_at، usage_limit_total، usage_limit_per_user، is_active، deleted) و `rules_of(code: DiscountCode)`.
  - `Usage(total_live: int, user_live: int | None)`؛ `user_live=None` یعنی هنوز موبایل تأییدشده‌ای نیست (مهمان): سقف هر کاربر در سبد مهمان بررسی نمی‌شود و در `POST /orders` (موبایل تأییدشده) دوباره بررسی می‌شود.
  - `Rejection` (StrEnum): `invalid` (ناموجود، حذف‌شده یا غیرفعال؛ عمداً یکسان تا وجود کد غیرفعال لو نرود)، `not_started`، `expired`، `below_minimum`، `exhausted`، `user_exhausted`، `no_eligible_lines`.
  - `check_code(rules, *, at, subtotal, usage) -> Rejection | None`: ترتیب قطعی: invalid → not_started (`at < starts_at`) → expired (`at ≥ ends_at`، بازه نیمه‌باز) → exhausted (`total_live ≥ usage_limit_total`) → user_exhausted → below_minimum (`subtotal < min_order_amount`). `subtotal` = جمع خطوط قابل‌خرید بعد از تخفیف محصول، قبل از کد، مالیات و ارسال.
  - `to_code_discount(rules) -> CodeDiscount` (percent → `percent_bps` + `max_amount`؛ fixed → `fixed_amount`؛ `eligible_keys=None` چون کد روی کل سبد است، D33).
  - `discount_error(rejection) -> BusinessRuleError` با `code=DISCOUNT_NOT_APPLICABLE` (422) و `details=[{"field": "code", "type": <rejection>}]`؛ پیام بدون عدد سقف یا شمارش.
  - بعد از `price_order`: `code_applied=False` → `no_eligible_lines`.
- تست unit جدولی (`tests/test_discount_rules.py`): هر rejection، مرزهای بازه (دقیقاً `starts_at` معتبر، دقیقاً `ends_at` منقضی)، سقف دقیقاً برابر، `user_live=None`، حداقل دقیقاً برابر، ترتیب اولویت، تبدیل به `CodeDiscount` و یک تست end-to-end خالص با `price_order` (درصد با سقف، مبلغ ثابت بیشتر از جمع).
- ریسک‌ها: off-by-one در بازه و سقف (تست مرز)؛ لو رفتن وجود کد غیرفعال (یکسان‌سازی invalid)؛ گردکردن دوباره (فقط calculator گرد می‌کند)؛ سقف هر کاربر برای مهمان (صریحاً به ORD-04 منتقل).
- Rollback: `git revert`.

## Acceptance Criteria
- [x] همه rejectionها و مرزها با تست جدولی؛ ترتیب اولویت قطعی.
- [x] مبلغ فقط از `price_order`؛ تبدیل درست percent/fixed/max.
- [x] خطای 422 `DISCOUNT_NOT_APPLICABLE` با `details.type` و بدون عدد.
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- کد: `app/modules/discounts/rules.py` (`CodeRules`، `Usage`، `Rejection`، `check_code`، `to_code_discount`، `discount_error`). تست: `tests/test_discount_rules.py` (8 تابع تست).
- **Rollback:** `git revert`.

## Log
- 2026-10-18: plan (batch ۲ جلسه phase؛ بازبین opus).
- 2026-10-18: بازبینی plan (opus): APPROVE پس از اصلاح؛ اعمال شد (شروع‌نشده → invalid، مبنای حداقل با تست sale، `at` با timezone، تست سقف نامحدود و limit−1، ADR-043). بازبینی diff (opus): PASS؛ تست حداقل حالا از `price_with_code` استفاده می‌کند. pytest (1620)، ruff، format و mypy سبز. COMPLETE.
