# ADDR-01 — Address CRUD with ownership

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** ADDR-00, AUTH-10 · **Level:** MEDIUM

## Objective
`/addresses` برای کاربر واردشده: فهرست، جزئیات، ایجاد، ویرایش و حذف آدرس‌های خودش؛ حداکثر ۱۰ و یک پیش‌فرض.

## PRD reference
«آدرس» ✓؛ ADR-039؛ تصمیم‌های کم‌اثر: ADR-045.

## Plan (batch ADDR-01/ADDR-02)
- `app/modules/addresses/{schemas,service,router}.py`؛ جدول `addresses` از قبل وجود دارد (بدون migration).
- مالکیت با شرط `user_id` در هر query (دیگران 404)؛ advisory lock هر کاربر برای سقف ۱۰ (422) و پیش‌فرض یکتا؛ اولین آدرس پیش‌فرض؛ حذف پیش‌فرض جدیدترین را پیش‌فرض می‌کند؛ موبایل E.164 و کد پستی ۱۰ رقمی نرمال؛ فیلدهای سیستمی نادیده؛ `no-store`.
- Rollback: `git revert`.

## Acceptance Criteria
- [x] فقط آدرس‌های خود کاربر (404 برای دیگران؛ 401 بدون ورود).
- [x] یک پیش‌فرض و سقف ۱۰ حتی در همزمانی (تست).
- [x] اعتبارسنجی 400 (کد پستی، موبایل، طول‌ها، فیلد ناشناخته، null).
- [x] pytest، ruff، format و mypy سبز.

## Implementation Notes
- تست: `tests/test_addresses.py` (10 تابع تست). fixture پاک‌سازی آدرس‌ها به `make_account` وابسته است تا قبل از کاربران پاک شوند (`addresses.user_id` RESTRICT).
- **Rollback:** `git revert`.

## Log
- 2026-10-18: plan و پیاده‌سازی (batch ۴ جلسه phase؛ MEDIUM، self-review؛ بازبین opus ADDR-02 آن را هم دید: PASS، تست همزمانی پیش‌فرض اضافه شد). pytest (1705)، ruff، format و mypy سبز. COMPLETE.
