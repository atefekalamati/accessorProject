# PROGRESS — منبع واحد «کجاییم؟»

**Last Updated:** 2026-09-29

## Current / Next
- **Phase › Milestone:** 1 Foundation › M1.2 Shared infrastructure
- **Current Task:** INF-03 — Pagination & filter/sort allowlist · COMPLETE → [tasks/phase-01/INF-03-pagination-allowlist.md](../../tasks/phase-01/INF-03-pagination-allowlist.md)
- **Status:** INF-03 COMPLETE: `app/shared/pagination.py` (page/limit برای public با سقف 48 و admin با سقف 100، `Page[T]`، sort و query-param allowlist)؛ `BadRequestError` (400).
- **Progress:** 18/140 task COMPLETE · وزنی 7.6% (31h / 407h) · MVP 11.6%
- **Blockers:** فاز ۱ مانعی ندارد. در فاز ۵: D8، D9، D10 (انتخاب provider واقعی) و D13.
- **Next Action:** قدم بعدی فاز ۱ (INF-04 یا FND-06) — بررسی task، پیشنهاد plan و گرفتن تأیید.
- **Branch:** `feat/m1.1-repo-foundation` (از `docs/project-planning`)
- **Stale branch:** `backend` (local و `origin/backend`، commit `48f1542`) قدیمی است و کاملاً در `master` merge شده (commit اضافه‌ای ندارد). طبق دستور کاربر دست‌نخورده می‌ماند و روی آن کار نمی‌کنیم.

---

## Overall Progress
**7.6%** = 31h COMPLETE / 407h planned (estimate). **روش:** وزن‌دهی بر اساس ساعت برآوردی (CANCELLED حذف می‌شود).

## Phase Progress
| Phase | Status | Est. | Complete | % | Deadline (پیش‌بینی) |
|---|---|---|---|---|---|
| 1 Foundation | IN_PROGRESS | 37h | 27.5h | 74.3% | 2026-10-09 |
| 2 Core domain | NOT_STARTED | 129h | 3h | 2.3% | 2026-12-06 |
| 3 Purchase flow | NOT_STARTED | 100.5h | 0.5h | 0.5% | 2027-01-22 |
| 4 Account & admin | NOT_STARTED | 61h | 0 | 0% | 2027-02-19 |
| 5 Release | NOT_STARTED | 41h | 0 | 0% | 2027-03-10 |
| 6 Post-core | NOT_STARTED | 38.5h | 0 | 0% | 2027-03-28 |

## Deadlines & Schedule
- فرض (قابل تغییر): تنها، پاره‌وقت، ۱۵ ساعت در هفته، بدون ددلاین سخت. همه ددلاین‌ها **پیش‌بینی** هستند.
- باقی‌مانده: 376h ≈ ۲۵ هفته. MVP باقی‌مانده: 235.5h ≈ ۱۶ هفته.
- **Verdict:** on track نسبت به forecast (بدون buffer).

## Completed Recently
- 2026-09-29: INF-03 (Page/limit pagination, sort & query-param allowlist).
- 2026-09-29: INF-01 (Error code catalog, domain errors, validation → 400).
- 2026-09-29: INF-02 (Integer-Toman money utilities)؛ DEC ثبت‌شده: D18 (ADR-014).
- 2026-09-29: FND-03 (Docker/Compose end-to-end).
- 2026-09-29: DEC-01، DEC-02، DEC-03، DEC-04، DEC-05، DEC-06، DEC-07، DEC-11، DEC-12، DEC-16 (ADR-003 تا ADR-013).
- 2026-09-13: FND-01، FND-02، FND-04، FND-05 (تأیید با اجرای تست‌ها در 2026-09-29).

## Remaining Work
- فاز ۱: FND-06، FND-07، INF-04 تا INF-06.
- فاز ۲ تا ۶: طبق [PLAN.md](PLAN.md).

## Blockers
| Blocked task | Cause |
|---|---|
| PAY-07 | D8 — انتخاب درگاه واقعی (قبل از فاز ۵) |
| OPS-05 | D9 — انتخاب SMS provider (قبل از فاز ۵) |
| OPS-07 | D10 — انتخاب file storage (قبل از فاز ۵) |
| OPS-04 | D13 — محیط production (deferred به فاز ۵) |

---

## Plan changes
### 2026-09-29 — INF-03: سبک pagination
- PRD («دسته‌بندی محصولات» ✓) صراحتاً `page`/`limit` و «تعداد کل» و «اطلاعات صفحه‌بندی» می‌خواهد، پس لیست‌های عمومی هم page/limit شدند (نه cursor). سقف limit برای public ۴۸ و برای admin ۱۰۰ است و page حداکثر ۱۰۰۰.
- **CAT-07:** معیار پذیرش جدید اضافه شد: helper مشترک برای کوئری صفحه‌بندی‌شده (count + offset، مرتب‌سازی قطعی با `id` برای شکستن تساوی) و تست pagination در سطح DB. برآورد از 5h به 6h رسید و کل برآورد از 406h به 407h. به‌جای helper از نوع keyset، helper از نوع offset ثبت شد، چون cursor حذف شده است.
- اصلاح جانبی: مقادیر COMPLETE فاز ۱ و مجموع کل در PLAN.md و ROADMAP.md قدیمی بودند و به‌روز شدند.

### 2026-09-29 — تصمیم‌های کاربر
- همه تصمیم‌های D1 تا D16 به‌جز D13 resolved شدند (ADR-001 تا ADR-013). D13 deferred شد. همه taskهای BLOCKED فاز ۱ تا ۴ به NOT_STARTED منتقل شدند.
- **تغییر نسبت به پیشنهاد قبلی:** validation → 400 و قانون کسب‌وکار → 422 (ADR-011). INF-01 رفتار فعلی repo را تغییر می‌دهد.
- **task جدید:** HANDOFF-01 (آخر فاز ۳، 3h) و OPS-07 (adapter واقعی storage، 3h).
- **جابه‌جایی:** DEC-10 از M2.2 به M5.2 منتقل شد و عنوانش به «Choose real file storage» تغییر کرد. DEC-08 و DEC-09 هم به «Choose real …» تغییر نام دادند.
- **PRD:** شش بخش مرجع طبق D2، D3، D4، D5، D6، D7 و D16 ویرایش شدند (جدول «PRD changes» در DECISIONS.md). taskهای `-00` از این به بعد بخش قالبی خود را بازنویسی و «✓ بازبینی‌شده» می‌کنند.
- **زمان‌بندی:** forecast بر اساس ۱۵ ساعت در هفته اضافه شد.

### 2026-09-29 — مهاجرت به ساختار فازبندی
- ساختار `M0`/`M1` به ۶ فاز، ۲۱ milestone و ۱۳۸ task منتقل شد (اکنون ۱۴۰ task).
- نگاشت فایل‌های قدیمی (محتوا منتقل شد، فایل‌های قدیمی حذف شدند): M0-01 → FND-03، M0-02 → FND-06، M0-03 → FND-07، M1-01 → INF-01، M1-02 → INF-02، M1-03 → INF-03، M1-04 → INF-04، M1-05 → INF-05.
- INF-06 اضافه شد. کارهای قبلی به‌صورت FND-01، FND-02، FND-04 و FND-05 (COMPLETE با شواهد) ثبت شدند.

## Log (جدیدترین بالا)
### 2026-09-29 — INF-03 COMPLETE
- **انجام شد:** `app/shared/pagination.py` شامل `PageParams`، `page_params()` و `public_page_params`/`admin_page_params`، `Page[T]` (`items`، `total`، `page`، `limit`، `pages`)، `resolve_sort` (کلید عمومی ← ordering سمت سرور) و `allowed_query_params`. همچنین `BadRequestError` در `app/core/errors.py`. تست‌ها در `tests/test_pagination.py`.
- **اعتبارسنجی:** pytest 268 passed (دیتابیس تست موقت)؛ ruff، format و mypy سبز.
- **بعدی:** INF-04 یا FND-06.

### 2026-09-29 — INF-01 COMPLETE
- **انجام شد:** `ErrorCode` + `ERROR_STATUS` (منبع واحد code → status)، زیرکلاس‌های 401/403/404/409/422/429 (`Retry-After`)، validation → 400، OpenAPI به‌روز شد، و `tests/test_errors.py` شامل تست 400 برای `Toman`، کامل‌بودن mapping و 500 عمومی. اصلاح‌های جانبی: هدر `X-Request-ID` روی 500، و `disable_existing_loggers=False` در `alembic/env.py`.
- **اعتبارسنجی:** pytest 217 passed (دیتابیس تست موقت)؛ ruff، format و mypy سبز.
- **بعدی:** INF-03.

### 2026-09-29 — INF-02 COMPLETE
- **انجام شد:** `app/shared/money.py` و `tests/test_money.py` (۴۸ تست). تصمیم D18 (ADR-014): modeهای `up`، `down`، `nearest` (half-up)، پیش‌فرض `nearest`/step=1. معیار HTTP 400 به INF-01 منتقل شد.
- **اعتبارسنجی:** pytest کامل با دیتابیس تست موقت؛ ruff، format و mypy سبز.
- **بعدی:** INF-01.

### 2026-09-29 — FND-03 COMPLETE
- **انجام شد:** Dockerfile با pip cache mount و `PIP_INDEX_URL` قابل تنظیم (build arg از `.env`). build با یک تلاش موفق شد. up، migrate، seed و `/health`، `/ready`، `/docs` (200) روی 8001 تأیید شد. هدر گزارش در CLAUDE.md بدون emoji شد. slash commandهای `/next`، `/done`، `/status`، `/blocked` اضافه شدند.
- **اعتبارسنجی:** pytest 24 passed (دیتابیس تست موقت)؛ ruff، format و mypy سبز.
- **بعدی:** INF-02.

### 2026-09-29 — ثبت تصمیم‌ها و ویرایش PRD
- **انجام شد:** DECISIONS.md (ADR-003 تا ADR-013 و جدول PRD changes)، ۲۳ ویرایش در بخش‌های مرجع PRD، به‌روزرسانی PLAN، ROADMAP و taskها، پروتکل جلسه در CLAUDE.md، و یادداشت تاریخی روی نقشه راه قدیمی.
- **بعدی:** FND-03.

### 2026-09-29 — مهاجرت سیستم برنامه‌ریزی
- بازنویسی فایل‌های برنامه‌ریزی؛ ساخت `tasks/phase-01/` (۱۶ فایل) و `tasks/phase-02/` (۱۴ فایل).

### 2026-09-29 — راه‌اندازی سیستم برنامه‌ریزی
- **اعتبارسنجی:**
  - `pytest` با PostgreSQL 16 موقت: 24 passed.
  - ruff، format و mypy: سبز.
  - چرخه alembic downgrade/upgrade: موفق.
  - seed، `docker compose config` و `docker build`: موفق.
  - smoke test با `uvicorn`: `/health` و `/api/v1/ready` پاسخ 200 دادند.
