# ACC-06 — Deletion OTP (`purpose`) + endpoints

**Status:** COMPLETE · **Priority:** LOW · **Estimate:** 2h (estimate) · **Deadline:** — · **Dependencies:** ACC-05 · **Level:** HIGH

## Objective
The customer deletes their account with a code sent to their own mobile: `POST /users/me/deletion/request-otp`, then `POST /users/me/deletion` `{code}` → 204 and the refresh cookie cleared. A login code never deletes and a deletion code never signs in (PRD «پروفایل» ✓, D37, ADR-063).

## PRD reference
«پروفایل» ✓ (حذف حساب)؛ «هویت و دسترسی» ✓ (OTP)؛ ADR-012، ADR-016، ADR-063.

## Acceptance Criteria
- [x] Migration `20261126_0037`: `otp_codes.purpose` (`login` default, `account_delete`; CHECK). Login lookups and request-otp expiry are per purpose; the limits (cooldown, per mobile, per IP, global) count every purpose together.
- [x] `POST /users/me/deletion/request-otp` (signed in): preconditions first (409 `ACCOUNT_HAS_ACTIVE_ORDERS`, 422 `STAFF_ACCOUNT`, no code sent), then a code to the account's own mobile; 429 as at login; no-store.
- [x] `POST /users/me/deletion` `{code}` (`extra="forbid"`): preconditions, then the newest open `account_delete` code (same attempt counting and expiry as login, wrong code → 401 `OTP_INVALID` with the attempt committed), then ACC-05 anonymization, all in one transaction → 204, refresh cookie cleared (same attributes as set), no-store.
- [x] Tests: success (old access and refresh → 401), login code refused for deletion and deletion code refused for login, wrong/expired codes, refusals send no code and consume none, 401 without auth, 429 cooldown; pytest, ruff, format, mypy green; OpenAPI regenerated; FRONTEND.md.

## Implementation Notes — plan
- `OtpPurpose` enum on the model; `OtpRepository.expire_active/lock_latest_unconsumed` take a purpose (default login); `OtpService.request_otp(..., purpose)`.
- `AccountDeletionService.precheck` (read the preconditions, no write) and `confirm` (OTP advisory lock of the mobile → carts → orders → user, as login and request-otp take the same advisory lock first).

**Risks**
1. Cross-use of codes → purpose filter on every lookup; tests both ways.
2. Losing the attempt counter on 401 → the transaction commits before the error (as login).
3. Deletion code burned by a refused deletion → preconditions run before the OTP check.
4. Cookie left in the browser → same name/path/flags as set.

**Rollback:** `alembic downgrade 20261126_0036` (drops open deletion codes and the column), then revert the commit.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-26: plan and implementation (speed mode); REVIEW-CHECKLIST self-check (§ auth: purpose-bound, single use, attempts, rate limit; § cookies). Opus review on the diff. Note: the 60 s resend cooldown is shared with the login code, so a deletion code can be requested at the earliest one minute after signing in (accepted: same limits as login, PRD).
- 2026-11-27: opus diff review: no blockers. Fixed: FRONTEND.md tells the client not to refresh/retry on 401 `OTP_INVALID` (it would burn attempts), that a repeat after 204 is 404 and that the shared cooldown needs a countdown; tests for attempt exhaustion, a concurrent double confirm (one 204, one `user.deleted` audit) and every cookie attribute; comment on the unlocked mobile read.
- 2026-11-27: found while testing, not part of ACC-06: the downgrade of the committed migration `0036` (ACC-05) gives every deleted account the same placeholder phone, so a downgrade past `0002` fails once there are 2+ deleted accounts (older revisions have a non-partial unique phone). Editing a committed migration needs the user's OK (CLAUDE.md §۹): the fix is kept as a patch and asked (PROGRESS Blockers).
- 2026-11-27: COMPLETE. Full suite ۲۴۶۲ green; ruff, format, mypy green; OpenAPI regenerated.
