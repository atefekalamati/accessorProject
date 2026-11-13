# WORKFLOW — گردش کار برنامه‌ریزی

قوانین دامنه و «پروتکل جلسه» در `CLAUDE.md` هستند. این فایل جزئیات گردش کار است.

## فایل‌های برنامه‌ریزی

| فایل | کاربرد |
|---|---|
| `docs/project/ROADMAP.md` | ۶ فاز: هدف، وضعیت، برآورد، درصد، ددلاین (پیش‌بینی)، verdict زمان‌بندی |
| `docs/project/PLAN.md` | فهرست همه milestoneها و taskها (ID، وضعیت، اولویت، برآورد، وابستگی، done when) |
| `docs/project/PROGRESS.md` | **منبع واحد «کجاییم؟»**: بخش Current / Next، درصد، blockerها، Plan changes، log |
| `docs/project/DECISIONS.md` | تصمیم‌های D1… (با task `DEC-NN` و taskهایی که مسدود می‌کنند)، ADRها و جدول PRD changes |
| `tasks/phase-0N/<ID>-<slug>.md` | جزئیات task؛ قالب و قواعد در `tasks/README.md` |

- **وضعیت‌ها:** `NOT_STARTED` / `IN_PROGRESS` / `BLOCKED` (منتظر تصمیم باز) / `COMPLETE` / `CANCELLED` / `DEFERRED` (کاربر به بعد موکول کرد).
- **درصد:** ساعت برآوردی COMPLETE ÷ کل ساعت (CANCELLED و DEFERRED حذف می‌شوند؛ ADR-058).
- **ددلاین‌ها:** فقط forecast با برچسب «پیش‌بینی». هرگز تاریخ حدسی بدون مبنا ننویس.

## برای هر task
1. فایل task و فقط بخش مرتبط PRD را بخوان و کد مرتبط را بررسی کن.
2. برای کار غیربدیهی، plan کوتاه (فایل‌ها، چرا، ریسک‌ها) بده و منتظر تأیید بمان.
3. کوچک‌ترین تغییر مناسب را پیاده کن.
4. معیارهای پذیرش را بررسی کن و تست، lint و type-check را اجرا کن.
5. وضعیت و Log فایل task را به‌روز کن.
6. PROGRESS.md (Current / Next، درصد) و در صورت نیاز PLAN.md و ROADMAP.md را به‌روز کن.
7. تصمیم معماری جدید را در DECISIONS.md ثبت کن.
8. commit کن (Conventional Commits، روی شاخه فاز) و گزارش کوتاه بده.

بدون validation هرگز COMPLETE نزن. اگر نیازمندی مبهم است، در DECISIONS.md ثبت کن و قبل از هر تغییر برگشت‌ناپذیر بپرس.

## تغییر برنامه
تاریخچه را بی‌صدا بازنویسی نکن:
- task حذف‌شده `CANCELLED` با ذکر دلیل می‌شود.
- task جدید ID جدید می‌گیرد.
- ددلاین‌ها به‌روز می‌شوند.
- یک ورودی تاریخ‌دار در «Plan changes» در PROGRESS.md ثبت می‌شود.

## درخواست‌های رایج
همیشه از فایل‌ها جواب بده، نه از حافظه گفت‌وگو.

| درخواست | منبع |
|---|---|
| «کجاییم؟» / Where are we? · «وضعیت پروژه» / Show project status | PROGRESS.md (+ ROADMAP.md) |
| «قدم بعدی؟» / What's next? · «از جایی که ماندیم ادامه بده» / Continue | PROGRESS.md › Current / Next → فایل task |
| «چه چیزی جلوی ما را گرفته؟» / What's blocking us? | PROGRESS.md › Blockers + DECISIONS.md |
| «چقدر مانده؟» / How much remains? | PROGRESS.md › Overall Progress + ROADMAP.md |
| «فاز بعد را برنامه‌ریزی کن» / Plan the next phase | PLAN.md → ساخت فایل‌های task آن milestone |
| «این feature را به task بشکن» / Break into tasks | PLAN.md (ID جدید) + فایل task |
| «این task تمام شد» / Mark complete | validation → فایل task → PROGRESS.md → PLAN.md/ROADMAP.md |
| «برنامه را به‌روز کن» / Update the plan | همه فایل‌ها + Plan changes |
