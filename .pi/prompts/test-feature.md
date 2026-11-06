---
description: Writes tests for a Spendly spec, then runs them via subagents
argument-hint: "<spec-name> e.g. 05-backend-routes-for-profile-page"
---

Run the two-subagent testing pipeline for the feature named in `$ARGUMENTS`.

This command writes tests and runs them. It never changes application code.

## Step 0 — Resolve and validate (before any subagent starts)

1. If `$ARGUMENTS` is empty, stop immediately and say:
   "Please provide a spec name. Usage: /test-feature <spec-name>
   e.g. /test-feature 05-backend-routes-for-profile-page"
2. Resolve the spec file with `find`/`read`:
   - `.pi/specs/$ARGUMENTS.md` when it exists, or
   - if `$ARGUMENTS` is a bare step number such as `05`, the single match of
     `.pi/specs/05-*.md`.
   - If there are zero or several matches, stop and list what is in `.pi/specs/`
     instead of guessing.
3. Read the spec and check its step against the implemented-vs-stub table in
   `AGENTS.md`. If the routes it targets are still step stubs, stop and say
   implementation must land before tests can be written.
4. Derive the test file path from the spec filename: strip the leading `NN-`
   and replace dashes with underscores, e.g.
   `05-backend-routes-for-profile-page.md` →
   `tests/test_backend_routes_for_profile_page.py`.
   Use that concrete path in both subagent tasks; never pass a raw
   `$ARGUMENTS` into a filename.

## Step 1 — Write tests (spendly-test-writer)

Launch the **spendly-test-writer** subagent with a short brief that states:

- Goal: write pytest tests for this spec.
- Spec: the resolved `.pi/specs/NN-*.md` path (the contract).
- Output: the concrete `tests/test_<topic>.py` path from Step 0.
- Structure reference only (API surface — module paths, route paths, helper
  names): `app.py`, `database/`, and the existing `tests/conftest.py` fixtures
  (`temp_db`, `app`, `client`, `demo_user_id`, `blank_user_id`).
- Rule: derive expectations from the spec, not from the implementation; cover
  happy paths, edge/empty cases, auth guards, validation errors, ownership
  isolation, and DB side effects.
- Limits: write only under `tests/`; if you run anything, it must be exactly one
  `uv run pytest <the target file> -q`. Never the full suite, never bare
  `pytest`, never `pip install`, never start the dev server — Step 2 owns the
  authoritative run.
- Stop condition: report instead of writing when the spec is ambiguous or the
  implementation diverges from it.

Launch it **blocking**: `subagent({ agent: "spendly-test-writer", task: "...",
async: false })`. Subagent launches are async by default, so do not leave it in
the background, do not put it in a parallel workflow, and do not launch the
runner in the same message.

Wait for the writer to finish, then confirm the test file exists. If the writer
reported anything other than success — no file written, stub routes, blocking
ambiguity — stop and report the reason. Do not proceed to Step 2.

## Step 2 — Run tests (spendly-test-runner)

Only after Step 1 succeeded, launch the **spendly-test-runner** subagent,
blocking, with:

- Test file: the concrete `tests/test_<topic>.py` path.
- Spec: the same spec path, for context.
- Diagnosis references: `app.py`, `database/db.py`, `database/queries.py`.
- Run command: `uv run pytest tests/test_<topic>.py -v`.
- Instruction: run only that file, never the full suite; classify each failure
  as an implementation bug, a spec divergence, or a missing feature.

## Handoff rules

- Do not start Step 2 until Step 1 is fully complete.
- Do not fix any application code, regardless of results; report instead.
- Do not run tests beyond the target file, and never bare `pytest`,
  `python -m pytest`, or `pip install` — this project runs through `uv run`.
  Only Step 2's runner performs the authoritative run; if the writer ran the
  full suite, note it as a process violation in the final report.
- If the writer could not write the test file, stop and report the reason.

## Final output

After both subagents complete, produce one combined summary:

### Testing Pipeline Report — $ARGUMENTS

**Step 1 — Tests written**
- Test file: `tests/test_<topic>.py`
- Each test with a one-line note on which spec requirement it validates

**Step 2 — Test results**
- The runner's structured report, with failures quoted verbatim

**Verdict**
One of:
- ✅ Ready for code review — all tests pass
- ❌ Needs fixes — failing tests plus root causes
