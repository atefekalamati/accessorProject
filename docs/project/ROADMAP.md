# ROADMAP — Project AK (ATK) Backend

| | |
|---|---|
| **Work mode (فرض قابل تغییر)** | تنها، پاره‌وقت، ۱۵ ساعت در هفته، بدون ددلاین سخت |
| **Forecast MVP (پایان فاز ۳)** | **پیش‌بینی:** 2027-01-22 |
| **Forecast کل پروژه** | **پیش‌بینی:** 2027-03-28 |
| **Total estimated effort** | 406h (estimate) · MVP: 265.5h |
| **Completed effort** | 20h (4.9%) · MVP: 7.5% |
| **Schedule verdict** | ددلاین سختی وجود ندارد، پس verdict فقط نسبت به forecast است: **on track** (شروع 2026-09-29). forecast هیچ buffer ندارد. اگر برآوردها ۲۰ تا ۳۰٪ بیشتر شوند، پایان MVP حدود فوریه تا مارس 2027 می‌شود. |

- **روش forecast:** ساعت باقی‌مانده تجمعی ÷ ۱۵ ساعت در هفته، از 2026-09-29. همه تاریخ‌ها **پیش‌بینی** هستند و با هر تغییر برآورد یا سرعت واقعی به‌روز می‌شوند.
- **روش درصد:** ساعت برآوردی taskهای COMPLETE ÷ کل ساعت (CANCELLED حذف می‌شود).
- taskها در [PLAN.md](PLAN.md) و وضعیت جاری در [PROGRESS.md](PROGRESS.md) است.

| Phase | Name | Status | Deadline (پیش‌بینی) | Effort (est.) | Done | Deps (phases / decisions) |
|---|---|---|---|---|---|---|
| 1 | Foundation | IN_PROGRESS | 2026-10-09 | 37h | 44.6% | — |
| 2 | Core domain | NOT_STARTED | 2026-12-06 | 128h | 2.3% | 1 |
| 3 | Purchase flow (MVP line) | NOT_STARTED | 2027-01-22 | 100.5h | 0.5% | 2 |
| 4 | Account & admin | NOT_STARTED | 2027-02-19 | 61h | 0% | 3 |
| 5 | Release | NOT_STARTED | 2027-03-10 | 41h | 0% | 3–4 / D8، D9، D10 (انتخاب واقعی)، D13 |
| 6 | Post-core (suggestion) | NOT_STARTED | 2027-03-28 | 38.5h | 0% | 3 |

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
- **Milestones:** M5.1 Security · M5.2 Operations. انتخاب درگاه، SMS، storage و محیط production قبل از شروع این فاز انجام می‌شود.

## Phase 6 — Post-core (پیشنهاد)
- کالکشن، جست‌وجوی پیشرفته، علاقه‌مندی، مرجوعی، اعلان. PRD همه را نسخه اول می‌داند؛ جایگاه آن‌ها بعد از هسته فقط پیشنهاد است.
