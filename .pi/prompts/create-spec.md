---
description: Create a spec file and feature branch for the next Spendly step
argument-hint: "<step_number> <feature name>"
---

You are a senior developer spinning up a new feature for the Spendly expense
tracker. Always follow the rules in `AGENTS.md`.

This command only creates a branch and a spec document. Do **not** implement
the feature, edit app code, or write templates as part of this command.

User input: `$ARGUMENTS`

## Step 1 — Check the working directory is clean

Run `git status` and look for uncommitted, unstaged, or untracked files. Ignore
the agent config directory `.pi/` — it is intentionally untracked and must not
block this command:

```bash
git status --porcelain -- . ':(exclude).pi'
```

If that prints anything, stop immediately and tell the user to commit or stash
those changes before proceeding. Do not continue until the output is empty.

## Step 2 — Parse the arguments

From `$ARGUMENTS` extract:

1. `step_number` — positive integer, zero-padded to 2 digits: 2 → `02`, 11 → `11`

2. `feature_title` — human-readable title in Title Case
   - Example: "Registration" or "Login and Logout"

3. `feature_slug` — git- and file-safe slug
   - Lowercase kebab-case
   - Only `a-z`, `0-9` and `-`
   - Maximum 40 characters
   - Example: `registration`, `login-logout`

4. `branch_name` — format `feature/<feature_slug>`
   - Example: `feature/registration`

If you cannot infer these from `$ARGUMENTS`, ask the user to clarify before
proceeding.

## Step 3 — Check the branch name is not taken

Check for an existing local branch first:

```bash
git show-ref --verify --quiet refs/heads/<branch_name>
```

If it exists, append a two-digit number: `feature/registration-01`,
`feature/registration-02`, etc., until the name is free.

## Step 4 — Switch to main and pull latest

```bash
git switch main
git pull --ff-only origin main
```

If either command fails (no network, divergent history, etc.), stop and report
the error. Do not continue from a stale or unexpected state.

## Step 5 — Create and switch to the feature branch

```bash
git switch -c <branch_name>
```

## Step 6 — Research the codebase

Read these files before writing the spec:

- `AGENTS.md` — conventions and current route status
- `app.py` — existing routes and structure
- `database/db.py` — existing schema and helpers
- `templates/base.html` — blocks available to new templates
- `static/css/style.css` — design tokens in `:root`
- All files in `.opencode/specs/` — avoid duplicating existing specs

## Step 7 — Write the spec

Generate a spec document with this exact structure:

```markdown
# Spec: <feature_title>

## Overview
One paragraph describing what this feature does and why it exists at this stage
of the Spendly roadmap.

## Depends on
Which previous steps this feature requires to be complete.

## Routes
Every new route needed:
- `METHOD /path` — description — access level (public/logged-in)

If no new routes: state "No new routes".

## Database changes
Any new tables, columns, or constraints needed. Verify against
`database/db.py` first. If none: state "No database changes".

## Templates
- **Create:** new templates with their path
- **Modify:** existing templates and what changes

## Files to change
Every file that will be modified.

## Files to create
Every new file that will be created.

## New dependencies
Any new Python packages, installed with `uv add <package>` (never hand-edit
`requirements.txt`; `pyproject.toml` + `uv.lock` are the source of truth).
If none: state "No new dependencies".

## Rules for implementation
Always include:
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Stub routes outside this step's scope must stay untouched

## Definition of done
A specific, testable checklist. Each item must be verifiable by running the app.
```

## Step 8 — Save the spec

Target path: `.opencode/specs/<step_number>-<feature_slug>.md`

If that file already exists, stop and ask whether to overwrite or pick a new
slug. Do not overwrite an existing spec without confirmation.

## Step 9 — Report to the user

Print a short summary in this exact format:

```text
Branch:    <branch_name>
Spec file: .opencode/specs/<step_number>-<feature_slug>.md
Title:     <feature_title>
```

Then tell the user:

> Review the spec at `.opencode/specs/<step_number>-<feature_slug>.md` and tell
> me when you're ready to begin implementation.

Do not print the full spec in the chat window unless explicitly asked.
