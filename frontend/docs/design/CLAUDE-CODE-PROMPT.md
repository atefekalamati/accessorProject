# Kick-off prompt (paste into Claude Code at repo root)

Place this folder in the repo as `docs/design/` first (see README-FA.md).

```
Frontend phase. Read docs/design/HANDOFF.md, docs/design/design-system/README.md, FRONTEND.md, openapi.json.
Plan first, no code: stack (Next.js App Router + TS, RTL fa), folder layout, routes per HANDOFF §4, typed API client generated from openapi.json, token import from tokens.css, state per §5, test + CI plan. List new deps for approval.
Rules: backend owns pricing; Persian digits at render only; designs = visual spec, openapi = contract (flag conflicts, don't guess); a11y per README; no secrets in client.
Then build in batches: (1) scaffold+tokens+layout+header/footer, (2) home+category+product, (3) OTP login, (4) cart+checkout, (5) orders+missing pages §7. Each batch: tests, lint, typecheck, reviewer pass, PR. Stop at each PR.
```
