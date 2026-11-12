# Tasks

فایل‌ها در `tasks/phase-0N/<ID>-<short-slug>.md` قرار دارند. فهرست کامل همه taskها (با یا بدون فایل) در `docs/project/PLAN.md` است.

- **پیشوندها:** FND · INF · AUTH · CAT · INV · PRC · CART · DSC · ADDR · ORD · PAY · ACC · ADM · CNT · SEC · OPS · DEC (task تصمیم؛ `DEC-NN` هم‌شماره `DNN` است).
- **وضعیت‌ها:** `NOT_STARTED` · `IN_PROGRESS` · `BLOCKED` (منتظر تصمیم باز) · `COMPLETE` · `CANCELLED` (با ذکر دلیل؛ هرگز حذف نمی‌شود) · `DEFERRED` (کاربر به بعد موکول کرد؛ ADR-058).

## قالب

```markdown
# <ID> — <Title>

**Status:** … · **Priority:** HIGH|MEDIUM|LOW · **Estimate:** Nh (estimate) · **Deadline:** … · **Dependencies:** … · **Level:** LOW|MEDIUM|HIGH

## Objective
## PRD reference
## Acceptance Criteria      (checkbox؛ قوانین حیاتی مرتبط از CLAUDE.md)
## Implementation Notes     (فقط مسیرهای موجود یا صریحاً برنامه‌ریزی‌شده)
## Validation               (دستورات دقیق از CLAUDE.md)
## Log                      (یادداشت‌های تاریخ‌دار)
```

## قواعد

- فایل task فقط برای milestone جاری و بعدی ساخته می‌شود. بقیه تا شروع milestone فقط یک ردیف در PLAN.md هستند.
- هر milestone که به بخش **قالبی** PRD تکیه دارد، با task `<PREFIX>-00` شروع می‌شود. این task:
  1. بخش قالبی PRD همان ماژول را در `sources/Project-AK-PRD.md` بازنویسی می‌کند.
  2. به عنوان آن بخش «✓ بازبینی‌شده» اضافه می‌کند.
  3. یک ردیف به جدول «PRD changes» در `docs/project/DECISIONS.md` اضافه می‌کند.
  4. به تأیید کاربر نیاز دارد. بعد از آن taskهای پیاده‌سازی شروع می‌شوند.
- `COMPLETE` فقط وقتی است که همه معیارهای پذیرش تیک خورده، تست، lint و type-check سبز باشند و PROGRESS.md به‌روز شده باشد.
