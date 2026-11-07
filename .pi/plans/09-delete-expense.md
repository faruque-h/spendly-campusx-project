# Implementation Plan — Step 9: Delete Expense

**Spec:** `.pi/specs/09-delete-expense.md` (reviewed + corrected — helper renamed
`remove_expense` to avoid shadowing the view, single `DELETE` + `rowcount`
instead of a read-then-write pair, success flash, stale-session guard, no inline
styles, no inline JS, `AGENTS.md` sync)
**Branch:** `feature/delete-expense` (already checked out — no branch work needed)
**Files to change:** `database/queries.py` (1 new helper + docstring), `app.py`
(1 import + 1 view replacing the stub + placeholder banner removal),
`templates/profile.html` (delete form in `.tx-actions`), `static/js/main.js`
(`data-confirm` listener), `static/css/style.css` (one block),
`AGENTS.md` (route table, gotchas, helper list, JS note, test count)
**Files to create:** `tests/test_delete_expense.py`
**Status:** implemented — 158 tests green (139 existing + 19 new)
**Locked decisions:** one view `delete_expense`, **POST only**; auth guard +
stale-session guard mirror `add_expense` / `edit_expense`; ownership enforced in
the `DELETE` itself; `rowcount == 0` → `abort(404)` (no pre-flight `SELECT`);
success → `flash("Expense deleted.", "success")` +
`redirect(url_for("profile"))`; confirmation is client-side only
(`data-confirm` → one listener in `main.js`); no new CSS tokens, no new
components, no new dependencies.

---

## 1. Objective

Let a signed-in user permanently remove one of their own expenses from the
profile transaction table, without letting them touch another user's row and
without a second round-trip that could go stale.

1. `database/queries.py` — add `remove_expense(expense_id, user_id)` returning
   `rowcount`; fix the module docstring that still claims two write paths.
2. `app.py` — replace the `GET`-only placeholder with the POST-only view
   (guard → delete → 404 on 0 rows → flash → redirect).
3. `templates/profile.html` — a small POST form + "Delete" button beside the
   existing "Edit" link, uniquely labelled for screen readers.
4. `static/js/main.js` + `static/css/style.css` — the `confirm()` prompt and the
   two token-based rules that keep the button looking like a row action.
5. `tests/test_delete_expense.py` — helper contract, route contract, profile
   markup; the existing 139 tests stay green.

---

## 2. Current state (verified)

| Item | Verified state |
|---|---|
| Branch / git | On `feature/delete-expense`. Nothing dirty except untracked `.pi/specs/09-delete-expense.md`. |
| Test baseline | `uv run pytest -q` → **139 passed in 8.72s**: 15 `test_backend_connection.py`, 50 `test_date_filter.py`, 40 `test_add_expense.py`, 34 `test_edit_expense.py`. |
| `app.py` — stub | Lines 429–437: the `# Placeholder routes — students will implement these` banner, then `@app.route("/expenses/<int:id>/delete")` → `def delete_expense(id)` → `return "Delete expense — coming in Step 9"`. This is now the **only** placeholder left. |
| `app.py` — imports | `abort` is already imported from Flask (line 8); `flash`, `redirect`, `session`, `url_for` too. `database.queries` block imports `get_category_breakdown, get_expense_by_id, get_recent_transactions, get_summary_stats, get_user_by_id, insert_expense, update_expense`. |
| `app.py` — guard idiom | `edit_expense` (lines ~390–405) is the template: auth check → `get_user_by_id` stale-session check → `abort(404)` on missing/foreign. Success flashes `Expense updated.` and redirects to `url_for("profile")`. |
| `database/queries.py` | 194 lines. Docstring line 6: `insert_expense() and update_expense() are the two write paths.` `update_expense` (lines 181–194) is the shape to copy: `with conn:`, parameterised statement, `return cursor.rowcount`, `finally: conn.close()`. No delete helper exists. |
| `templates/profile.html` | Lines 87–89: `<td class="tx-actions">` containing only `<a class="tx-action-link" href="{{ url_for('edit_expense', id=t.id) }}">Edit</a>`. Loop variable is `t`; empty state at line 93 is `colspan="5"`. |
| `static/js/main.js` | Single line: `// main.js — students will add JavaScript here as features are built`. Loaded by `base.html` line 56 on **every** page, before the `scripts` block. |
| `static/css/style.css` | `.tx-action-link` at 883–893 (hover → `--accent` + underline), then `.badge` at 895. **No bare `button` selector anywhere** in the file, so the new `<button>` starts from UA styles (13.33px Arial, grey gradient) and must be reset. Global `:focus-visible` ring is at 997 (`outline: 2px solid var(--accent)`), which covers a link-styled button. Tokens `--ink-muted`, `--danger`, `--text-sm`, `--space-3` all exist in `:root`. |
| Existing tests that could break | `test_backend_connection.py:124` counts `<td class="tx-date">`; `test_date_filter.py:88,799` regex `tx-date` / `tx-amount`; `test_edit_expense.py:475` asserts the `th.tx-actions` text and `:486` asserts `colspan="5"`. **None** parse the inside of `td.tx-actions`, so adding a form there breaks nothing. |
| Fixtures | `tests/conftest.py`: `temp_db`, `app`, `client`, `demo_user_id` (8 seeded expenses), `blank_user_id` (no expenses). Sign-in idiom: `with client.session_transaction() as sess: sess["user_id"] = user_id`. Flash assertion idiom from `test_edit_expense.py`: POST with `follow_redirects=True`, assert the message is in the body. |
| `AGENTS.md` | Line 12 lists the query helpers ("two write paths"); line 21 says 139 tests; line 59 has `| GET /expenses/<id>/delete | Stub — Step 9 |`; line 65 calls the placeholder route a course step; line 65's neighbour says the only JS is inline in `landing.html`. All five lines go stale with this step. |

---

## 3. Decisions taken while planning

| # | Decision | Why |
|---|---|---|
| D1 | Helper named **`remove_expense`**, not `delete_expense` | `app.py` defines the view as `def delete_expense`. A same-named import at the top of the module is rebound by that `def`, so the in-view call would raise `TypeError: delete_expense() takes 1 positional argument but 2 were given` and never touch the DB. Keeping the helper name distinct preserves the alias-free import block. |
| D2 | One `DELETE … WHERE id = ? AND user_id = ?`; `rowcount == 0` → `abort(404)` | The spec's draft checked `get_expense_by_id` first, then deleted — two statements, a TOCTOU gap, and an unnecessary second connection. `update_expense` already established the `rowcount` contract; reuse it. |
| D3 | Keep the endpoint name `delete_expense` | The stub already uses it and `profile.html` will call `url_for("delete_expense", id=t.id)`. Only the *helper* is renamed. |
| D4 | Stale-session guard kept (parity with add/edit) | A dead session resolves to "no owned rows" anyway, but redirecting to `/login` beats a 404 for a user who was signed in a moment ago. One extra `SELECT` on a destructive action is cheap. |
| D5 | Confirmation via `data-confirm` + one delegated listener in `main.js` | Removes the inline `onsubmit` that the spec's draft allowed, keeps markup declarative, and gives the already-loaded empty `main.js` its first real job. The form still works without JS (deletes unprompted) — documented trade-off. |
| D6 | `.tx-delete-form` / `.tx-delete-btn`, not `.btn-delete` | `btn-*` is the page-level button family (`.btn-primary`, `.btn-ghost`, `.btn-submit`). An in-table action should look like `.tx-action-link`, so the Delete button is a reset link, not a bordered button. |
| D7 | Danger colour is already a token (`--danger: #a93226`) | No `:root` change. Hover goes `--ink-muted` → `--danger` + underline, mirroring `.tx-action-link`'s hover. |
| D8 | Unique `aria-label` per Delete button | The table renders up to 10 identical "Delete" labels; screen-reader users need category/amount/date context. |
| D9 | Remove the now-empty placeholder banner from `app.py` | With this view implemented there are no stubs left; leaving a "students will implement these" header over the app entrypoint would be misleading. Same for the matching `AGENTS.md` gotcha. |
| D10 | Do not preserve the date filter on the success redirect | Bare `/profile`, exactly like Steps 7 and 8. Consistency beats a one-off improvement; noted in "Out of scope". |

---

## 4. Implementation steps (in order)

### 4.1 `database/queries.py` — two edits

**a) Docstring (lines 1–7)** — the "two write paths" claim becomes false:

```python
"""Query helpers for Spendly. No Flask imports.

Every function opens its own connection via get_db() and closes it before
returning, so callers never manage connections. Optional date_from/date_to
(ISO YYYY-MM-DD, inclusive) narrow every read helper to that range.
insert_expense(), update_expense() and remove_expense() are the three write
paths.
"""
```

**b) New helper** — append after `update_expense` (keeps all write paths
together at the bottom of the file, matching the existing layout):

```python
def remove_expense(expense_id, user_id):
    """Delete one owned expense; return the number of rows deleted (0 or 1)."""
    conn = get_db()
    try:
        with conn:  # commits on success, rolls back on error
            cursor = conn.execute(
                "DELETE FROM expenses WHERE id = ? AND user_id = ?",
                (expense_id, user_id),
            )
        return cursor.rowcount
    finally:
        conn.close()
```

- Parameterised only; the `user_id = ?` predicate is the ownership guard.
- `cursor.rowcount` is the deleted-row count for `DELETE` in `sqlite3`.
- A 0-row delete still commits (a no-op) — no special handling needed.

### 4.2 `app.py` — import, then replace the stub

**a) Import** — add `remove_expense` to the existing `database.queries` block,
between `insert_expense` and `update_expense` (alphabetical, as the block is
today):

```python
from database.queries import (
    get_category_breakdown,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    insert_expense,
    remove_expense,
    update_expense,
)
```

**b) Replace lines 429–437** — delete the placeholder banner and the stub, and
put the real view after `edit_expense` (route order then matches the step
sequence: add, edit, delete):

```python
@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    if get_user_by_id(user_id) is None:
        # Stale session for a user that no longer exists.
        session.clear()
        flash("Please sign in again.", "error")
        return redirect(url_for("login"))

    if remove_expense(id, user_id) == 0:
        # Missing, or owned by someone else — indistinguishable by design.
        abort(404)

    flash("Expense deleted.", "success")
    return redirect(url_for("profile"))
```

Guard order matters and must not be reordered:

1. auth → `/login` (nothing deleted)
2. stale session → `session.clear()` + flash + `/login`
3. delete (single owned statement)
4. `0` rows → 404
5. flash + redirect

Notes:

- `GET` never reaches the view: Flask's routing returns **405** with
  `Allow: POST, OPTIONS`. Do not add a `request.method` branch.
- Keep the `if __name__ == "__main__":` block immediately after, unchanged.
- Nothing else in `app.py` changes; `abort` is already imported.

### 4.3 `templates/profile.html` — Actions cell (lines 87–89)

```html
                                <td class="tx-actions">
                                    <a class="tx-action-link" href="{{ url_for('edit_expense', id=t.id) }}">Edit</a>
                                    <form class="tx-delete-form" method="POST"
                                          action="{{ url_for('delete_expense', id=t.id) }}"
                                          data-confirm="Delete this expense? This cannot be undone.">
                                        <button type="submit" class="tx-delete-btn"
                                                aria-label="Delete {{ t.category }} expense of ₹{{ '%.2f'|format(t.amount) }} on {{ t.date|display_date }}">Delete</button>
                                    </form>
                                </td>
```

- `url_for` only — no hardcoded `/expenses/<id>/delete`.
- No inline `style`, no inline `onsubmit`; the `display:inline` rule lives in CSS.
- The empty-state row stays `colspan="5"` (no new column).
- Currency stays `₹` with 2 dp, date goes through `display_date`.

### 4.4 `static/js/main.js` — confirmation listener

Replace the one-line stub with:

```js
// main.js — shared behaviour, no frameworks.

// Any form carrying data-confirm asks before submitting. Without JS the form
// still submits: the prompt is an enhancement, not a gate.
document.addEventListener("submit", (event) => {
    const message = event.target.dataset.confirm;
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});
```

- Delegated, so it also serves any later destructive form that adds
  `data-confirm`; no per-page wiring, no `DOMContentLoaded` needed (the script
  is loaded at the end of `<body>`, and delegation works regardless).
- `window.confirm` returns `false` on Cancel/Escape → `preventDefault()` keeps
  the row intact.

### 4.5 `static/css/style.css` — one block after `.tx-action-link:hover` (line 893)

```css
.tx-delete-form {
    display: inline;
    margin-left: var(--space-3);
}

.tx-delete-btn {
    padding: 0;
    border: 0;
    background: transparent;
    font: inherit;
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--ink-muted);
    cursor: pointer;
}

.tx-delete-btn:hover {
    color: var(--danger);
    text-decoration: underline;
}
```

- `font: inherit` is required: there is no bare `button` rule, so without it the
  button would render in the UA default (13.33px Arial) instead of DM Sans.
- Tokens only — no new hex, radius, spacing, or shadow. `--danger` already
  exists in `:root` with `--danger-light` / `--danger-border` alongside it.
- `td.tx-actions` already sets `text-align: right; white-space: nowrap`, so the
  link and the form stay on one line.
- The global `:focus-visible` ring covers keyboard focus; no extra focus rule.

### 4.6 `AGENTS.md` — five stale lines

| Line | Change |
|---|---|
| 12 | `plus insert_expense / update_expense, the two write paths` → `plus insert_expense / update_expense / remove_expense, the three write paths` |
| 21 | `139 tests` → the real count after the new module lands |
| 59 | `| GET /expenses/<id>/delete | Stub — Step 9 |` → `| POST /expenses/<id>/delete | Implemented — Step 9 (owned DELETE, 404 for missing/foreign, flash + redirect to /profile) |`; retitle the table section since no stubs remain |
| 65 | Delete the "placeholder route … intentional plain text" gotcha (the stub is gone), and keep "Do not implement a stub route unless the active task explicitly targets that step" only if it still reads sensibly with zero stubs — otherwise drop it too |
| JS bullets (`static/js/…`) | `main.js — empty stub` → "delegated `data-confirm` submit prompt (profile delete forms)"; the "only JS is inline in `landing.html`" claim → both `main.js` and the landing modal |

---

## 5. Tests — `tests/test_delete_expense.py`

Reuse the `test_edit_expense.py` helper style rather than ad-hoc string checks.

```python
"""Tests for Step 9 delete-expense (app.py + database/queries.py).

Contract: .pi/specs/09-delete-expense.md
Importing `app` seeds the database, so it only happens via `temp_db`.
"""

import pytest

import database.db as db_module
from database.queries import insert_expense, remove_expense

SUCCESS_FLASH = "Expense deleted."
MISSING_ID = 999999
```

Local helpers:

```python
def _sign_in(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _redirect_path(response):
    return urlsplit(response.headers["Location"]).path


def _row(expense_id):
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE id = ?", (expense_id,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


def _expenses_for(user_id):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT id FROM expenses WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
    finally:
        conn.close()


def _seeded_expense(user_id, **overrides):
    """Insert one expense for `user_id`; returns its id."""
    values = {"amount": 12.5, "category": "Bills",
              "date": "2026-03-21", "description": "Coffee"}
    values.update(overrides)
    return insert_expense(user_id, values["amount"], values["category"],
                          values["date"], values["description"])


def _other_user_expense():
    """Second user owning one expense; returns (user_id, expense_id)."""
```

(Use `insert_expense` from `queries` for fixture rows; never depend on seed
ordering, and never touch `spendly.db`.)

| # | Test | Assertion |
|---|---|---|
| 1 | `remove_expense` own row | returns `1`; `_row(id)` is `None` |
| 2 | `remove_expense` wrong user | returns `0`; `_row(id)` equals the pre-delete dict exactly |
| 3 | `remove_expense` missing id | returns `0`; no exception |
| 4 | `remove_expense` with siblings | exactly the target row is gone; the user's other rows and the `users` row survive |
| 5 | POST unauthenticated | 302, path `/login`; row still exists |
| 6 | POST stale session (`user_id = MISSING_ID`) | 302, path `/login`; row still exists |
| 7 | POST own expense | 302, path `/profile`; row gone; `demo_user_id`'s other rows untouched |
| 8 | POST own expense, `follow_redirects=True` | body contains `Expense deleted.` and no longer contains the deleted description/amount |
| 9 | POST other user's expense | 404; that row still exists (compare full dict) |
| 10 | POST missing id | 404 |
| 11 | POST `/expenses/abc/delete` | 404 (no rule matches a non-int path) |
| 12 | GET unauthenticated | 405 |
| 13 | GET authenticated | 405; `"POST" in response.headers["Allow"]`; row still exists |
| 14 | profile renders delete forms | for each listed row, `f'action="/expenses/{row["id"]}/delete"'` and `method="POST"` present |
| 15 | profile shows both actions | each listed row's id appears in **both** `/expenses/<id>/edit` and `/expenses/<id>/delete` |
| 16 | profile delete button is accessible | `aria-label="Delete ` present per row and the label contains the category |
| 17 | profile empty state | `colspan="5"` still present for `blank_user_id` |
| 18 | delete then reload profile | deleted id absent from `/profile`; the user's other ids still present |

Deliberately **not** tested: Flask's default 404/405 markup, `.tx-delete-*` CSS,
`window.confirm` behaviour (browser-side, no JS test harness exists), flash
styling.

Expected new tests: **19** (139 → 158), all green.

---

## 6. Verification

```bash
# 1. Fast contract check while iterating
uv run pytest tests/test_delete_expense.py -q

# 2. Full suite — must stay green, including test_edit_expense.py's
#    th.tx-actions / colspan="5" assertions
uv run pytest

# 3. Dev server (only if port 5001 is free — check first)
uv run python app.py
```

Manual smoke (`demo@spendly.com` / `demo123`):

1. `/profile` → every row shows **Edit Delete** on the right, Delete in muted
   grey, both on one line; keyboard `Tab` reaches the Delete button and shows
   the accent focus ring.
2. Click Delete → confirm dialog (`Delete this expense? This cannot be
   undone.`) → **Cancel** leaves the row and the totals untouched.
3. Click Delete → **OK** → landing back on `/profile` with the
   `Expense deleted.` flash, the row gone, and Total spent / Transactions /
   Category breakdown all reflecting the removal.
4. Delete the last remaining expense → profile shows `₹0.00`, `0` transactions,
   "No spending in this range.", and the "No transactions" empty row.
5. Visit `http://localhost:5001/expenses/<id>/delete` directly → 405 page.
6. Signed out, `curl -X POST http://localhost:5001/expenses/1/delete` →
   302 to `/login`.
7. Sign in as a second account and POST another user's id (via
   `curl -b` / devtools) → 404.
8. Submit the form twice quickly (devtools "Resend") → second request 404,
   nothing extra deleted.
9. Narrow to ~360 px → the Actions cell does not force horizontal scroll
   (`.table-wrap` scrolls instead).

---

## 7. Risks / out of scope

| Item | Note |
|---|---|
| Helper name divergence (`remove_expense` vs `insert`/`update`) | Deliberate (D1). The docstring and spec record why; the alternative — a shadowed import — is a runtime `TypeError`. |
| Deleting the wrong row | The `user_id` predicate is the only guard, and the browser confirm is the only friction. A shared link/POST could delete an owned row without a prompt if a user is tricked into submitting it — the residual CSRF gap below. |
| CSRF | No token infrastructure exists; Steps 1–8 post plain forms. `SESSION_COOKIE_SAMESITE = "Lax"` (already set) blocks cookie-bearing cross-site POSTs. Out of scope, documented in the spec. |
| `rowcount` semantics | Verified for `DELETE` in the stdlib `sqlite3` module; returns 0 for a foreign/missing id, which is exactly the 404 signal. No `SELECT`-then-`DELETE` fallback needed. |
| Confirmation is not server-side | A double submit lands on the 404 page; a JS-disabled browser deletes without prompting. Accepted. |
| Filter lost after delete | Redirect is a bare `/profile` (parity with Steps 7/8). The deleted row is gone anyway, but the remaining list is unfiltered. |
| Existing test coupling | Checked by grep: nothing parses the inside of `td.tx-actions`, and `th.tx-actions` / `colspan="5"` are unchanged. `test_recent_transactions` key sets are untouched (no query-shape change). |
| `AGENTS.md` drift | The single most likely follow-up miss; §4.6 lists all five lines with line numbers. |
| Out of scope | Custom 404/405 templates, undo/soft delete/`deleted_at`, bulk delete, delete-from-edit-page link, toast/flash dedupe, pagination, preserving filters or `next`, CSRF tokens. |

---

## 8. Definition of done → evidence

| DoD bullet | Where it is proven |
|---|---|
| Logged-out POST → `/login`, nothing deleted | test 5, manual 6 |
| Missing / foreign id → 404 | tests 9, 10, 11 |
| `GET` → 405 (anonymous and signed-in) | tests 12, 13, manual 5 |
| Own expense deleted, `Expense deleted.` flashed | tests 7, 8 |
| Redirect to `/profile`, expense no longer listed | test 18, manual 3 |
| Cancel in `confirm()` leaves the row intact | manual 2 (browser-only) |
| Rows show Edit **and** Delete, each button labelled | tests 14, 15, 16, manual 1 |
| `remove_expense` scoped by `user_id`, returns `rowcount` | tests 1–4 |
| No inline styles/JS; tokens only | §4.3–4.5 (code review + manual 1) |
| `AGENTS.md` route table, gotchas, helper list, test count | §4.6 |
| `uv run pytest` green (139 existing + 19 new = 158) | §6 step 2 |
