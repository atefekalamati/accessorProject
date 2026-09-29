# PR: Phase 1 — Foundation

**Title:** `feat: Phase 1 foundation — shared infrastructure, test DB, CI, audit`

**Base:** `master` ← **Head:** `feat/m1.1-repo-foundation` (19 commits, 69 files, +3620 / −129)

---

## Summary

Completes Phase 1 (Foundation): M1.1 Repo foundation and M1.2 Shared infrastructure.
There is no shop logic yet. This PR adds the building blocks that Phase 2 (Auth & RBAC,
Catalog, Inventory, Pricing) depends on.

### Infrastructure & tooling
- **FND-03:** Docker/Compose runs end to end. Host ports come from `DB_HOST_PORT` /
  `API_HOST_PORT`, and the pip build is hardened.
- **FND-06:** `postgres-test` compose profile (disposable, no volume). The test session
  aborts (exit 3) unless the `TEST_DATABASE_URL` database name ends with `_test`.
- **FND-07:** GitHub Actions CI runs pytest (with PostgreSQL), ruff check, ruff format
  --check and mypy strict.

### Shared infrastructure
- **INF-01:** error code catalog and typed `AppError` subclasses. Validation errors map to
  400 and business-rule violations to 422 (ADR-011).
- **INF-02:** integer-Toman money utilities with a single rounding function (ADR-001, ADR-014).
- **INF-03:** page/limit pagination, plus sort and query-parameter allowlists.
- **INF-04:** soft-delete mixin and the `not_deleted` filter helper (ADR-015, SD rule).
- **INF-06:** `app/core/redaction.py`. Secrets (token, secret, password, OTP, hash,
  cookie, Bearer/JWT) are redacted from JSON logs, and Iranian mobile numbers are masked.
  Persian and Arabic digits are handled too.
- **INF-05:** `app/shared/audit.py`. `record_audit()` writes an `AuditLog` row inside the
  caller's transaction; it flushes but never commits, so a rollback also removes the
  audit row. `metadata` holds:
  - `actor`: `"system"` when there is no user
  - `request_id`
  - a redacted field-level `diff`

  The action name must follow the `<entity>.<verb>` format.

### Planning & docs
- Planning system under `docs/project/` (ROADMAP, PLAN, PROGRESS, DECISIONS, WORKFLOW)
  and one file per task under `tasks/`.
- Open decisions resolved as ADR-003 to ADR-015. PRD sections updated; see the
  "PRD changes" table in DECISIONS.md.
- Plan additions:
  - **SEC-04:** DB-level append-only `audit_logs`, meaning a trigger that blocks UPDATE.
    A DELETE-blocking trigger already exists.
  - **OPS-04:** new trusted-proxy criterion.

## Notable changes for reviewers
- `"hash"` was added to the shared `SENSITIVE_KEY_PARTS`. Keys such as `code_hash` are now
  redacted in both logs and audit metadata.
- The PostgreSQL test fixtures (`database_url`, `migrated_database`, `db_engine`,
  `db_session`) moved from `tests/test_database.py` to `tests/conftest.py`.
- No new migration. The schema is unchanged since `20260913_0001`.
- No new dependencies.

## Validation
- `pytest`: **345 passed, 0 skipped**, run locally against `postgres-test`
  (`project_ak_test`).
- `ruff check`, `ruff format --check` and `mypy app tests` (strict) are all green.
- **CI:** the workflow was green when FND-07 was completed (commit `8792b7f`). Check the
  run for the head commit `579bd75` in the Checks tab before merging. I could not read CI
  status because the repository is private and `gh` is not installed.

## Not in this PR
- Any shop features, such as auth, catalog, inventory, cart, orders or payments. These
  start in Phase 2 on `feat/phase-2-core-domain`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
