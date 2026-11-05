---
description: Runs security and quality review in parallel for one Spendly feature, then merges both into a single report
argument-hint: "<spec-name> e.g. 03-login-and-logout"
---

Run the code review pipeline for the feature in `$ARGUMENTS`.

Both reviewers are read-only. This command reports; it changes code only after
you are asked and you explicitly approve.

## Step 0 — Resolve the spec

1. If `$ARGUMENTS` is empty, stop and say:
   "Please provide a spec name. Usage: /code-review-feature <spec-name>
   e.g. /code-review-feature 03-login-and-logout"
2. Resolve the spec file with `find`/`read`: `.pi/specs/$ARGUMENTS.md`, or the
   single match of `.pi/specs/NN-*.md` when `$ARGUMENTS` is a bare step number.
   If it does not exist (or several match), stop, report it, and list what is
   actually in `.pi/specs/`.

## Step 1 — Pre-flight: establish the review scope

1. Run `git status --short`. This is the authoritative scope list.
2. Run `git diff HEAD` for staged and unstaged changes to tracked files.
3. **Untracked files never appear in `git diff`.** Every `??` path is part of
   the change set: list those paths and have both reviewers `read` them.
   In this course most features arrive as new files, so this is the normal
   case, not an edge case.
4. If there are no tracked changes and no untracked source files, stop and
   say: "No changes detected. Implement the feature before running code
   review."
5. Ignore as review targets (they may still be read for context): `.pi/`
   specs and plans, `spendly.db`, `__pycache__/`, `progress.md`, and anything
   gitignored. The review target is app code — `app.py`, `database/`,
   `templates/`, `static/`.

Pass the file list and the spec path to both reviewers, not a pasted diff blob:
each reviewer has read-only `git` and reads the diff itself, which avoids
truncated or stale diff text in the task brief.

## Step 2 — Parallel review

Launch **both** reviewers in the same turn, in parallel, since neither writes
anything:

```js
subagent({ workflow: "parallel", args: { tasks: [
  { agent: "spendly-security-reviewer", task: "..." },
  { agent: "spendly-quality-reviewer",  task: "..." },
] } })
```

Each brief states: the resolved spec path, the scope file list (including
untracked paths), "read `git status --short` and `git diff HEAD` yourself",
and its own lane.

- **spendly-security-reviewer** — SQL injection, authentication, authorization
  (IDOR, session-scoped queries), sensitive data exposure. Must not comment on
  style, naming, or architecture.
- **spendly-quality-reviewer** — file placement, naming, Flask conventions,
  design-token reuse, dead code, maintainability. Must not comment on security.

Both are told to report file:line they actually read, and that stubs are out of
scope. Do not start one before the other, and do not run them serially.

## Step 3 — Unified report

Combine the two outputs into one report.

- **De-duplicate.** If both flagged the same line, keep one entry and note both
  lenses (e.g. `database/queries.py:31` — SQL built with an f-string: injection
  risk *and* the query belongs in the queries module).
- **Keep lanes.** If a reviewer strayed into the other's lane, move that item to
  the correct section instead of dropping it, and say you moved it.
- **Never invent findings** to fill a section. "Nothing found" is a valid result
  and should be stated plainly.
- If either reviewer failed or returned no output, say which one failed and do
  not present the report as complete.

```markdown
Code Review Report — $ARGUMENTS

## Scope
Spec: `.pi/specs/NN-*.md` · Files: [changed + new paths]

## Security findings
[spendly-security-reviewer output, verbatim structure]

## Quality findings
[spendly-quality-reviewer output, verbatim structure]

## Combined action plan
Ordered by what to fix first. Both reviewers are educational, so use their own
buckets rather than inventing verdicts:
1. Security — "Things to learn from" (sql injection, authz, data exposure)
2. Quality — "Worth improving" (placement, naming, Flask conventions)
3. Security — "Nice to have" (XSS hardening, cookie flags, CSRF concept)
4. Quality — "Polish ideas" (PEP 8 nits, token drift, small duplication)
5. Both — "Things worth checking" (items neither could verify)

Each item: file:line, one-line fix, which reviewer raised it.

## Overall verdict
- READY TO COMMIT — no findings worth acting on now
- COMMIT, THEN FOLLOW UP — suggestions only, none blocking
- FIX BEFORE COMMIT — at least one injection, authz, or secret-handling issue
```

Do not treat style nits as blocking, and do not let the educational tone hide a
real injection or authorization hole — those belong at the top of the plan and
under FIX BEFORE COMMIT.

## Step 4 — Ask before changing anything

After presenting the report, ask:

"Do you want me to implement the action plan now?"

Wait for explicit confirmation. Do not touch any file until the user approves.

## Rules

- Do not edit any file before approval.
- Run both reviewers in parallel in one turn; never serially.
- Never skip the pre-flight scope check, and never scope by `git diff` alone.
- Do not proceed if the spec file cannot be resolved — report and stop.
- If either reviewer fails or returns nothing, report it; do not pass off a
  partial review as complete.
- When you do implement, follow `AGENTS.md`: reuse `:root` tokens, no new
  dependencies, `uv run` for commands.
