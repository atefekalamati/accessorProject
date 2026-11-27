# ROADMAP — Project AK (ATK) Backend

| | |
|---|---|
| **Work mode (فرض قابل تغییر)** | تنها، پاره‌وقت، ۱۵ ساعت در هفته، بدون ددلاین سخت |
| **Forecast MVP (پایان فاز ۳)** | **پیش‌بینی:** 2027-01-23 |
| **Forecast کل پروژه** | **پیش‌بینی:** 2026-12-18 (بدون taskهای DEFERRED؛ production go-live جدا، ADR-058) |
| **Total estimated effort** | 419h فعال (estimate؛ 17h DEFERRED جدا) · MVP: 280.5h |
| **Completed effort** | 347.5h (82.9%) · فاز ۴: 2026-11-13 (PR #7، tag `phase-4`) |
| **Schedule verdict** | ددلاین سختی وجود ندارد، پس verdict فقط نسبت به forecast است: **on track** (شروع 2026-09-29). forecast هیچ buffer ندارد. اگر برآوردها ۲۰ تا ۳۰٪ بیشتر شوند، پایان MVP حدود فوریه تا مارس 2027 می‌شود. |

- **روش forecast:** ساعت باقی‌مانده تجمعی ÷ ۱۵ ساعت در هفته، از 2026-09-29. همه تاریخ‌ها **پیش‌بینی** هستند و با هر تغییر برآورد یا سرعت واقعی به‌روز می‌شوند.
- **روش درصد:** ساعت برآوردی taskهای COMPLETE ÷ کل ساعت (CANCELLED و DEFERRED حذف می‌شوند).
- **سرعت واقعی:** فاز ۴ در 2026-11-13 تمام شد، حدود ۱۴ هفته زودتر از forecast قبلی. forecastهای زیر از 2026-11-13 و با همان ۱۵ ساعت در هفته دوباره حساب شده‌اند و هنوز محافظه‌کارانه‌اند.
- taskها در [PLAN.md](PLAN.md) و وضعیت جاری در [PROGRESS.md](PROGRESS.md) است.

| Phase | Name | Status | Deadline (پیش‌بینی) | Effort (est.) | Done | Deps (phases / decisions) |
|---|---|---|---|---|---|---|
| 1 | Foundation | COMPLETE | 2026-10-09 | 37h | 100% | — |
| 2 | Core domain | COMPLETE | 2026-12-07 | 142h | 100% | 1 |
| 3 | Purchase flow (MVP line) | COMPLETE | 2027-01-23 | 101.5h | 100% | 2 |
| 4 | Account & admin | COMPLETE | 2026-11-13 (واقعی) | 67h | 100% | 3 |
| 5 | Release | IN_PROGRESS | 2026-11-27 | 29h فعال (+17h DEFERRED) | 0% | 3–4 · production go-live: D8، D9، D10، D13 (DEFERRED، ADR-058) |
| 6 | Post-core (suggestion) | NOT_STARTED | 2026-12-18 | 42.5h | 0% | 3 |

## Phase 1 — Foundation
- **Objective:** repo قابل اجرا، دیتابیس، migration، تست و lint، و زیرساخت مشترک.
- **Milestones:** M1.1 Repo foundation · M1.2 Shared infrastructure.
- **Deliverables:** Docker قابل اجرا، دیتابیس تست با `profiles: [test]`، CI با GitHub Actions، کاتالوگ خطا (validation = 400 و قانون کسب‌وکار = 422)، ابزار پول، pagination، soft delete، سرویس audit، redaction در log.

## Phase 2 — Core domain
- **Objective:** هویت، کاتالوگ، موجودی و قیمت.
- **Milestones:** M2.1 Auth & RBAC · M2.2 Catalog · M2.3 Inventory & reservation · M2.4 Pricing & tax.
- **Deliverables:** OTP، ۵ نقش، refresh در cookie، کاتالوگ، InventoryItem با یک انبار پیش‌فرض، تابع خالص قیمت با `tax_enabled=false`.

## Phase 3 — Purchase flow (MVP line)
- **Objective:** جریان کامل خرید.
- **Milestones:** M3.1 Cart · M3.2 Discount codes · M3.3 Address & shipping · M3.4 Checkout & orders · M3.5 Payment.
- **Done when:** تست end-to-end (PAY-06) سبز شود و HANDOFF-01 (سازگاری PRD و `openapi.json` برای فرانت) انجام شود.

## Phase 4 — Account & admin
- **Milestones:** M4.1 Customer account · M4.2 Admin panel · M4.3 Content & home page.

## Phase 5 — Release
- **Milestones:** M5.1 Security · M5.2 Operations.
- **Scope (ADR-058):** D8، D9، D10 و D13 موکول شدند. PAY-07، OPS-04، OPS-05، OPS-07 و DEC-08/09/10/13 `DEFERRED` هستند. دروازه فاز ۵ با بقیه taskها بسته می‌شود و یک image آماده staging می‌دهد. **استقرار production تا آن تصمیم‌ها و taskها مسدود است.**

## Phase 6 — Post-core
- **Scope (ADR-062):** مرجوعی (M6.4) و حذف حساب (M6.6). کالکشن، جست‌وجوی پیشرفته، علاقه‌مندی و اعلان `POST_LAUNCH` هستند (در PLAN می‌مانند، از forecast بیرون‌اند).
