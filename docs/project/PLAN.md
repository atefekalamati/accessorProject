# PLAN — فهرست فازها، milestoneها و taskها

- جزئیات هر task در `tasks/phase-0N/<ID>-<slug>.md` است. ستون «فایل» با ✓ یعنی فایل task وجود دارد.
- وضعیت‌ها: `NOT_STARTED` · `IN_PROGRESS` · `BLOCKED` (منتظر تصمیم باز) · `COMPLETE` · `CANCELLED`.
- **همه برآوردها (h) تخمین هستند.** ددلاین‌ها **پیش‌بینی (forecast)** هستند، نه تعهد. فرض: کار تنها و پاره‌وقت، ۱۵ ساعت در هفته، شروع 2026-09-29، بدون buffer. پیش‌بینی فقط در سطح فاز است.
- ستون **Level** (LOW/MEDIUM/HIGH) سطح ریسک task است، نه اولویت (Pri). plan هر task با Level=HIGH باید ریسک‌ها، مراحل rollback و تست‌های اضافه را هم فهرست کند (CLAUDE.md بخش ۱۱).
- **قاعده soft delete (SD rule):** هر read عمومی (list یا detail) رکورد soft-deleted را برنمی‌گرداند و detail آن → 404 `NOT_FOUND`. هر write که به entity ارجاع می‌دهد (افزودن به سبد، `POST /checkout/validate`، `POST /orders` و...) ارجاع به رکورد soft-deleted را رد می‌کند، با همان خطای ارجاع به entity ناموجود. taskهایی که «SD rule (test)» دارند باید برای آن تست داشته باشند. فیلد unique روی مدل soft-deletable طبق ADR-015 partial unique index با شرط `WHERE deleted_at IS NULL` است و تصمیم هر مدل در task خودش گرفته می‌شود.
- قاعده خطا (ADR-011): validation → **400**، نقض قانون کسب‌وکار → **422**.
- task `-00` (نیازمندی) بخش **قالبی** PRD همان ماژول را بازنویسی می‌کند، عنوان آن بخش را «✓ بازبینی‌شده» می‌کند، ردیفی به «PRD changes» در DECISIONS.md اضافه می‌کند و به تأیید کاربر نیاز دارد.

---

## Phase 1 — Foundation · forecast: 2026-10-09

### M1.1 Repo foundation
| ID | Title | Status | Pri | Level | Est | Deps | Done when | فایل |
|---|---|---|---|---|---|---|---|---|
| FND-01 | App skeleton, settings, /health, API docs | COMPLETE | HIGH | LOW | 4 | — | health/settings tests green | ✓ |
| FND-02 | Request-id, JSON logging, unified error handlers | COMPLETE | HIGH | MEDIUM | 3 | FND-01 | error-contract test green | ✓ |
| FND-03 | Docker/Compose runnable end-to-end | COMPLETE | HIGH | MEDIUM | 3 | FND-01, FND-04 | compose up healthy; migrate + seed in container | ✓ |
| FND-04 | Database layer + initial migration | COMPLETE | HIGH | MEDIUM | 6 | FND-01 | 24 tests green on PG16 | ✓ |
| FND-05 | Role seed, dev DB-status route, DBeaver doc | COMPLETE | MEDIUM | LOW | 2 | FND-04 | seed idempotent test green | ✓ |
| FND-06 | Test DB via compose `profiles: [test]` | COMPLETE | MEDIUM | LOW | 1.5 | FND-04, ADR-013 | one command → all tests | ✓ |
| FND-07 | CI with GitHub Actions | COMPLETE | MEDIUM | LOW | 2 | FND-06, ADR-013 | CI green | ✓ |
| DEC-01 | Confirm stack (D1) | COMPLETE | HIGH | LOW | 0.5 | — | ADR-003 | ✓ |

### M1.2 Shared infrastructure
| ID | Title | Status | Pri | Level | Est | Deps | Done when | فایل |
|---|---|---|---|---|---|---|---|---|
| INF-01 | Error code catalog, domain errors, validation → 400 | COMPLETE | HIGH | HIGH | 3 | FND-02, ADR-008, ADR-011 | 400/422/409 rules tested; OpenAPI updated | ✓ |
| INF-02 | Integer-Toman money utilities | COMPLETE | HIGH | HIGH | 2 | ADR-001 | no float; rounding table-tested | ✓ |
| INF-03 | Pagination & filter/sort allowlist | COMPLETE | HIGH | MEDIUM | 3 | FND-02 | bad page/limit/sort/param → 400 | ✓ |
| INF-04 | Soft delete mixin & helpers | COMPLETE | MEDIUM | MEDIUM | 1.5 | FND-04 | soft-deleted rows filtered; no migration diff | ✓ |
| INF-05 | AuditLog writer service | COMPLETE | HIGH | MEDIUM | 3 | FND-04 | same-transaction audit; secrets redacted | ✓ |
| INF-06 | Sensitive-data redaction in logs | COMPLETE | MEDIUM | HIGH | 1.5 | FND-02 | OTP/tokens never logged; phone masked | ✓ |
| DEC-07 | HTTP 410 (D7) | COMPLETE | MEDIUM | HIGH | 0.5 | — | ADR-008 | ✓ |
| DEC-12 | Error format, 400 vs 422 (D12) | COMPLETE | HIGH | HIGH | 0.5 | — | ADR-011 | ✓ |

**Phase 1:** 37h · COMPLETE 37h

---

## Phase 2 — Core domain · forecast: 2026-12-07

### M2.1 Auth & RBAC — PRD «هویت و دسترسی» ✓
| ID | Title | Status | Pri | Level | Est | Deps | Done when | فایل |
|---|---|---|---|---|---|---|---|---|
| DEC-02 | Role set (D2) | COMPLETE | HIGH | HIGH | 0.5 | — | ADR-004 | ✓ |
| DEC-16 | Token transport (D16) | COMPLETE | HIGH | HIGH | 0.5 | — | ADR-012 | ✓ |
| SEC-05 | Secret scanning in CI (gitleaks, pinned, allowlist for fake fixtures) | COMPLETE | HIGH | MEDIUM | 2 | FND-07 | CI fails on findings; history scan clean | ✓ |
| SEC-06 | Dependency lock file with hashes; CI + Dockerfile install from it | NOT_STARTED | MEDIUM | MEDIUM | 2 | FND-07, FND-03 | --require-hashes in CI and Docker; drift check | ✓ |
| AUTH-01 | Align User model with PRD + migration | COMPLETE | HIGH | HIGH | 2 | FND-04 | new migration; one active account per mobile | ✓ |
| AUTH-02 | Roles & permissions seed (5 roles) | COMPLETE | HIGH | HIGH | 3 | FND-05, ADR-004 | idempotent seed incl. super_admin | ✓ |
| AUTH-03 | OtpCode model (hashed, expiring, attempts) | COMPLETE | HIGH | HIGH | 2 | AUTH-01 | no plaintext OTP column | ✓ |
| AUTH-04 | SMS provider interface + fake | COMPLETE | HIGH | HIGH | 2 | ADR-009 | fake injectable in tests | ✓ |
| AUTH-05 | POST /auth/request-otp + rate limit (429) | COMPLETE | HIGH | HIGH | 4 | AUTH-03, AUTH-04, INF-01, INF-06 | per-mobile & per-IP 429 tested | ✓ |
| AUTH-06 | POST /auth/verify-otp + Session + token service | COMPLETE | HIGH | HIGH | 4 | AUTH-05, AUTH-02, ADR-012, SEC-05 | single-use OTP; refresh cookie; hashed | ✓ |
| AUTH-07 | POST /auth/refresh with rotation | COMPLETE | HIGH | HIGH | 3 | AUTH-06 | rotation + reuse detection | ✓ |
| AUTH-08 | POST /auth/logout | COMPLETE | MEDIUM | HIGH | 1.5 | AUTH-07 | cookie cleared; refresh → 401 | ✓ |
| AUTH-09 | GET /auth/me, PATCH /users/me | COMPLETE | HIGH | HIGH | 2.5 | AUTH-06 | system fields rejected (400) | ✓ |
| AUTH-10 | Permission dependency + ownership helper | COMPLETE | HIGH | HIGH | 3 | AUTH-06, AUTH-02 | 401/403 from DB permissions | ✓ |
| AUTH-11 | Admin user endpoints + AuditLog + warehouse_manager data migration | COMPLETE | MEDIUM | HIGH | 5 | AUTH-10, INF-03, INF-05 | only super_admin changes roles; only DEFAULT_ROLES assignable | ✓ |
| AUTH-12 | Auth API & security test suite | COMPLETE | HIGH | HIGH | 3 | AUTH-05…11 | all PRD acceptance criteria tested | ✓ |

### M2.2 Catalog — PRD «دسته‌بندی محصولات» ✓، «جزئیات محصول» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| DEC-03 | Stock model (D3) | COMPLETE | HIGH | HIGH | 0.5 | — | ADR-005 |
| CAT-00 | Rewrite «جزئیات محصول» requirements | NOT_STARTED | HIGH | HIGH | 2 | — | PRD section ✓ بازبینی‌شده + approved |
| CAT-01 | Category model + migration (tree, slug, status, order) | NOT_STARTED | HIGH | MEDIUM | 3 | INF-04 | unique slug; inactive hidden |
| CAT-02 | Product model + soft delete + draft/published/archived | NOT_STARTED | HIGH | MEDIUM | 3 | CAT-01, INF-04 | referenced products soft-deleted only |
| CAT-03 | ProductVariant model (SKU, active, purchasable; no stock column) | NOT_STARTED | HIGH | MEDIUM | 3 | CAT-02, ADR-005 | unique SKU |
| CAT-04 | Attributes & values (color/size/model) | NOT_STARTED | HIGH | MEDIUM | 3 | CAT-03 | variant ↔ attribute values |
| CAT-05 | Media model + storage interface + local fake | NOT_STARTED | MEDIUM | MEDIUM | 4 | CAT-02, ADR-009 | ordered media, main image |
| CAT-06 | Public GET /categories, /categories/{slug} | NOT_STARTED | HIGH | MEDIUM | 3 | CAT-01 | only active categories; SD rule (test) |
| CAT-07 | Public product listing with filters/sort/pagination | NOT_STARTED | HIGH | MEDIUM | 6 | CAT-03, INF-03 | allowlisted filters; no N+1; shared paginated-query helper (count + offset, deterministic `id` tie-break) + DB-level pagination tests (no dup/skip across pages, correct total); SD rule (test) |
| CAT-08 | Public product detail GET /products/{slug} | NOT_STARTED | HIGH | MEDIUM | 3 | CAT-00, CAT-04, CAT-05 | published only; stable contract; SD rule (test) |
| CAT-09 | Category filters endpoint + CategoryFilter | NOT_STARTED | MEDIUM | MEDIUM | 3 | CAT-04 | filters from data; SD rule (test) |
| CAT-10 | Admin category CRUD + AuditLog | NOT_STARTED | HIGH | MEDIUM | 3 | CAT-01, AUTH-10, INF-05 | changes audited |
| CAT-11 | Admin product/variant CRUD + publish rules | NOT_STARTED | HIGH | MEDIUM | 5 | CAT-03, CAT-05, AUTH-10 | published needs active variant + main media; SD rule (test) |
| CAT-12 | Catalog API tests | NOT_STARTED | HIGH | MEDIUM | 3 | CAT-06…11 | 400/401/403/404/409/422 covered |

### M2.3 Inventory & reservation — PRD «موجودی و رزرو» ✓، «انبار» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| DEC-04 | Warehouses (D4) | COMPLETE | HIGH | HIGH | 0.5 | — | ADR-005 |
| DEC-06 | Reservation moment (D6) | COMPLETE | HIGH | HIGH | 0.5 | — | ADR-007 |
| INV-01 | Warehouse (1 default) + InventoryItem per variant+warehouse | NOT_STARTED | HIGH | HIGH | 3 | CAT-03, ADR-005 | stock only in InventoryItem |
| INV-02 | InventoryMovement + manual adjustment with reason + audit | NOT_STARTED | HIGH | HIGH | 3 | INV-01, INF-05 | every change → movement + AuditLog |
| INV-03 | Pure free-stock & stock-status functions | NOT_STARTED | HIGH | HIGH | 2 | INV-01 | free = total − active reservations |
| INV-04 | Reservation models + reserve service (row lock), used by POST /orders | NOT_STARTED | HIGH | HIGH | 5 | INV-03, ADR-007 | 15-min; SELECT … FOR UPDATE |
| INV-05 | Commit / release services (idempotent, internal) | NOT_STARTED | HIGH | HIGH | 3 | INV-04, ADR-008 | expired → 409 RESERVATION_EXPIRED |
| INV-06 | Expiry release job / lazy release | NOT_STARTED | HIGH | HIGH | 3 | INV-05 | expired reservations free stock |
| INV-07 | GET /products/{id}/availability | NOT_STARTED | MEDIUM | HIGH | 2 | INV-03, CAT-08 | in/low/out status; SD rule (test) |
| INV-08 | Admin inventory endpoints (list, patch, reservations, history) | NOT_STARTED | MEDIUM | HIGH | 4 | INV-02, AUTH-10 | inventory:update enforced |
| INV-09 | Concurrency test: no oversell | NOT_STARTED | HIGH | HIGH | 3 | INV-04 | parallel buyers never go negative |

### M2.4 Pricing & tax — PRD «قیمت و مالیات» ✓
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| DEC-11 | Tax in v1 (D11) | COMPLETE | MEDIUM | LOW | 0.5 | — | ADR-010 |
| PRC-01 | Variant price fields + PricingSetting (tax_enabled=false) + migration | NOT_STARTED | HIGH | HIGH | 3 | CAT-03, INF-02 | salePrice ≤ basePrice constraint |
| PRC-02 | Pure pricing function (sale window, discounts, tax, shipping, single rounding) | NOT_STARTED | HIGH | HIGH | 5 | INF-02 | table-driven unit tests |
| PRC-03 | PriceHistory + admin price change + AuditLog | NOT_STARTED | HIGH | HIGH | 4 | PRC-01, INF-05, AUTH-10 | every change in history + audit |
| PRC-04 | GET /products/{id}/pricing | NOT_STARTED | MEDIUM | HIGH | 2 | PRC-02 | server-computed only; SD rule (test) |
| PRC-05 | Pricing settings (super_admin only) | NOT_STARTED | MEDIUM | HIGH | 3 | PRC-01, AUTH-10 | others → 403 |
| PRC-06 | Pricing tests (unit table + tamper API) | NOT_STARTED | HIGH | HIGH | 3 | PRC-02…05 | client amounts ignored |

**Phase 2:** 132h · COMPLETE 18h

---

## Phase 3 — Purchase flow (MVP line) · forecast: 2027-01-23

### M3.1 Cart — PRD «سبد خرید»، «ورود یا خرید مهمان» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| DEC-05 | Validate endpoints (D5) | COMPLETE | HIGH | HIGH | 0.5 | — | ADR-006 |
| CART-00 | Rewrite cart & guest-checkout requirements | NOT_STARTED | HIGH | HIGH | 2 | ADR-006 | PRD sections ✓ بازبینی‌شده + approved |
| CART-01 | Cart & CartItem models + secure guest cart token | NOT_STARTED | HIGH | MEDIUM | 4 | CART-00, CAT-03 | guest and user carts |
| CART-02 | Add/update/remove items with free-stock check (no reservation) | NOT_STARTED | HIGH | HIGH | 4 | CART-01, INV-03 | qty ≤ free stock; add ≠ reserve; SD rule (test) |
| CART-03 | GET /cart computed server-side with price/stock change flags | NOT_STARTED | HIGH | HIGH | 3 | CART-02, PRC-02 | changes reported |
| CART-04 | Guest → user cart merge on login | NOT_STARTED | HIGH | MEDIUM | 3 | CART-01, AUTH-06 | deterministic merge |
| CART-05 | Cart tests | NOT_STARTED | HIGH | MEDIUM | 3 | CART-02…04 | ownership 403/404 covered |

### M3.2 Discount codes — PRD «کد تخفیف»، «تخفیف‌ها» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| DSC-00 | Rewrite discount requirements | NOT_STARTED | HIGH | HIGH | 2 | — | PRD sections ✓ بازبینی‌شده + approved |
| DSC-01 | DiscountCode & redemption models | NOT_STARTED | HIGH | HIGH | 3 | DSC-00 | limits modeled; per-user usage limit keyed by normalized phone, not user_id (ADR-017) |
| DSC-02 | Pure discount validation/calculation | NOT_STARTED | HIGH | HIGH | 4 | DSC-01, PRC-02 | expired/used/ineligible → 422 |
| DSC-03 | Apply/remove code on cart | NOT_STARTED | HIGH | HIGH | 3 | DSC-02, CART-03 | recalculated server-side |
| DSC-04 | Admin discount CRUD + AuditLog | NOT_STARTED | MEDIUM | HIGH | 3 | DSC-01, AUTH-10, INF-05 | audited |
| DSC-05 | Concurrent usage-cap test | NOT_STARTED | HIGH | HIGH | 2 | DSC-03 | cap never exceeded |

### M3.3 Address & shipping — PRD «آدرس»، «شیوه ارسال» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| ADDR-00 | Rewrite address & shipping requirements | NOT_STARTED | HIGH | HIGH | 2 | — | PRD sections ✓ بازبینی‌شده + approved |
| ADDR-01 | Address CRUD with ownership (table exists) | NOT_STARTED | HIGH | MEDIUM | 3 | ADDR-00, AUTH-10 | own addresses only; one default |
| ADDR-02 | ShippingMethod + shipping calculator interface | NOT_STARTED | HIGH | HIGH | 3 | ADDR-00, INF-02 | cost from backend |
| ADDR-03 | Admin shipping methods | NOT_STARTED | MEDIUM | HIGH | 2 | ADDR-02, AUTH-10 | audited |
| ADDR-04 | Address & shipping tests | NOT_STARTED | HIGH | MEDIUM | 2 | ADDR-01…03 | ownership + validation |

### M3.4 Checkout & orders — PRD «نتیجه سفارش»، «مدیریت سفارش» (قالبی) + «معماری سیستم» ✓
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| ORD-00 | Rewrite checkout & order requirements | NOT_STARTED | HIGH | HIGH | 2 | ADR-006, ADR-007 | PRD sections ✓ بازبینی‌شده + approved |
| ORD-01 | Order, OrderItem snapshot, OrderPriceSnapshot, address snapshot | NOT_STARTED | HIGH | HIGH | 5 | ORD-00, PRC-01 | past orders immune to product changes; order number format cannot resemble a mobile number (e.g. `ORD-YYYY-NNNNNN`) |
| ORD-02 | Idempotency-Key infrastructure | NOT_STARTED | HIGH | HIGH | 3 | INF-01 | same key → same result |
| ORD-03 | POST /checkout/validate | NOT_STARTED | HIGH | HIGH | 3 | CART-03, DSC-03, ADDR-02 | price/stock/discount/shipping re-checked; SD rule (test) |
| ORD-04 | POST /orders (verified mobile, reserve 15 min, snapshot) | NOT_STARTED | HIGH | HIGH | 5 | ORD-01, ORD-02, INV-04 | idempotent; transactional; SD rule (test) |
| ORD-05 | Order state machine (order/payment/shipment) | NOT_STARTED | HIGH | HIGH | 4 | ORD-01 | invalid transitions → 422 |
| ORD-06 | Order tests (idempotency, price-changed, insufficient stock) | NOT_STARTED | HIGH | HIGH | 3 | ORD-03…05 | duplicate create → one order; SD rule (test) |

### M3.5 Payment — PRD «پرداخت» (قالبی) + «معماری سیستم» ✓
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| PAY-00 | Rewrite payment requirements | NOT_STARTED | HIGH | HIGH | 2 | — | PRD section ✓ بازبینی‌شده + approved |
| PAY-01 | Payment model + PaymentGateway interface + fake | NOT_STARTED | HIGH | HIGH | 4 | PAY-00, ORD-01, ADR-009 | fake usable in tests |
| PAY-02 | POST /payments/init | NOT_STARTED | HIGH | HIGH | 3 | PAY-01, ORD-04 | amount = grandTotal from DB |
| PAY-03 | Callback: verify, amount == grandTotal, idempotent, commit reservation | NOT_STARTED | HIGH | HIGH | 5 | PAY-02, INV-05 | duplicate callback changes nothing |
| PAY-04 | Failure/expiry: release reservation, allow retry | NOT_STARTED | HIGH | HIGH | 3 | PAY-03, INV-06 | expired reservation never consumed |
| PAY-05 | Callback tests (duplicate, amount mismatch, expired) | NOT_STARTED | HIGH | HIGH | 3 | PAY-03, PAY-04 | abuse paths covered |
| PAY-06 | End-to-end purchase test | NOT_STARTED | HIGH | HIGH | 4 | PAY-05 | cart → OTP → checkout → order → payment → stock committed |
| HANDOFF-01 | PRD consistency review + export openapi.json | NOT_STARTED | HIGH | HIGH | 3 | PAY-06, all Phase 1–3 `-00` | PRD matches implemented API; `openapi.json` exported for frontend; frontend note: refresh must be single-flight across tabs (ADR-017 reuse detection) |

**Phase 3:** 100.5h · COMPLETE 0.5h

---

## Phase 4 — Account & admin · forecast: 2027-02-20

### M4.1 Customer account — PRD «پروفایل»، «سفارش‌ها» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| ACC-00 | Rewrite account requirements | NOT_STARTED | MEDIUM | HIGH | 2 | — | PRD sections ✓ بازبینی‌شده + approved |
| ACC-01 | Own orders list & detail | NOT_STARTED | HIGH | MEDIUM | 3 | ACC-00, ORD-05 | others' orders → 404 |
| ACC-02 | Account ownership tests | NOT_STARTED | HIGH | MEDIUM | 2 | ACC-01 | IDOR covered |

### M4.2 Admin panel — PRD «داشبورد»، «محصولات»، «مدیریت سفارش»، «مشتریان»، «گزارش‌ها»، «گزارش ممیزی» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| ADM-00 | Rewrite admin requirements | NOT_STARTED | MEDIUM | HIGH | 3 | — | PRD sections ✓ بازبینی‌شده + approved |
| ADM-01 | Admin order list/detail/filter | NOT_STARTED | HIGH | MEDIUM | 4 | ADM-00, ORD-05 | paginated, permission-checked |
| ADM-02 | Order status change + shipment tracking + AuditLog | NOT_STARTED | HIGH | HIGH | 4 | ADM-01 | valid transitions only; audited |
| ADM-03 | Customer list/detail (admin, support) | NOT_STARTED | MEDIUM | MEDIUM | 3 | ADM-00 | no secrets exposed |
| ADM-04 | Dashboard metrics | NOT_STARTED | MEDIUM | HIGH | 4 | ADM-01 | metrics from backend |
| ADM-05 | Sales reports | NOT_STARTED | MEDIUM | HIGH | 4 | ADM-04 | integer Toman totals |
| ADM-06 | Audit log viewer | NOT_STARTED | MEDIUM | MEDIUM | 3 | INF-05 | super_admin only |
| ADM-07 | Role × endpoint matrix tests (5 roles) | NOT_STARTED | HIGH | MEDIUM | 4 | ADM-01…06 | every admin route checked |

### M4.3 Content & home page — PRD «صفحه اصلی» ✓ + «محتوا و بنرها»، «درباره برند»، «تماس با ما»، «سؤالات متداول»، «قوانین و حریم خصوصی» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| CNT-00 | Rewrite content requirements | NOT_STARTED | MEDIUM | HIGH | 3 | — | PRD sections ✓ بازبینی‌شده + approved |
| CNT-01 | HomeSection/items + GET /home | NOT_STARTED | HIGH | MEDIUM | 5 | CAT-08 | only published, in-window content; SD rule (test) |
| CNT-02 | Admin home sections CRUD (content_manager) | NOT_STARTED | MEDIUM | MEDIUM | 3 | CNT-01, AUTH-10 | ordering controllable; audited; SD rule (test) |
| CNT-03 | Banner model + admin | NOT_STARTED | MEDIUM | MEDIUM | 3 | CNT-00, CAT-05 | schedule respected |
| CNT-04 | Static pages (about, terms, privacy) | NOT_STARTED | LOW | LOW | 3 | CNT-00 | published only |
| CNT-05 | FAQ | NOT_STARTED | LOW | LOW | 2 | CNT-00 | ordered, published only |
| CNT-06 | Contact form / tickets | NOT_STARTED | LOW | MEDIUM | 4 | CNT-00 | rate-limited |
| CNT-07 | Content tests | NOT_STARTED | MEDIUM | LOW | 2 | CNT-01…06 | public/admin split covered |

**Phase 4:** 61h

---

## Phase 5 — Release · forecast: 2027-03-12

### M5.1 Security — PRD «امنیت»، «تست و پذیرش»، «حالت‌های رابط» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| SEC-00 | Rewrite security & acceptance requirements | NOT_STARTED | HIGH | HIGH | 2 | — | PRD sections ✓ بازبینی‌شده + approved |
| SEC-01 | Global rate limiting | NOT_STARTED | HIGH | HIGH | 3 | SEC-00 | 429 on abuse |
| SEC-02 | Security headers + request size limit | NOT_STARTED | HIGH | HIGH | 2 | SEC-00 | headers tested |
| SEC-03 | Security review & tests (authz, IDOR, tampering) | NOT_STARTED | HIGH | HIGH | 5 | Phase 3 | findings fixed or tracked |
| SEC-04 | DB-level append-only audit_logs (trigger blocks UPDATE; DELETE trigger exists since FND-04) | NOT_STARTED | HIGH | HIGH | 2 | INF-05 | UPDATE/DELETE rejected by DB (integration test) |

### M5.2 Operations — PRD «پایش و رخدادها» (قالبی)
| ID | Title | Status | Pri | Level | Est | Deps | Done when |
|---|---|---|---|---|---|---|---|
| DEC-08 | Choose real payment gateway (D8) | NOT_STARTED | HIGH | HIGH | 0.5 | — | ADR written |
| DEC-09 | Choose real SMS provider (D9) | NOT_STARTED | HIGH | LOW | 0.5 | — | ADR written |
| DEC-10 | Choose real file storage (D10) | NOT_STARTED | HIGH | LOW | 0.5 | — | ADR written |
| DEC-13 | Production target (D13) | NOT_STARTED | HIGH | LOW | 0.5 | — | ADR written |
| OPS-01 | Metrics + error-tracking adapter | NOT_STARTED | MEDIUM | MEDIUM | 4 | — | metrics endpoint |
| OPS-02 | Monitoring & alerts | NOT_STARTED | MEDIUM | MEDIUM | 3 | OPS-01 | alerts defined |
| OPS-03 | Backup/restore runbook | NOT_STARTED | HIGH | HIGH | 3 | — | restore rehearsed |
| OPS-04 | Deployment docs + production config (incl. trusted-proxy config) | BLOCKED | HIGH | HIGH | 4 | D13 | checklist complete; audit/log IP = real client IP, forwarded headers trusted only from configured proxies |
| OPS-05 | Real SMS provider adapter | BLOCKED | HIGH | HIGH | 3 | AUTH-04, D9 | works behind interface |
| OPS-06 | OpenAPI export & versioning | NOT_STARTED | MEDIUM | LOW | 2 | HANDOFF-01 | versioned file |
| OPS-07 | Real file storage adapter | BLOCKED | HIGH | MEDIUM | 3 | CAT-05, D10 | works behind interface |
| PAY-07 | Real payment gateway adapter (Toman→Rial here) | BLOCKED | HIGH | HIGH | 5 | PAY-01, D8 | verify + callback on sandbox |

**Phase 5:** 43h

---

## Phase 6 — Post-core · forecast: 2027-03-30 (پیشنهاد؛ PRD همه را نسخه اول می‌داند)

taskهای بزرگ‌تر از ۴ ساعت در task نیازمندی به taskهای کوچک‌تر شکسته می‌شوند.

| Milestone | ID | Title | Status | Pri | Level | Est | Deps |
|---|---|---|---|---|---|---|---|
| M6.1 Collections | CAT-13 | Rewrite «کالکشن‌ها» requirements | NOT_STARTED | LOW | HIGH | 2 | — |
| M6.1 Collections | CAT-14 | Collections implementation | NOT_STARTED | LOW | MEDIUM | 5 | CAT-13 · SD rule (test) |
| M6.2 Search | CAT-15 | Rewrite «جست‌وجو» requirements | NOT_STARTED | LOW | HIGH | 2 | — |
| M6.2 Search | CAT-16 | Advanced search implementation | NOT_STARTED | LOW | MEDIUM | 6 | CAT-15 · SD rule (test) |
| M6.3 Wishlist | ACC-03 | Rewrite «علاقه‌مندی‌ها» requirements | NOT_STARTED | LOW | HIGH | 1.5 | — |
| M6.3 Wishlist | ACC-04 | Wishlist implementation | NOT_STARTED | LOW | MEDIUM | 4 | ACC-03 · SD rule (test) |
| M6.4 Returns | ORD-07 | Rewrite «مرجوعی» requirements | NOT_STARTED | LOW | HIGH | 2 | — |
| M6.4 Returns | ORD-08 | Returns (stock only after inspection) | NOT_STARTED | LOW | HIGH | 6 | ORD-07 |
| M6.5 Notifications | CNT-08 | Rewrite «اعلان‌ها» requirements | NOT_STARTED | LOW | HIGH | 2 | — |
| M6.5 Notifications | CNT-09 | Notifications implementation | NOT_STARTED | LOW | MEDIUM | 6 | CNT-08 |

**Phase 6:** 38.5h

---

**Grand total:** 412h (estimate) · MVP (Phase 1–3): 269.5h · COMPLETE: 55.5h
