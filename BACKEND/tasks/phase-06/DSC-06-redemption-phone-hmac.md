# DSC-06 — Redemption phone → HMAC with key rotation

**Status:** COMPLETE · **Priority:** LOW · **Estimate:** 2.5h (estimate) · **Deadline:** — · **Dependencies:** ORD-07 · **Level:** HIGH

## Objective
`discount_redemptions` never stores a raw mobile: only `HMAC-SHA256(phone)` and the key id. Keys come from `Settings` (`PHONE_HMAC_KEYS`), several at once (first writes, all count), so the per-customer limit of a code survives key rotation and account deletion + re-registration (PRD «کد تخفیف» ✓, ADR-063 A2, before ACC-05).

## PRD reference
«کد تخفیف» ✓ (اعتبار: سقف هر کاربر با HMAC موبایل)؛ «پروفایل» ✓ (حذف حساب)؛ ADR-017، ADR-031، ADR-043، ADR-063 A2.

## Acceptance Criteria
- [x] `PHONE_HMAC_KEYS` in `Settings` (`id:secret,...`, newest first, secret ≥ 32, unique ids; validated at startup); required in production; fail closed elsewhere when unset; placeholder in `.env.example`; CI staging env sets one.
- [x] Pure helper `app/core/phone_hmac.py` (parse, digest, digests under all keys) with unit tests.
- [x] Migration `20261126_0035`: `phone` → `phone_hmac` (64 hex, CHECK) + `phone_key_id` (CHECK); existing rows backfilled with the write key; live per-customer index on `(discount_code_id, phone_hmac)`; downgrade restores `phone` from `orders.phone`. Test of backfill and downgrade.
- [x] Redeem writes the write key's digest; usage counts the phone's digest under every key; the same-order retry compares under the row's key. A removed key no longer counts (tested).
- [x] Existing discount tests store prior uses under the older key (rotation exercised everywhere).
- [x] Runbook `docs/ops/PHONE-HMAC-KEYS.md` (format, rotation, migration).
- [x] `test_database` head revision; pytest, ruff, format, mypy green.

## Implementation Notes — plan
Key lookup uses `get_settings()` (cached, process-wide) inside the discount repository and redemption service, so no constructor changes. The digest is unsalted per row by design: it must be equal for equal phones to count.

**Risks**
1. Losing the per-customer limit on rotation → all keys count; test with two keys.
2. Migration on a DB with rows but no key → fails loudly (documented); downgrade path tested.
3. Key leak → digests of Iranian mobiles are brute-forceable with the key (10⁹ space): keep the key secret; rotation procedure.
4. Index/plan regression → index on the digest column, same shape as before.

**Rollback:** `alembic downgrade 20261113_0034` (restores `phone` from orders), then revert the commit.

## Validation
```powershell
python -m pytest -q          # با TEST_DATABASE_URL
python -m ruff check . ; python -m ruff format --check . ; python -m mypy app tests
```

## Log
- 2026-11-26: plan and implementation in one pass (speed mode); REVIEW-CHECKLIST self-check (§ secrets: env only, fail closed; § migration: backfill + downgrade). Opus review on the diff.
- 2026-11-26: opus diff review: no blockers. Fixed: the secret is kept out of `repr` (test); the per-customer index also covers `phone_key_id`; the runbook states that rotation protects new rows only (a leaked key exposes its digests); `get_settings()` as the key source recorded in DECISIONS; tests for the write key on redeem, a retry under the older key and a removed key → 409.
- 2026-11-26: COMPLETE. Full suite ۲۴۳۵ green, then the affected files again after the review fixes (79 green, ۲۴۳۸ in total); ruff, format, mypy green.
