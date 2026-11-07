# Spec: Edit Expense

## Overview
Step 8 lets a logged-in user edit any of their own expenses via a pre-populated
form at `/expenses/<id>/edit`. The GET handler loads the existing expense and
renders the form with its current values; the POST handler validates the
submission and updates the row in place. Ownership is enforced in SQL: a user
can only read or write expenses that belong to them, and a missing or
foreign-owned id returns **404** (not 403 — that would leak which ids exist).

Two helpers are added to `database/queries.py`: `get_expense_by_id` and
`update_expense`. The transactions table in `profile.html` gains an "Edit"
action link per row, which requires `get_recent_transactions` to also return
the expense `id` — a change that also touches an existing Step 5 test.

## Depends on
- Step 1: Database setup (`expenses` table exists with all required columns)
- Step 3: Login / Logout (`session["user_id"]` is set and enforced)
- Step 5: Profile page renders transactions (the edit link lives there)
- Step 7: Add Expense (establishes the validation + form pattern this step
  mirrors one-for-one)

Step 6 (date filter) is **not** a dependency: like Step 7, the success redirect
goes to a bare `/profile`, so an edited expense is always visible afterwards
(see "Out of scope" for the consequence).

## Routes
One view function, `edit_expense`, with `methods=["GET", "POST"]`:

- `GET /expenses/<int:id>/edit` — render the form pre-populated with the stored
  values — logged-in only
- `POST /expenses/<int:id>/edit` — validate and save — logged-in only

Auth guard (both methods, first lines of the view, mirroring `/expenses/add`):

```python
if session.get("user_id") is None:
    return redirect(url_for("login"))

if get_user_by_id(session["user_id"]) is None:
    # Stale session for a user that no longer exists.
    session.clear()
    flash("Please sign in again.", "error")
    return redirect(url_for("login"))
```

Order inside the view matters — do not reorder:

1. Auth + stale-session guard
2. `get_expense_by_id(id, session["user_id"])`; if `None` → `abort(404)`
3. GET → render; POST → validate → `update_expense(...)` → redirect

Fetching **before** validating means a POST to another user's expense is a 404
rather than a validation round-trip, and it avoids echoing someone else's data
back into a form.

No `next`/return-to parameter and no flash on the guard — keep parity with
`/profile` and `/expenses/add`. No custom 404 page exists in this project, so
`abort(404)` (import `abort` from `flask`) returning Flask's default error body
is correct for this step.

## Database changes
No new tables or columns. All required columns already exist in `expenses`:
`id`, `user_id`, `amount`, `category`, `date`, `description`, `created_at`.
There is no `updated_at` column and this step does not add one, so an edit does
not record a modification timestamp.

## Query helpers
Add to `database/queries.py` (no Flask imports; each opens and closes its own
connection):

```python
def get_expense_by_id(expense_id, user_id):
    """One expense as a dict, or None if missing or not owned by `user_id`."""

def update_expense(expense_id, user_id, amount, category, date, description=None):
    """Update one owned expense; return the number of rows changed (0 or 1)."""
```

- **`get_expense_by_id`** — `SELECT id, amount, category, date, description
  FROM expenses WHERE id = ? AND user_id = ?`; return a **plain dict** with
  exactly those five keys (matching `get_user_by_id`'s return style, not a raw
  `sqlite3.Row`), or `None`. The `user_id = ?` predicate is the ownership guard:
  a foreign-owned row is indistinguishable from a missing row.
- **`update_expense`** — a single parameterised
  `UPDATE expenses SET amount = ?, category = ?, date = ?, description = ?
  WHERE id = ? AND user_id = ?`, wrapped in `with conn:` (commit on success,
  rollback on error), connection closed in `finally`. Return
  `cursor.rowcount`. The second `user_id = ?` guard means a race (row deleted
  between GET and POST, or a forged id) affects zero rows instead of writing.
- **`get_recent_transactions`** — add `id` to the `SELECT` list and to the
  dict comprehension's keys. Nothing else about the query changes (`ORDER BY
  date DESC, id DESC`, `limit` parameter, date bounds all stay).
- **Module docstring** — it currently says `insert_expense()` is "the single
  write path". Update it to name both write helpers
  (`insert_expense`, `update_expense`).

## Validation (POST)
Identical to Step 7 — compute one `error` string (first failing rule wins) and
either re-render or update. Do not flash validation errors; flash is reserved
for the success message.

Submitted values are read with `request.form.get(..., "")` and used for the
re-render so the form stays sticky.

| Field | Rule | Error message |
|---|---|---|
| `amount` | strip; `round(float(value), 2)` (catch `ValueError`); must be `math.isfinite` and `> 0` | `Please enter an amount greater than 0.` |
| `category` | must be in `CATEGORIES` from `database.db` | `Please choose a valid category.` |
| `date` | strip; `datetime.strptime(value, "%Y-%m-%d").date().isoformat()` | `Please enter a valid date (YYYY-MM-DD).` |
| `description` | strip; blank → `None`; `len > 200` rejected | `Description must be 200 characters or fewer.` |

The draft was missing the description length rule (it exists in Step 7 and in
`add_expense.html`'s `maxlength="200"`). Also keep the non-finite and rounding
guards: `float("nan")` / `float("1e999")` parse without raising, and the stored
`REAL` must match the input's `step="0.01"`. Date normalisation is required for
the same reason as Step 7: SQLite compares the TEXT `date` column
lexicographically, so `2026-3-5` must be stored as `2026-03-05`.

Reuse `_parse_iso_date` from `app.py` for the date. **Recommended DRY refactor:**
extract the existing validation block out of `add_expense` into a module-level
helper returning `(form, error)`, e.g.

```python
def _parse_expense_form(form_data):
    """(normalised field dict, error-or-None) shared by add and edit."""
```

and call it from both views. This is the only intended change to Step 7 code;
its behaviour, status codes, and error strings must not change, and
`tests/test_add_expense.py` must stay green. If you skip it, copy the rules
exactly — do not "improve" them per route.

Failure response: `render_template("edit_expense.html", ..., error=error), 400`
— 400, matching `register`/`login`/`add_expense` (the draft said 200; that
contradicts the codebase and `AGENTS.md`).

Success response: `flash("Expense updated.", "success")` then
`redirect(url_for("profile"))` — never render the form again after a write.

If `update_expense` returns `0` (row vanished or was never owned), `abort(404)`
rather than reporting success.

## Templates

- **Create**: `templates/edit_expense.html`
  - Extends `base.html`; `{% block title %}Edit expense — Spendly{% endblock %}`
  - Reuses the centred auth layout exactly like `add_expense.html`
    (`.auth-section` / `.auth-container` / `.auth-header` / `.auth-title` /
    `.auth-subtitle` / `.auth-card` / `.auth-switch`). No new styles needed.
  - `{% if error %}<div class="auth-error" role="alert">{{ error }}</div>{% endif %}`
  - `<form method="POST" action="{{ url_for('edit_expense', id=expense_id) }}">`
    — use `url_for`, not a hand-written URL (the draft hardcoded
    `/expenses/{{ expense.id }}/edit`)
  - Same four `.form-group` + `.form-input` fields as `add_expense.html`, with
    the same attributes and the same variable names (`amount`, `category`,
    `date`, `description`) so the view can pass `**form`:
    - `amount` — `type="number"`, `step="0.01"`, `min="0.01"`,
      `inputmode="decimal"`, `required autofocus`, `value="{{ amount or '' }}"`
    - `category` — `<select name="category" class="form-input" required>`
      looping `categories` (`CATEGORIES` from the route); exactly one option
      carries `selected` when `option == category`; no placeholder option
    - `date` — `type="date"`, `required`, `value="{{ date or '' }}"`
    - `description` — `type="text"`, `maxlength="200"` (optional, no
      `required`), `value="{{ description or '' }}"`
  - Submit: `<button type="submit" class="btn-submit">Save Changes</button>`
  - Cancel: `.auth-switch` paragraph link ("Cancel and go back") to
    `url_for('profile')`, same as Step 7 — no `.btn-ghost` button

- **Modify**: `templates/profile.html` — transactions table
  - Add `<th scope="col" class="tx-actions">Actions</th>` as the **last**
    header cell (Date, Description, Category, Amount, Actions)
  - Add `<td class="tx-actions"><a href="{{ url_for('edit_expense',
    id=t.id) }}">Edit</a></td>` as the last cell of each row
  - **Update the empty-state row** from `colspan="4"` to `colspan="5"` — the
    draft missed this, and without it the "No transactions in this range."
    cell will not span the table
  - Keep `t` as the loop variable (the template already uses `t`, not `tx`)

- **Modify**: `static/css/style.css`
  - One new rule next to `.tx-amount`, built only from existing tokens:
    `.tx-table th.tx-actions, .tx-table td.tx-actions { text-align: right;
    white-space: nowrap; }` plus a link colour from `--ink-muted`/`--accent`
    with `text-decoration: none` and a hover/focus colour — no new colors,
    radii, spacing values, or shadows (a global `:focus-visible` ring already
    covers keyboard focus)

## Files to change
- `database/queries.py`
  - Add `get_expense_by_id` and `update_expense` (exact contract above)
  - Add `id` to `get_recent_transactions`'s `SELECT` and returned dict
  - Update the module docstring (two write paths, not one)
- `app.py`
  - Import `abort` from `flask`; import `get_expense_by_id` and
    `update_expense` from `database.queries`
  - Delete the plain-text placeholder from the "Placeholder routes" section and
    move `edit_expense` up into the main routes area, below `add_expense`; leave
    the `/expenses/<id>/delete` placeholder untouched
  - Decorator: `@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])`
  - Optionally extract `_parse_expense_form` (see Validation)
- `templates/profile.html` — Actions column + edit links + `colspan="5"`
- `static/css/style.css` — `.tx-actions` rule
- `tests/test_backend_connection.py` — **required**: `test_get_recent_transactions`
  asserts `set(item) == {"date", "description", "category", "amount"}`; that set
  must become `{"id", "date", "description", "category", "amount"}` or the suite
  will fail
- `AGENTS.md` — route table: `GET /expenses/<id>/edit` → Implemented (Step 8),
  and its method becomes `GET`/`POST`; drop that route from the "placeholder
  routes" gotcha (it still applies to `/expenses/<id>/delete`)

## Files to create
- `templates/edit_expense.html` — the edit-expense form
- `tests/test_edit_expense.py` — tests listed below

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA stays enabled on every connection (already in `get_db()`)
- Ownership is enforced in SQL, twice: the `SELECT` and the `UPDATE` both carry
  `id = ? AND user_id = ?`
- A missing or foreign-owned expense is **404** on both GET and POST
- Validation failures are **400** with the form re-rendered and the submitted
  (not stored) values retained; only a successful write redirects
- Amounts stored via `round(float(value), 2)`; dates stored as zero-padded ISO
- Blank description stores SQL `NULL`, never the empty string
- Category list comes from `CATEGORIES`; never re-declare it
- All templates extend `base.html`; no inline styles; CSS tokens only (hex
  literals stay in `:root`)
- Currency displays as ₹ everywhere — never £ or $
- Do not implement Step 9 (delete) or touch the `/expenses/<id>/delete` stub

## Out of scope / accepted trade-offs
- The success redirect goes to a bare `/profile`, so an active date filter is
  dropped after saving (same as Step 7). The edited row is therefore always
  visible; returning to the filtered view is not implemented in this step.
- `/profile` lists only the 10 most recent transactions, so only those rows
  have Edit links. No pagination or "all transactions" view is added.
- No concurrency control beyond the `user_id`-scoped `UPDATE`: last write wins.
- No `updated_at` column, audit trail, or soft delete.
- Cancel returns to `/profile` and discards edits silently — no "unsaved
  changes" warning (no JavaScript in this step).

## Tests to write
File: `tests/test_edit_expense.py` (uses the existing `temp_db`, `client`,
`demo_user_id`, `blank_user_id` fixtures; authenticate via
`client.session_transaction()`, exactly like `test_add_expense.py`). The demo
user seeds 8 expenses — create a second user with an expense for the ownership
cases.

### Unit tests (helpers)
| Function | Input | Expected output |
|---|---|---|
| `get_expense_by_id` | existing id + owning `user_id` | dict whose keys are exactly `id`, `amount`, `category`, `date`, `description`, values equal to the stored row |
| `get_expense_by_id` | existing id + wrong `user_id` | `None` |
| `get_expense_by_id` | non-existent id | `None` |
| `update_expense` | correct owner, `amount=99.0` | returns `1`; a direct query shows the new amount, and the row `id`/`user_id` are unchanged |
| `update_expense` | wrong `user_id` | returns `0`; row byte-for-byte unchanged (no exception raised) |
| `update_expense` | `description=None` | returns `1`; stored value is SQL `NULL` |
| `get_recent_transactions` | demo user | every dict contains an `id` equal to the row's `id`, ordering unchanged |

### Route tests
`GET /expenses/<id>/edit`
- unauthenticated → 302 to `/login`
- own expense → 200; body contains a `<form method="POST">`, the amount
  (`value="<amount>"`), the ISO date, the description, and a `<select>` with
  exactly one `selected` option matching the stored category
- a row inserted with `insert_expense(..., 12.5, ...)` (one decimal) → rendered
  as `value="12.50"` (all seed amounts already have two decimals, so the test
  must create this row itself)
- other user's expense → 404
- non-existent id → 404
- non-integer id (`/expenses/abc/edit`) → 404

`POST /expenses/<id>/edit`
- unauthenticated → 302 to `/login` and the row is unchanged
- valid data → 302 to `/profile`; DB reflects the new amount, category, date
  and description; a `success` flash is queued; other rows untouched
- other user's expense → 404 and that row is unchanged
- non-existent id → 404
- missing amount → 400, error text present, submitted category/date retained
- `amount=0` → 400 with error
- `amount=-5` → 400 with error
- `amount=abc` → 400 with error
- `amount=nan` → 400 with error (non-finite guard)
- `amount=12.344` → 302; stored value is `12.34` (2-dp rounding)
- invalid category (`"Pets"`) → 400 with error, row unchanged
- invalid date (`"20-03-2026"`) → 400 with error
- non-padded date (`"2026-3-5"`) → 302; stored as `2026-03-05`
- no description → 302; stored `description IS NULL`
- description of 201 chars → 400 with error
- validation failure does not overwrite the stored row (re-read it afterwards)

### Profile page
- `/profile` body contains an edit link for each of the demo user's expenses
  pointing at `/expenses/<id>/edit`
- empty-state row uses `colspan="5"` (blank user)

## Definition of done
- [ ] Logged-out `GET`/`POST /expenses/<id>/edit` redirect to `/login`
- [ ] Missing, malformed, or foreign-owned id → 404 on both methods
- [ ] Logged-in GET shows the form pre-filled with the stored amount (2 dp),
      category (pre-selected), date, and description
- [ ] A valid POST updates the row in place, flashes `Expense updated.`, and
      redirects to `/profile` where the new values are visible
- [ ] Editing cannot touch another user's row (SQL `user_id` guard on both
      statements, verified by test)
- [ ] Missing / zero / negative / non-numeric / non-finite amount → 400 with
      error and submitted values retained
- [ ] Invalid category → 400 with error; invalid date → 400 with error
- [ ] Description is optional (blank → `NULL`); over-200 chars → 400 with error
- [ ] Stored date is canonical `YYYY-MM-DD`; stored amount rounded to 2 dp
- [ ] Every row in the profile transaction table has one Edit link pointing at
      the correct URL, and the empty state spans all five columns
- [ ] `tests/test_backend_connection.py` updated for the new `id` key and the
      suite passes: `uv run pytest` (the current 105 tests plus the new ones,
      all green)
- [ ] `AGENTS.md` route table and placeholder-route gotcha updated

## Changes made in review
- **Status codes:** validation failures corrected from 200 to **400** (matches
  `register`, `login`, `add_expense`, and `AGENTS.md`).
- **Missing rule:** added the 200-character description limit, absent from the
  draft's validation list but present in Step 7 and in the template's
  `maxlength`.
- **Missing guards:** added the `math.isfinite` and `round(..., 2)` amount
  rules and the zero-padded ISO date normalisation from Step 7.
- **Breaking existing test:** flagged that adding `id` to
  `get_recent_transactions` fails `tests/test_backend_connection.py`
  (exact-key-set assertion); the spec now requires updating it.
- **Broken layout:** the empty-state `colspan="4"` must become `colspan="5"`.
- **Unspecified helper contracts:** pinned `get_expense_by_id`'s return shape
  (plain dict, five keys) and `update_expense`'s return value (`rowcount`),
  plus the 0-rows → 404 race handling.
- **Missing 404 mechanics:** specified `abort(404)`, its import, why 404 beats
  403, and that no custom 404 template is in scope.
- **Ordering:** fetch-before-validate, so a foreign POST is a 404 and never
  echoes another user's row into the form.
- **Stale-session guard:** added the `get_user_by_id` check used by
  `add_expense`, so a dead session cannot masquerade as a 404 or a silent
  no-op update.
- **Template details:** `url_for` instead of hardcoded action URLs, amount
  rendered at 2 dp on GET, exact field attribute parity, loop variable `t`,
  and a `.tx-actions` CSS rule built from tokens.
- **Docstring debt:** `database/queries.py`'s "single write path" comment is
  now wrong; the spec requires updating it.
- **Missing test coverage:** added nan/inf, rounding, date normalisation,
  over-200 description, non-integer id, unchanged-row-after-failure, flash,
  profile edit links, and the `get_recent_transactions` `id` test.
- **Stale project doc:** `AGENTS.md` claims "83 tests"; the suite is actually
  105 today (all passing), so the definition of done cites the real number and
  implementation should refresh that line while editing the route table.
- **Scope/exclusions:** added "Do not implement Step 9", the `AGENTS.md`
  update, and an explicit "Out of scope / accepted trade-offs" section
  (filter loss on redirect, 10-row window, last-write-wins, no `updated_at`).
