# ADDR-04 — Address & shipping tests

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** ADDR-01…03 · **Level:** MEDIUM

## Objective
پرکردن خلأهای تست مالکیت و validation آدرس و روش ارسال (بیشتر مسیرها در ADDR-01..03 پوشش دارند).

## Plan (batch ADDR-03/ADDR-04)
- آدرس (`tests/test_addresses.py`): PATCH با `user_id` کاربر دیگر نادیده گرفته می‌شود (200، مالک بدون تغییر: آدرس برای مالک دیده می‌شود و برای دیگری 404)؛ admin و super_admin آدرس مشتری را نمی‌بینند (404، بدون استثنای نقش)؛ شناسه ناموجود در GET/PATCH/DELETE → 404؛ 422 سقف بدون همزمانی (پیام و `details`).
- روش ارسال (`tests/test_admin_shipping.py`): end-to-end — ادمین می‌سازد → در فهرست عمومی؛ غیرفعال/حذف → از فهرست عمومی خارج و `get_selectable` → 422؛ تغییر `cost` در فهرست عمومی دیده می‌شود.
- بدون تغییر کد برنامه (اگر باگی پیدا شد: توقف یا رفع در همین batch اگر داخل plan باشد).

## Acceptance Criteria
- [x] تست مالکیت و validation آدرس و روش ارسال کامل.
- [x] pytest، ruff، format و mypy سبز.

## Log
- 2026-10-18: plan (batch ۱ جلسه phase).
- 2026-10-18: ۴ تست آدرس (`tests/test_addresses.py`: مالک جعلی در PATCH، بی‌دسترسی نقش‌های staff، 404 شناسه ناموجود، 422 سقف) و تست end-to-end اثر ادمین بر فهرست عمومی و `get_selectable` (`tests/test_admin_shipping.py`). بدون تغییر کد برنامه. pytest (1740)، ruff، format و mypy سبز. M3.3 کامل شد. COMPLETE.
