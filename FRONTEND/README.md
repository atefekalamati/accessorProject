# Kaléa storefront (FRONTEND)

Next.js (App Router) storefront for the Project AK API. Persian, right-to-left.

Sources, by precedence: `BACKEND/docs/api/versions/openapi-phase-5.json` (frozen contract)
→ `BACKEND/docs/api/FRONTEND.md` → PRD → `docs/design/` (visual spec only; start with
`docs/design/HANDOFF.md`). Backend requests found along the way:
[docs/BACKEND-FOLLOWUPS.md](docs/BACKEND-FOLLOWUPS.md).

## Requirements

Node 24 LTS (`.nvmrc`), npm with the committed lockfile.

## Commands

```sh
npm ci                 # install exactly the locked versions
cp .env.example .env.local   # then set API_ORIGIN
npm run dev            # http://localhost:3000
npm run gen:api        # regenerate src/api/schema.gen.ts from openapi-phase-5.json
npm run check:api      # fail if the generated types drifted from the contract (CI)
npm run lint           # ESLint (incl. jsx-a11y) + Prettier check
npm run typecheck
npm test               # Vitest + Testing Library + MSW (schema-typed)
npm run build          # standalone output
npm run e2e            # Playwright + axe against a mock API (needs `npm run build` first)
```

On Windows, run Vitest from a shell whose working directory uses an upper-case drive letter
(`E:\…`); with `e:\…` Vitest loads two runner instances and every suite fails with
"failed to find the runner".

## Settings (server-only, `.env.example`)

| Variable             | Meaning                                                                             |
| -------------------- | ----------------------------------------------------------------------------------- |
| `API_ORIGIN`         | Backend origin for the `/api/v1/*` proxy and server rendering                       |
| `TRUSTED_PROXY_HOPS` | Trusted proxies in front of this server; 0 forwards no client IP (see OPS-04 notes) |
| `FAKE_GATEWAY_PAGE`  | `1` shows the fake-gateway page (development/staging only)                          |

No `NEXT_PUBLIC_*` variables: nothing configurable reaches the browser.

## How it fits together

- **Same-origin proxy** `src/app/api/v1/[...path]/route.ts` → `src/server/api-proxy.ts`:
  forwards `/api/v1/*` to `API_ORIGIN` with an allowlist of headers, passes every
  `Set-Cookie` back, and replaces `X-Forwarded-For`/`X-Real-IP` with one client IP. The
  refresh and cart cookies stay first-party, so no CORS setup is needed.
- **API types** `src/api/schema.gen.ts` (generated, committed, drift-checked in CI);
  `src/api/client.ts` (browser, openapi-fetch with auth) and `src/api/server.ts` (Server
  Components, public endpoints, no caching).
- **Auth** `src/auth/`: access token in memory only; refresh via the HttpOnly cookie,
  single-flight per tab and across tabs (Web Locks + BroadcastChannel); a non-secret
  `ak_session` hint cookie lets guests skip the refresh call.
- **Formatting** `src/lib/format.ts`: Persian digits, «… تومان», Jalali dates, at render
  only. **Idempotency** `src/lib/idempotency.ts`: one key per user intent.
- **Styling**: tokens imported from `docs/design/design-system/tokens.css` (never retyped),
  CSS Modules, self-hosted fonts via `next/font/local`.

## Docker

```sh
docker build -t kalea-web .                     # standalone image, runs as `node`
docker compose up --build                       # frontend + backend stack (see compose.yaml)
```

`compose.yaml` includes `../BACKEND/docker-compose.yml` unchanged, plus
`compose.backend-proxy.yaml`, which only lets the API trust `X-Forwarded-For` from the
frontend container's fixed address.
