# Runbook — discount redemption phone keys (`PHONE_HMAC_KEYS`)

Discount redemptions never store a mobile number. They store `HMAC-SHA256(phone)` and the
id of the key that made it (DSC-06, ADR-063 A2). The digest is what keeps the "once per
customer" limit of a code, also after the customer deletes the account and registers again.

## Format

```
PHONE_HMAC_KEYS=k2:<secret-32+-chars>,k1:<older-secret>
```

- Entries are `id:secret`, newest first. The id is 1–16 chars `[a-z0-9_-]` and starts with
  a letter or digit; every secret is at least 32 characters.
- The **first** key writes new redemptions. **Every** key is used to count earlier ones.
- Required in production (startup fails without it). Elsewhere a missing value makes any
  signed-in code check (cart apply, checkout, order) fail with 500 (fail closed, like
  `OTP_HASH_SECRET`).
- Keep it only in the secret store / `.env` (never in git). Treat it like `JWT_SECRET`.

Generate a secret: `openssl rand -hex 32`.

## Rotate a key

Rotation protects **new** redemptions only. With a leaked key, the digests it already made
can be brute-forced back to mobile numbers (the Iranian mobile space is about 10⁹), and the
raw numbers needed to re-hash them may no longer exist (accounts deleted, ACC-05). So keep
the key in the secret store only, and treat a leak as a personal-data incident.

1. Generate a new secret and put it **first**, keeping the old key after it:
   `PHONE_HMAC_KEYS=k3:<new>,k2:<old>`.
2. Deploy and restart. New redemptions use `k3`; limits still count the `k2` rows.
3. Leave `k2` in the list as long as codes with a per-customer limit are still active
   (or until their `ends_at`). Removing it makes the uses it recorded stop counting toward
   "once per customer" (total limits are not affected).
4. Optional, after removing `k2`: nothing else to do. Rows keep `phone_key_id = 'k2'` and
   simply no longer match anyone.

Never reorder keys (the first one is the write key) and never reuse an id for a different
secret: rows with that id would stop matching.

## Migration `20261126_0035`

Upgrading a database that already has redemptions hashes them with the write key, so
`PHONE_HMAC_KEYS` must be set before `alembic upgrade head`. Downgrade restores `phone`
from each order's snapshot (`orders.phone`); an anonymized order (ACC-05) gets the
placeholder `+989000000000`.
