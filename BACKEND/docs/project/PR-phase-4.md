## Phase 4 — Account & admin

All Phase 4 tasks are COMPLETE (ADR-037 phase gate). Customers can see their own orders; staff get the admin panel (orders, shipments, refunds, customers, audit log, dashboard, reports); the store front is now content-managed (home page sections, banners, static pages, FAQ, contact form).

### Tasks done (27)
- **M4.1 Customer account:** ACC-00 (requirements), ACC-01 (own orders list and detail, `can_pay` / `can_cancel`), ACC-02 (ownership and IDOR tests), CAT-18 (colour swatches with hex and `is_new` on product cards, D42).
- **M4.2 Admin panel:** ADM-00 (requirements), ADM-01 (order and payment lists with filters), ADM-02 (shipment moves with tracking code, staff cancel of unpaid orders), ADM-03 (customers, masked mobile in lists, audited full view), ADM-04 (dashboard by Tehran day), ADM-05 (sales reports by day, Saturday week and Jalali month), ADM-06 (audit log viewer, super_admin only), ADM-07 (5 roles × every admin route), ADM-08 (manual refund record `refund_required → refunded`).
- **M4.3 Content & home page:** CNT-00 (requirements), CNT-01 (`GET /home` from ordered, scheduled sections), CNT-02 (admin home sections), CNT-03 (scheduled banners in hero sections), CNT-04 (static pages), CNT-05 (FAQ), CNT-06 (rate-limited contact form and its admin queue), CNT-07 (public/admin split end to end).

### ADRs
ADR-053 to ADR-057 (`docs/project/DECISIONS.md`):
- ADR-053: Phase 4 requirements (D35–D42).
- ADR-054: manual refund amount and source.
- ADR-055: Tehran time boundaries and the Jalali calendar for the dashboard and reports.
- ADR-056: static pages, FAQ and contact form choices.
- ADR-057: CI speed-ups (uv install from the hashed lock, Docker layer cache, `paths-ignore` for frontend and Markdown pushes). The full suite and staging smoke still run on every push.

### PRD changes
2026-10-26 (ACC-00, ADM-00, CNT-00): eleven templated sections rewritten and marked ✓ («پروفایل», «سفارش‌ها», «داشبورد», «مشتریان», «گزارش‌ها», «گزارش ممیزی», «محتوا و بنرها», «درباره برند», «تماس با ما», «سؤالات متداول», «قوانین و حریم خصوصی»). «مدیریت سفارش» ✓ and «صفحه اصلی» ✓ were completed (manual refund, shipment, narrower home scope). The product card in «دسته‌بندی محصولات» ✓ gained colour swatches and `is_new`. Approved by the user (D35–D42).

### Migrations
`20261026_0025` to `20261111_0032` (8). Each has a downgrade, and the test session runs a full down/up/down/up cycle.
- `0025`: hex colour on variant options.
- `0026`: shipments.
- `0027`: payment refunds. Its downgrade refuses while refunded payments exist.
- `0028`: static pages.
- `0029`: FAQ items.
- `0030`: contact messages.
- `0031`: home sections and items.
- `0032`: banners.

Downgrading `0028`..`0032` drops content tables and their data.

### Tests
- 2247 passed locally, with integration tests on PostgreSQL 16 and none skipped.
- CI is green on the head commit of this branch. The ephemeral staging smoke ran on an empty database (migrate, seed, login, admin write, purchase end to end).
- ruff, ruff format and mypy strict are green.

### Release notes — deploying this phase
1. `alembic upgrade head`, which applies `0025`..`0032`.
2. **Re-run the seed: `python -m app.db.seed`.** It adds two permissions and new role grants. The seed is idempotent and never revokes a grant.
   - `payments:refund`: admin and super_admin.
   - `contact_messages:manage`: support, admin and super_admin.

   Until the seed runs, those staff get 403 on `POST /admin/payments/{id}/refund` and `/admin/contact-messages`.
3. Optional new settings, with their defaults in `.env.example`:
   - `PRODUCT_NEW_DAYS=30`
   - `CONTACT_WINDOW_SECONDS=3600`
   - `CONTACT_MAX_PER_IP=5`
   - `CONTACT_MAX_PER_PHONE=3`
4. New public endpoints for the frontend (`docs/api/openapi.json` is current):
   - `GET /home`
   - `GET /pages/{slug}`
   - `GET /faq`
   - `POST /contact`
   - `GET /orders` and `GET /orders/{id}`
5. Behind a reverse proxy, the per-IP limits (contact form, discount codes, payment callback) see one shared IP until OPS-04 (trusted proxy, D13) is done.

### After merge (phase gate)
- CD job `publish-image` pushes `ghcr.io/atefekalamati/accessorproject-api:<sha>` and `:phase-4`.
- git tag `phase-4` on the merge commit, then the `feat/phase-5-release` branch.

### Known follow-ups
- PAY-07: real payment gateway (blocked on D8).
- OPS-05: real SMS provider (blocked on D9).
- OPS-07: real file storage (blocked on D10).
- OPS-04: trusted proxy and production config (blocked on D13).
- M6: collections, wishlist, search, returns and notifications (deferred by D36 and D35).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
