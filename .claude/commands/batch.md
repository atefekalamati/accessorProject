Batch mode (rules also in CLAUDE.md section 11, "Batch mode").

1. Propose: read Current/Next in docs/project/PROGRESS.md and the current milestone in docs/project/PLAN.md. Pick the next 3–5 related, unblocked tasks (total estimate ≤ ~8h if any task is HIGH; ≤ ~12h otherwise, approved directly with "ok"). Never include PAY-* tasks or inventory reservation/commit/release tasks. Those always run one task per session.
2. Write ONE combined plan covering files, order and tests. For each HIGH-level task, add its risks, rollback steps and extra tests. Report the status header, then wait for approval.
3. After approval, for each task in order:
   a. Implement only what the approved plan covers.
   b. Run `pytest -q` with TEST_DATABASE_URL, then `ruff check .`, `ruff format --check .` and `mypy app tests`, all quietly.
   c. Self-review the diff against the task's acceptance criteria and the CLAUDE.md rules.
   d. Update the task file (criteria, status, Log) and PROGRESS.md, including percentages.
   e. Commit (Conventional Commits) and `git push`, never force.
   f. Continue to the next task without waiting.
4. Stop immediately and report if any of these happen:
   - a test fails and the cause is unclear
   - an open decision or PRD ambiguity appears
   - work outside the approved plan is needed
   - an unplanned schema or migration change is needed
5. End with ONE report:
   - the status header
   - one line per task: ID, status, commit, tests
   - totals
   - the next batch proposal
   - a request that the user verify CI
