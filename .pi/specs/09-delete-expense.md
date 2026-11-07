# Spec: Delete Expense

## Overview
Step 9 lets a logged-in user permanently delete one of their own expenses from the
profile transaction table. Each row's existing Actions cell gains a small
`POST` form next to the Step 8 "Edit" link; the handler deletes the row scoped by
`id = ? AND user_id = ?`, flashes a success message, and redirects back to
`/profile`.

Deletion is **one SQL statement**, not a read-then-write pair: `remove_expense()`
returns `cursor.rowcount`, and `0` means "missing or not yours" → **404**. This
mirrors `update_expense()`'s race handling from Step 8, avoids a TOCTOU window
between the ownership check and the `DELETE`, and means no new lookup helper is
needed (`get_expense_by_id` is **not** called in this step).

There is no confirmation page and no soft delete. Accidental clicks are guarded
only by a browser `confirm()` dialog, requested declaratively via a
`data-confirm` attribute and handled by the shared `static/js/main.js`. The row
is gone the moment the POST lands — there is no undo.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 3: Login / Logout (`session["user_id"]` is set and enforced)
- Step 5: Profile page renders transactions (the delete form lives there)
- Step 8: Edit Expense (the Actions column, `.tx-actions` CSS, and the
  `add`/`edit` success-flash pattern this step copies)

Step 6 (date filter) is **not** a dependency: the success redirect goes to a bare
`/profile`, so an active date range is dropped after deleting (same as Steps 7
and 8). See "Out of scope".

## Routes
One view function, `delete_expense`, **POST only**:

- `POST /expenses/<int:id>/delete` — delete one owned expense, redirect to
  `/profile` — logged-in only

```python
@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    ...
```

The decorator replaces the GET-only placeholder stub in `app.py`; the endpoint
name `delete_expense` must stay, because `profile.html` references
`url_for("delete_expense", id=t.id)`.

Order inside the view — do not reorder:

1. Auth guard: `if session.get("user_id") is None: return redirect(url_for("login"))`
2. Stale-session guard (parity with `/expenses/add` and `/expenses/<id>/edit`):
   `get_user_by_id(session["user_id"])` is `None` → `session.clear()`,
   `flash("Please sign in again.", "error")`, redirect to `/login`
3. `remove_expense(id, session["user_id"])`
4. `if deleted == 0: abort(404)` — missing id *and* foreign-owned id are
   indistinguishable, so a user cannot probe which ids exist
5. `flash("Expense deleted.", "success")`
6. `return redirect(url_for("profile"))`

Notes pinned by this spec:

- **405 is automatic.** Flask rejects a bare `GET` at routing time, before the
  view runs, so `GET` → 405 for anonymous and signed-in users alike. No
  `methods` check belongs in the view body.
- `abort` is already imported in `app.py`; no new Flask imports are needed.
- No custom 404 page exists in this project — Flask's default error body is
  correct here (same as Step 8).
- No `next` / return-to parameter, and no flash on the auth guard (parity with
  the other guarded views).
- POST-redirect-GET: the redirect means a browser refresh does not resubmit the
  form.

## Database changes
No new tables or columns. `expenses` already has `id`, `user_id`, `amount`,
`category`, `date`, `description`, `created_at`.

## Query helpers
Add `remove_expense()` to `database/queries.py` (no Flask imports; opens and
closes its own connection):

```python
def remove_expense(expense_id, user_id):
    """Delete one owned expense; return the number of rows deleted (0 or 1)."""
```

- A single parameterised `DELETE FROM expenses WHERE id = ? AND user_id = ?`,
  wrapped in `with conn:` (commit on success, rollback on error), connection
  closed in `finally`. Return `cursor.rowcount`.
- The `user_id = ?` predicate is the ownership guard: a foreign-owned row is
  indistinguishable from a missing one, and the earlier cheap ownership check
  cannot go stale because there isn't one.
- **Why `remove_expense` and not `delete_expense`:** `app.py` already defines a
  view named `delete_expense`. A same-named helper imported at the top of
  `app.py` would be *shadowed* by the later `def`, and the call inside the view
  would raise `TypeError` instead of touching the database. Keeping the helper
  name distinct preserves the uniform, alias-free import block in `app.py`.
- **Docstring debt:** the module docstring currently says `insert_expense()` and
  `update_expense()` "are the two write paths". Update it to name all three
  (`insert_expense`, `update_expense`, `remove_expense`).

## Templates
- **Modify** `templates/profile.html` — inside the existing
  `<td class="tx-actions">`, after the Edit link (loop variable is `t`, not `tx`):

  ```html
  <form class="tx-delete-form" method="POST"
        action="{{ url_for('delete_expense', id=t.id) }}"
        data-confirm="Delete this expense? This cannot be undone.">
    <button type="submit" class="tx-delete-btn"
            aria-label="Delete {{ t.category }} expense of ₹{{ '%.2f'|format(t.amount) }} on {{ t.date|display_date }}">Delete</button>
  </form>
  ```

  - `url_for` only — never a hardcoded `action` path.
  - `aria-label` is required: the table renders many identical "Delete" buttons,
    and the label gives each one unique context.
  - **No inline styles.** The draft's `style="display:inline"` exception is
    dropped; `.tx-delete-form` carries that rule in `style.css` instead.
  - **No inline JS.** The confirm prompt is declarative (`data-confirm`) and
    handled once in `main.js`, so the styling rule and the "shared JS lives in
    `static/js/main.js`" convention both hold.
  - The empty-state row keeps `colspan="5"` — Delete adds no column, so Step 8's
    span is unchanged.

- **Modify** `static/js/main.js` (currently an empty stub, already loaded by
  `base.html` on every page) — one delegated listener, no framework:

  ```js
  document.addEventListener("submit", (event) => {
      const message = event.target.dataset.confirm;
      if (message && !window.confirm(message)) {
          event.preventDefault();
      }
  });
  ```

  Without JS the form still submits (the expense is deleted unprompted) — an
  accepted trade-off for a confirmation dialog.

## Files to change
- `database/queries.py` — add `remove_expense()`; update the module docstring to
  list three write helpers.
- `app.py` — import `remove_expense`; replace the placeholder
  `@app.route("/expenses/<int:id>/delete")` (GET) with the POST-only handler and
  the guard order above. Delete the "coming in Step 9" placeholder string.
- `templates/profile.html` — the delete form + accessible button in `.tx-actions`.
- `static/js/main.js` — the `data-confirm` submit listener.
- `static/css/style.css` — two rules, built from existing tokens **only**
  (`--ink-muted`, `--danger`, `--text-sm`, `--space-3`); no new `:root` entries
  are needed, since `--danger`, `--danger-light`, and `--danger-border` already
  exist:

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

  The button is styled as a link-like row action, matching `.tx-action-link`;
  the existing global `:focus-visible` ring covers keyboard focus, so no extra
  focus rule. `.btn-delete` from the draft is dropped — the `btn-*` family is
  for primary/ghost page-level buttons, not in-table actions.
- `AGENTS.md` — required doc sync:
  - route table: `GET /expenses/<id>/delete` → **Stub** becomes
    `POST /expenses/<id>/delete` → **Implemented (Step 9)**;
  - drop `/expenses/<id>/delete` from the "placeholder route" gotcha (the
    placeholder disappears with this step) and refresh the
    implemented/stub wording;
  - `database/queries.py` helper list gains `remove_expense`;
  - the test count line ("currently 139 tests") must be refreshed to the real
    number after the new file lands.

## Files to create
- `tests/test_delete_expense.py` — tests listed below.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA stays enabled on every connection (already in `get_db()`)
- Ownership is enforced in the `DELETE` itself (`id = ? AND user_id = ?`); a
  missing or foreign-owned id must be **404**, never 403 (no id-existence leak)
- The route accepts `POST` only; `GET` must be **405**
- Unauthenticated access redirects to `/login` (302); nothing is deleted
- Success flashes `Expense deleted.` and redirects to `url_for("profile")` —
  never renders a template
- All templates extend `base.html`; **no inline styles at all** (the `width: %`
  on the breakdown bar is pre-existing data-driven markup and is out of scope)
- CSS tokens only; hex literals stay in `:root`; do not introduce new colours,
  radii, or spacing values
- Vanilla JS only — the confirm handler lives in `main.js`; no libraries
- Currency displays as ₹ everywhere — never £ or $
- Reuse the `t` loop variable and `url_for`; do not re-declare the category list

## Out of scope / accepted trade-offs
- **No CSRF token.** The project has no CSRF infrastructure and Steps 1–8 post
  plain forms without tokens; this step keeps that parity. `SESSION_COOKIE_SAMESITE
  = "Lax"` (already set in `app.py`) blocks cookie-bearing cross-site POSTs, which
  is the mitigation available without a new dependency.
- No confirmation page, no "trash", no undo, no soft delete — deletion is
  immediate and permanent once the POST lands.
- If JS is disabled the row deletes without the `confirm()` prompt.
- A double-click submits twice; the second request finds nothing and lands on the
  404 page. No flash-message dedupe or redirect-with-state.
- The success redirect goes to a bare `/profile`, so an active date filter is
  dropped (same as Steps 7 and 8).
- `/profile` shows only the 10 most recent transactions, so only those rows are
  deletable from the UI — no pagination or "all transactions" view.
- No bulk delete, no delete-from-edit-page link, no audit trail or `deleted_at`.

## Tests to write
File: `tests/test_delete_expense.py` (uses the existing `temp_db`, `client`,
`demo_user_id`, `blank_user_id` fixtures; authenticate via
`client.session_transaction()`, exactly like `test_add_expense.py`). The demo
user seeds 8 expenses — create a second user owning one expense for the ownership
case (mirror `_other_user_expense()` in `test_edit_expense.py`), and create rows
with `insert_expense()` rather than depending on seed ordering.

### Unit tests (helper)
| Function | Input | Expected output |
|---|---|---|
| `remove_expense` | valid `expense_id`, owning `user_id` | returns `1`; the row is gone from the database |
| `remove_expense` | valid `expense_id`, wrong `user_id` | returns `0`; the row is **unchanged** (no exception raised) |
| `remove_expense` | non-existent `expense_id` | returns `0`; no exception raised |
| `remove_expense` | owning user has several expenses | exactly one row removed; the user's other rows and the `users` row survive |

### Route tests
`POST /expenses/<id>/delete`
- unauthenticated → 302 to `/login`; the row still exists
- own expense → 302 to `/profile`; row gone; a `success` flash
  (`Expense deleted.`) is queued; the user's other expenses untouched
- other user's expense → 404; that row still exists
- non-existent id → 404
- non-integer id (`/expenses/abc/delete`) → 404

`GET /expenses/<id>/delete`
- unauthenticated → 405
- authenticated → 405 (`Allow` header contains `POST`); the row still exists

### Profile page
- `/profile` body contains a delete form per rendered transaction, pointing at
  `/expenses/<id>/delete`, with `method="POST"`
- each of those rows also still contains its `/expenses/<id>/edit` link (both
  actions coexist)
- blank user's empty-state row still uses `colspan="5"`
- after a successful delete, a fresh `GET /profile` no longer lists that expense

## Definition of done
- [ ] Logged-out `POST /expenses/<id>/delete` redirects to `/login` and deletes nothing
- [ ] `POST` for a non-existent or other user's expense returns 404
- [ ] `GET /expenses/<id>/delete` returns 405 (anonymous and signed-in)
- [ ] Deleting your own expense removes exactly that row and flashes `Expense deleted.`
- [ ] After deletion the user lands on `/profile` and the expense is gone from the
      transaction list
- [ ] Cancelling the browser `confirm()` dialog does not submit the form and leaves
      the expense intact (manual check — not automated)
- [ ] Each transaction row shows both "Edit" and "Delete" actions, and each Delete
      button has a unique `aria-label`
- [ ] `remove_expense()` scopes its `DELETE` by `user_id` and returns `rowcount`
- [ ] No inline styles or inline JS added; CSS uses existing tokens only
- [ ] `AGENTS.md` route table, placeholder-route gotcha, helper list, and test count updated
- [ ] `uv run pytest` is green — the current 139 tests plus the new file

## Changes made in review
- **Shadowed import / broken call:** the draft imported the helper as
  `delete_expense` while the view is also `def delete_expense`; the later
  definition rebinds the module-level name, so the in-view call raises
  `TypeError` instead of deleting. Helper renamed `remove_expense()` and the
  reason documented.
- **Two round-trips → one statement:** dropped the `get_expense_by_id` pre-check
  in favour of `rowcount == 0 → abort(404)`, matching `update_expense`'s
  race-safe pattern and removing a TOCTOU window. `get_expense_by_id` is
  therefore *not* reused in this step.
- **Missing success flash:** added `Expense deleted.` + flash parity with
  `Expense added.` / `Expense updated.`, plus a test asserting it.
- **Missing stale-session guard:** the draft's guard was auth-only; added the
  `get_user_by_id` check used by `add_expense` / `edit_expense` so a dead session
  gets a sign-in prompt instead of a 404.
- **Dropped the inline-style exception:** `style="display:inline"` is replaced by
  a `.tx-delete-form` rule, so the "no inline styles" rule of the project holds
  with no carve-outs.
- **Inline JS removed:** `onsubmit="return confirm(...)"` became
  `data-confirm` + one delegated listener in the already-loaded `main.js`,
  keeping markup declarative and giving the empty `main.js` stub its intended job.
- **Wrong CSS name/tokens:** `.btn-delete` (page-level button family, unspecified
  colour) replaced by `.tx-delete-form` / `.tx-delete-btn` built from the existing
  `--ink-muted`, `--danger`, `--text-sm`, `--space-3`. No new tokens are needed;
  `--danger*` already exists in `:root`.
- **Template bugs:** the draft used a `tx` loop variable (the template uses `t`)
  and a hardcoded `action` path; both fixed with `url_for`. Added a per-row
  `aria-label` because the table renders many identical "Delete" buttons.
  Confirmed `colspan="5"` needs no change.
- **Missing `AGENTS.md` sync:** the draft omitted the route-table row, the now-stale
  "placeholder route" gotcha, the helper list, and the test-count line that every
  prior step updates. Added as required files-to-change work.
- **Docstring debt:** `database/queries.py`'s "two write paths" docstring becomes
  wrong with a third write helper; the spec now requires updating it.
- **Test contract pinned:** `remove_expense` returns `rowcount` (not "row removed"
  prose), the ownership case asserts the row is *unchanged*, and coverage now
  includes untouched-sibling rows, the flash, the `Allow` header on 405, and
  profile-level Edit+Delete coexistence.
- **Scope/exclusions:** added an explicit "Out of scope" section — no CSRF token
  (with the `SameSite=Lax` mitigation), no undo/soft delete, filter loss on the
  redirect, double-submit → 404, JS-disabled deletion, 10-row window.
- **Test count:** the definition of done cites the real current number (139, all
  passing) so the suite size cannot silently drift again.
