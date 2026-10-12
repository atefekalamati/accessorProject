Phase mode (rules also in CLAUDE.md section 11, "Phase mode"). Same rules as /batch (`.claude/commands/batch.md`), chained until the phase is done.

1. Read Current/Next in docs/project/PROGRESS.md and the current phase in docs/project/PLAN.md. Report the status header.
2. Loop over batches in the order PROGRESS.md "Next Action" gives:
   a. Propose and run one batch exactly as /batch steps 1–5 (plan, AUTOPILOT exceptions, REVIEW-CHECKLIST + independent reviewer subagent for HIGH plans and final diffs, pytest/ruff/mypy, task file + PROGRESS.md, Conventional Commit, push, CI watched green).
   b. PAY-* tasks and inventory reservation/commit/release tasks still run alone, one per batch, and their plans stop for the user.
   c. After each batch with CI green, start the next one without waiting.
3. Stop and report immediately on any /batch stop condition (unclear test failure, open decision or PRD ambiguity, work outside the plan, unplanned schema/migration change, red CI) or an AUTOPILOT exception.
4. Session cap: 4 batches. Then one report (status header, one line per task, totals, next step, CI result) and say "ready for /clear"; the user runs /clear + /phase.
5. Phase gate, automatically when every task of the phase is COMPLETE (ADR-037):
   a. Open a PR from the phase branch to `master` with `gh pr create` (gh at `C:\Program Files\GitHub CLI\gh.exe`). Body: tasks done, ADRs, PRD changes, migrations, test count; end with the PR attribution line.
   b. Watch the PR CI, including the ephemeral staging smoke job (OPS-08). Red = stop and report.
   c. Stop and ask the user to merge. Never merge yourself.
   d. After the user merges: confirm the CD job (OPS-09) pushed the image to GHCR with tags `<sha>` and `phase-N`; create and push git tag `phase-N` on the merge commit.
   e. Create the next phase branch from `master` (`feat/phase-<N+1>-<name>`), update PROGRESS.md, push, continue.
