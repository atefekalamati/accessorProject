# CART-04 — Guest → user cart merge on login

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** CART-01, AUTH-06 · **Level:** MEDIUM

## Objective
در `POST /auth/verify-otp`، سبد مهمان (cookie `cart_token`) در سبد کاربر ادغام شود و cookie پاک شود (D30).

## PRD reference
«سبد خرید» ✓ و «ورود یا خرید مهمان» ✓؛ D30 (ADR-039)؛ ADR-040، ADR-041.

## Plan
- `app/modules/cart/merge.py` (`CartMerger.merge`): تراکنش جدا بعد از ورود؛ lock سبد کاربر → سبد مهمان؛ قواعد ادغام در ADR-040؛ نتیجه `MergeResult` و log `cart.merged`.
- `IssuedTokens.user_id`؛ `verify_otp` cookie را می‌خواند، ادغام می‌کند و `clear_cart_cookie`؛ شکست ادغام log و ورود موفق.
- ریسک‌ها: خراب‌شدن ورود (try/except + تست)؛ ادغام دوبار (status merged + lock؛ تست همزمانی)؛ کاهش سبد کاربر (تست)؛ سقف خطوط (تست).
- Rollback: بدون schema؛ `git revert`.

## Acceptance Criteria
- [x] ادغام قطعی: جمع تا سقف موجودی آزاد، هرگز کاهش، حذف variant غیرقابل‌فروش یا بی‌موجودی، سقف ۵۰ خط (تست).
- [x] idempotent و امن در همزمانی (تست gather).
- [x] cookie مهمان بعد از ادغام پاک می‌شود؛ cookie بد یا ناشناخته ورود را خراب نمی‌کند؛ بدون cookie بدون Set-Cookie (تست).
- [x] شکست ادغام ورود را خراب نمی‌کند و cookie می‌ماند (تست).
- [x] مبنای قیمت خط منتقل‌شده همان قیمتی است که مهمان دیده بود (تست flag بعد از ورود).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- تست: `tests/test_cart_merge.py` (۹ تست). باگ پیدا و رفع‌شده: log بعد از commit به ویژگی منقضی `user_cart.id` دسترسی داشت (با session پیش‌فرض MissingGreenlet).
- **Rollback:** `git revert`.

## Log
- 2026-10-12: plan و پیاده‌سازی (batch ۴ جلسه phase). REVIEW-CHECKLIST (خودم؛ MEDIUM، بدون بازبین subagent اجباری): §1 (lock مرتب، تست همزمانی)، §2 (هویت از login)، §3 (cookie فقط با الگوی token)، §7 (cookie پاک با همان ویژگی‌ها) پاس؛ بقیه N/A. pytest (1522)، ruff، format و mypy سبز. COMPLETE.
