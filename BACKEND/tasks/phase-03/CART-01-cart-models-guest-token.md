# CART-01 — Cart & CartItem models + secure guest cart token

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 4h (estimate) · **Deadline:** — · **Dependencies:** CART-00, CAT-03 · **Level:** MEDIUM

## Objective
جدول‌های `carts` و `cart_items`، token امن سبد مهمان (فقط hash ذخیره می‌شود) و helper cookie؛ پایه CART-02..04.

## PRD reference
«سبد خرید» ✓ و «ورود یا خرید مهمان» ✓؛ D30 (ADR-039)؛ تصمیم‌های کم‌اثر: ADR-040.

## Plan (batch CART-01/CART-02)
- `app/db/models/cart.py`: Cart (`user_id` یا `token_hash`، دقیقاً یکی؛ status active/merged/expired؛ `expires_at` فقط برای مهمان؛ partial unique یک سبد active برای هر کاربر؛ CHECK hex برای hash). CartItem (FK مرکب variant+product مثل inventory_items، qty 1..MAX، unique cart+variant، CASCADE از cart).
- migration `20261012_0017`؛ ثبت در `__init__`، `_MODELS`، `EXPECTED_TABLES` و HEAD_REVISION؛ teardown fixture کاتالوگ cart_items را اول حذف می‌کند.
- `app/modules/cart/tokens.py`: `token_urlsafe(32)`، SHA-256، parse سخت‌گیر cookie، set/clear با `HttpOnly; Secure; SameSite=Lax; Path=/api/v1`، 30 روز.
- `app/modules/cart/repository.py`: `lock_user_cart` (ON CONFLICT روی partial unique + FOR UPDATE)، `find_guest_cart` (فقط active و منقضی‌نشده)، `create_guest_cart`، خطوط به ترتیب id (ADR-031).
- ریسک‌ها: ایجاد همزمان سبد کاربر (تست gather)؛ ذخیره token خام (CHECK hex)؛ حذف variant با خط سبد (FK RESTRICT؛ حذف نرم است).
- Rollback: `alembic downgrade -1` (فقط dev)؛ `git revert`.

## Acceptance Criteria
- [x] قیدهای schema (یک مالک، hash hex، انقضای مهمان، status، qty، FK مرکب، unique) و یک سبد active برای هر کاربر (تست).
- [x] ایجاد همزمان سبد کاربر یک ردیف می‌سازد (تست).
- [x] token تصادفی، فقط hash ذخیره، cookie با ویژگی‌های D30 (تست).
- [x] migration و تست schema/drift؛ pytest، ruff، format و mypy سبز.

## Implementation Notes
- تست: `tests/test_cart_models.py` (۱۸ تست).
- **Rollback:** `alembic downgrade -1`؛ `git revert`.

## Log
- 2026-10-12: plan (milestone M3.1، batch ۳ جلسه phase). REVIEW-CHECKLIST: N/A برای MEDIUM. pytest (1477)، ruff، format و mypy سبز. COMPLETE.
