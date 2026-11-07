---
description: Commit, push, create PR, merge, and clean up after a feature is complete
argument-hint: "[spec-name] e.g. 08-edit-expense"
---

Ship the current feature branch end to end: pre-flight, commit, push, PR,
squash merge, branch cleanup. Follow the rules in `AGENTS.md`.

Optional spec name is `$ARGUMENTS` (no `.md`), e.g. `08-edit-expense`. When it is
empty, resolve the spec from the branch name in Step 1.

The squash merge and the branch deletions below are destructive by design.
Running this command is the user's explicit authorization for them — do not ask
for confirmation again.

## Step 0 — Pre-flight (stop on any failure)

1. Run `git branch --show-current` and write the result down as the feature
   branch. Every command below uses `<branch>` for that literal name; do **not**
   re-read it after Step 9 switches to `main`.
   If it is empty (detached HEAD) or `main`/`master`, stop and say:
   "Refusing to ship from `<branch>`. Switch to a feature branch first."
2. Run `git status --short`. This is the authoritative change set — `git diff`
   never lists untracked files, and new templates/tests are the normal case in
   this repo.
3. Run `uv run pytest`. Every test must pass. On failure, stop and report the
   failures; never commit or merge a red suite.
4. Connect the GitHub MCP server with `mcp({ connect: "github" })`. If it does
   not connect or is unauthenticated, stop and say:
   "GitHub MCP is not connected. Run /mcp to check connection."

## Step 1 — Resolve context

- `git remote get-url origin` → parse `owner` and `repo` from the GitHub URL
  (both `https://github.com/OWNER/REPO.git` and `git@github.com:OWNER/REPO.git`
  forms).
- Base branch is `main`. Run `git fetch origin main` so `origin/main` is current.
- Spec: when `$ARGUMENTS` is set, use `.pi/specs/$ARGUMENTS.md` (or the single
  `NN-*.md` match when it is a bare step number). Otherwise map
  `feature/<slug>` → `.pi/specs/NN-<slug>.md`. If zero or several specs match,
  list `.pi/specs/` and stop — the PR body needs the spec's overview and
  definition of done. Never invent spec content.

## Step 2 — Generate commit message

Read the whole change set, not just `git diff`:

```bash
git status --short
git diff HEAD
git log origin/main..HEAD --oneline
```

Also `read` every untracked (`??`) path; otherwise new files contribute nothing
to the message.

Generate a Conventional Commit message:

- `feat:` new feature
- `fix:` bug fix
- `chore:` config or tooling
- `docs:` documentation only

Rules:
- Lowercase
- No period at the end
- Under 72 characters
- Describes what the user can now do, not what the code does

Good: "feat: add delete expense button with confirmation dialog"
Bad: "feat: added DELETE route to app.py"

## Step 3 — Commit

If `git status --porcelain` is empty there is nothing to commit — skip to Step 4
and report "✓ Nothing to commit — using existing commits".

```bash
git add -A
git commit -m "<generated-message>"
```

`git add -A` also stages the `.pi/specs/` and `.pi/plans/` docs for this
feature — expected, not a mistake.

Report: "✓ Committed — <generated-message>"

## Step 4 — Push to feature branch

```bash
git push -u origin <branch>
```

If the push fails for any reason other than "no upstream configured", stop and
report the error.

Report: "✓ Pushed — <branch>"

## Step 5 — Create PR via GitHub MCP

Call `github_create_pull_request` with:

- `owner` / `repo` from Step 1
- `head`: `<branch>`
- `base`: `main`
- `title`: plain English feature name, no conventional commit prefix.
  Example: "Add delete expense functionality"
- `body`:

```markdown
## What this PR does
<one paragraph from the spec's Overview section>

## Changes
<one bullet per file from `git diff --name-only origin/main...HEAD`,
one line description each>

## Definition of done
<copy the definition of done checklist from the spec; mark [x] only items you
actually verified in this run — the green `uv run pytest` plus any smoke steps
you performed. Leave everything else [ ] rather than claiming it>

## How to test
1. Run `uv run python app.py` (dev server is on port 5001)
2. Log in as demo@spendly.com / demo123
3. <specific steps from the spec to verify this feature works>
```

Capture `pull_number` from the response — Step 6 merges by number, not URL.

Report: "✓ PR created — <PR URL>"

## Step 6 — Merge PR via GitHub MCP

1. Call `github_get_pull_request_status`. If any status check is failing, stop
   and report it; do not merge.
2. Call `github_merge_pull_request` with `owner`, `repo`, `pull_number` and
   `merge_method: "squash"` (the default is `merge`).

Report: "✓ PR merged to main"

## Step 7 — Verify the merge

Call `github_get_pull_request` and confirm `merged` is true. If it is not, stop
immediately: never delete branches for an unmerged PR.

Report: "✓ Merge verified"

## Step 8 — Delete remote branch

The GitHub MCP server has no delete-branch tool, so use git:

```bash
git push origin --delete <branch>
```

A "remote ref does not exist" error is success here — GitHub may already have
deleted the branch via its auto-delete setting.

Report: "✓ Remote branch deleted"

## Step 9 — Switch to main and pull

```bash
git switch main && git pull --ff-only origin main
```

Report: "✓ Switched to main — up to date"

## Step 10 — Delete local feature branch

A squash merge leaves the branch's commits out of `main`, so `git branch -d`
refuses by design. Use `-D` now that Step 7 verified the merge:

```bash
git branch -D <branch>
```

Report: "✓ Local branch deleted"

## Final summary

Print:
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
/ship-feature complete
✓ Committed — <message>
✓ Pushed — <branch>
✓ PR created and merged
✓ Remote branch deleted
✓ Switched to main
✓ Local branch deleted
Next: run /create-spec for the next feature
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌

## Rules

- Never commit or push directly to `main`; stop on `main`, `master`, or a
  detached HEAD
- Always squash merge (`merge_method: "squash"`)
- Delete both branches only after the PR reports `merged: true`
- Never proceed to merge if PR creation failed or a status check is failing
- `uv run pytest` must pass before committing; never check a DoD item that was
  not actually verified
- If push fails due to no upstream, use `git push -u origin <branch>`
- If GitHub MCP is not connected stop and say:
  "GitHub MCP is not connected. Run /mcp to check connection."
