# Implementation Plan — Step 8: Edit Expense

**Spec:** `.pi/specs/08-edit-expense.md` (reviewed + corrected — 400s not 200s,
description-length rule, `id` in `get_recent_transactions`, `colspan="5"`)
**Branch:** `feature/edit-expense` (already checked out — no branch work needed)
**Files to change:** `app.py` (imports + one new route + one shared validation
helper), `database/queries.py` (2 new helpers, 1 modified, docstring),
`templates/profile.html` (Actions column + links + colspan),
`static/css/style.css` (one small block), `tests/test_backend_connection.py`
(one assertion), `AGENTS.md` (route table + counts)
**Files to create:** `templates/edit_expense.html`, `tests/test_edit_expense.py`
**Status:** implemented — 139 tests green (`105 existing + 34 new`)
**Locked decisions:** one view `edit_expense` with `GET, POST`; auth guard and
stale-session guard mirror `add_expense`; ownership enforced in SQL on **both**
the `SELECT` and the `UPDATE`; missing/foreign/unparsable id → **404** via
`abort`; validation failures → **400** with sticky submitted values; success →
`flash("Expense updated.", "success")` + `redirect(url_for("profile"))`;
validation is shared with Step 7 through one extracted helper; form reuses the
`.auth-card` + `.form-input` + `.btn-submit` family — **no new component**;
`/expenses/<id>/delete` stays a stub.

---

## 1. Objective

Let a signed-in user change an existing expense — amount, category, date,
description — without letting them touch anyone else's row and without
duplicating the Step 7 validation rules in a second place.

1. `database/queries.py` — `get_expense_by_id(...)` (owned read, `None`
   otherwise) and `update_expense(...)` (owned write, returns `rowcount`);
   add `id` to `get_recent_transactions` so the table can link rows.
2. `app.py` — extract the Step 7 validation block into
   `_parse_expense_form(form_data)` and use it from **both** `add_expense` and
   the new `edit_expense` view (guard → fetch/404 → validate → update →
   redirect).
3. `templates/edit_expense.html` — new page, byte-for-byte the same field
   markup as `add_expense.html`, different labels/action.
4. `templates/profile.html` + `static/css/style.css` — an "Actions" column with
   an "Edit" link per row.
5. `tests/test_edit_expense.py` + one assertion fix in
   `tests/test_backend_connection.py` — 105 existing tests stay green.

---

## 2. Current state (verified)

| Item | Verified state |
|---|---|
| Branch / git | On `feature/edit-expense`; working tree has one untracked file (`.pi/specs/08-edit-expense.md`). Nothing else dirty. |
| Test baseline | `uv run pytest` → **105 passed**: 15 in `test_backend_connection.py`, 50 in `test_date_filter.py`, 40 in `test_add_expense.py`. |
| `app.py` — placeholder | Lines ~369–380: "Placeholder routes" banner, then `@app.route("/expenses/<int:id>/edit")` → `return "Edit expense — coming in Step 8"`, then the delete stub. Both are inside the placeholder block, **after** `add_expense`. |
| `app.py` — imports | `math`, `sqlite3`, `re`, `os` at top; `from datetime import date, datetime`; Flask imports at line 7 are `Flask, flash, redirect, render_template, request, session, url_for` — **`abort` is not imported**. `CATEGORIES`, `get_db`, `init_db`, `seed_db` from `database.db`; five query helpers from `database.queries`. |
| `app.py` — Step 7 view | Lines ~296–367: auth guard → stale-session guard (`get_user_by_id`) → default `form` → POST normalise/validate (single `error`, first failing rule) → `insert_expense` (catches `sqlite3.IntegrityError` for a dead session) → flash + redirect, or `render_template(..., **form), 400`. The validation block is inline in the view — this is the code to extract. |
| `database/queries.py` | 150 lines. `get_recent_transactions` at line 84 selects `date, description, category, amount` and builds a 4-key dict. Helpers open/close their own connection; `insert_expense` uses `with conn:` and returns `lastrowid`. Module docstring line 6 says "insert_expense() is the single write path." |
| `database/db.py` | `get_db()` sets `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`. Seed data: 8 expenses for the demo user, each already 2 dp. No `updated_at` column. |
| `templates/add_expense.html` | 63 lines; `.auth-section` → `.auth-container` → `.auth-header` → `.auth-card` → error div → `<form method="POST" action="{{ url_for('add_expense') }}">` → 4 `.form-group`s → `.btn-submit` → `.auth-switch` cancel link. Direct copy source for the edit page. |
| `templates/profile.html` | Transactions table at lines ~70–95: 4 `<th scope="col">` (last is `class="tx-amount"`), 4 `<td>` per row (loop variable is `t`), empty-state `<td class="empty-note" colspan="4">` at line 89. |
| `static/css/style.css` | `.table-wrap` 843, `.tx-table` 845, `th` 847, `td` 859, hover 865, `.tx-date` 867, `.tx-table th/td.tx-amount` 869–875. Tokens `--ink-muted`, `--ink-soft`, `--accent`, `--text-sm`, `--space-*` all exist. No `.tx-*` link rule yet. |
| Tests that constrain us | `test_backend_connection.py:58` asserts `set(item) == {"date", "description", "category", "amount"}` — **this breaks when `id` is added**. `test_backend_connection.py:124` counts `<td class="tx-date">` and `test_date_filter.py:88,799` regex `<td class="tx-date">` / `<td class="tx-amount">` — all **unaffected** by one extra trailing `<td>`. |
| Fixtures | `tests/conftest.py`: `temp_db`, `app`, `client`, `demo_user_id` (8 seeded expenses), `blank_user_id` (user with none). Login idiom: `with client.session_transaction() as sess: sess["user_id"] = user_id`. |

---

## 3. Decisions taken while planning

| # | Decision | Why |
|---|---|---|
| D1 | Extract Step 7's validation into `_parse_expense_form(form_data)` in `app.py` and call it from both views | The spec requires identical rules; copying them guarantees drift (this review already caught one missing rule). The helper is pure, has no Flask imports beyond `request.form`-shaped objects, and Step 7's tests pin its behaviour. |
| D2 | `_parse_expense_form` returns `(form, error, amount, iso_date)` | Call sites need the sticky dict for the re-render and the normalised amount/date for the write. Docstring states `amount`/`iso_date` are only valid when `error is None`. |
| D3 | 404 via `abort(404)` (Flask's default body), no custom `404.html` | No error template exists in the project; adding one is Step 8 scope creep. `TESTING=True` still returns a 404 response (HTTPExceptions are handled, not propagated), so route tests can assert the status code. |
| D4 | Fetch the expense **before** validating on POST | A foreign-owned or deleted id must be a 404, not a validation round-trip that echoes another user's data back into a form. |
| D5 | `update_expense` returns `rowcount`; `0` → `abort(404)` | Covers the GET/POST race (row deleted in between) and makes a forged id a 404 instead of a fake success flash. |
| D6 | Actions column is **last** (Date, Description, Category, Amount, Actions), right-aligned, `class="tx-actions"`, link class `tx-action-link` | Keeps the money column where users expect it and needs one token-based CSS block. If the right-aligned Amount looks pinched in review, the fallback is swapping Amount and Actions — a two-line template change, noted in §7. |
| D7 | GET prefills `amount` with `f"{expense['amount']:.2f}"` | Seed/inserted values are 2 dp, but a manually inserted `12.5` must render `12.50` in a money form. Sticky POST values are passed through verbatim. |
| D8 | Form template reuses `expense_id` (not the whole `expense` dict) and the same `amount`/`category`/`date`/`description` variable names as Step 7 | Lets the view do `**form` exactly like `add_expense`, so the two templates differ only in title/labels/action. |
| D9 | Keep the route parameter named `id` | Matches the shipped delete stub and Flask convention; the `<int:...>` converter already gives a 404 for `/expenses/abc/edit`. Local shadowing of the builtin is pre-existing style in this file. |
| D10 | Update `AGENTS.md` test count while there | It still says "83 tests"; the suite is 105 now and will grow. Leaving it stale would repeat the drift this review just fixed. |

---

## 4. Implementation steps (in order)

### 4.1 `database/queries.py` — three edits

**a) Docstring (lines 1–7)** — the "single write path" claim becomes false:

```python
"""Query helpers for Spendly. No Flask imports.

Every function opens its own connection via get_db() and closes it before
returning, so callers never manage connections. Optional date_from/date_to
(ISO YYYY-MM-DD, inclusive) narrow every read helper to that range.
insert_expense() and update_expense() are the two write paths.
"""
```

**b) `get_recent_transactions` (line 84)** — add `id` to the select and the dict:

```python
            "SELECT id, date, description, category, amount FROM expenses "
```
```python
    return [
        {
            "id": row["id"],
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]
```

**c) New helpers** — append after `insert_expense` (keeps write paths together):

```python
def get_expense_by_id(expense_id, user_id):
    """One expense as a dict, or None if missing or not owned by `user_id`."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return {
        "id": row["id"],
        "amount": row["amount"],
        "category": row["category"],
        "date": row["date"],
        "description": row["description"],
    }


def update_expense(expense_id, user_id, amount, category, date,
                   description=None):
    """Update one owned expense; return the number of rows changed (0 or 1)."""
    conn = get_db()
    try:
        with conn:  # commits on success, rolls back on error
            cursor = conn.execute(
                "UPDATE expenses SET amount = ?, category = ?, date = ?, "
                "description = ? WHERE id = ? AND user_id = ?",
                (amount, category, date, description, expense_id, user_id),
            )
        return cursor.rowcount
    finally:
        conn.close()
```

Both statements carry `id = ? AND user_id = ?`; a foreign row is
indistinguishable from a missing one. `description=None` writes SQL `NULL`.

### 4.2 `app.py` — imports, shared validator, view, placeholder removal

**Imports**

```python
from flask import (
    Flask,
    abort,          # new
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
```
```python
from database.queries import (
    get_category_breakdown,
    get_expense_by_id,      # new
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    insert_expense,
    update_expense,         # new
)
```

**Extract the validator** — place it in the "Date filter helpers" area or a new
`# Expense form helpers` block above the routes, and replace the inline block in
`add_expense` with a call. Behaviour, rule order, and strings must not change:

```python
def _parse_expense_form(form_data):
    """Normalise + validate the add/edit expense form.

    Returns (sticky fields, error-or-None, amount, iso_date). `amount` and
    `iso_date` are only meaningful when `error` is None.
    """
    form = {
        "amount": (form_data.get("amount") or "").strip(),
        "category": form_data.get("category") or "",
        "date": (form_data.get("date") or "").strip(),
        "description": (form_data.get("description") or "").strip(),
    }

    # round() first: round(0.004, 2) is 0.0, so validating the raw value
    # would let a sub-cent amount through as zero. float() also parses
    # 'nan'/'inf', hence the isfinite guard.
    amount = None
    try:
        amount = round(float(form["amount"]), 2)
    except ValueError:
        pass

    iso_date = _parse_iso_date(form["date"])

    error = None
    if amount is None or not math.isfinite(amount) or amount <= 0:
        error = "Please enter an amount greater than 0."
    elif form["category"] not in CATEGORIES:
        error = "Please choose a valid category."
    elif iso_date is None:
        error = "Please enter a valid date (YYYY-MM-DD)."
    elif len(form["description"]) > 200:
        error = "Description must be 200 characters or fewer."

    if error is not None:
        return form, error, None, None
    return form, error, amount, iso_date
```

`add_expense`'s POST branch then reads:

```python
        form, error, amount, iso_date = _parse_expense_form(request.form)
        if error is None:
            try:
                insert_expense(
                    session["user_id"], amount, form["category"], iso_date,
                    form["description"] or None,
                )
            except sqlite3.IntegrityError:
                session.clear()
                flash("Please sign in again.", "error")
                return redirect(url_for("login"))
            flash("Expense added.", "success")
            return redirect(url_for("profile"))

        return render_template("add_expense.html", categories=CATEGORIES,
                               error=error, **form), 400
```

The INSERT previously received `round(amount, 2)`; the helper now returns the
rounded value, so pass it straight through.

**New view** — delete the placeholder from the placeholder block and place the
real view directly after `add_expense()`:

```python
@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    if get_user_by_id(user_id) is None:
        # Stale session for a user that no longer exists.
        session.clear()
        flash("Please sign in again.", "error")
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "POST":
        form, error, amount, iso_date = _parse_expense_form(request.form)
        if error is None:
            changed = update_expense(id, user_id, amount, form["category"],
                                     iso_date, form["description"] or None)
            if changed == 0:
                # Row deleted between the GET and this POST.
                abort(404)
            flash("Expense updated.", "success")
            return redirect(url_for("profile"))

        return render_template("edit_expense.html", categories=CATEGORIES,
                               expense_id=id, error=error, **form), 400

    form = {
        "amount": f"{expense['amount']:.2f}",
        "category": expense["category"],
        "date": expense["date"],
        "description": expense["description"] or "",
    }
    return render_template("edit_expense.html", categories=CATEGORIES,
                           expense_id=id, error=None, **form)
```

Leave the `delete_expense` stub and the placeholder banner intact (the banner
now covers only delete).

### 4.3 `templates/edit_expense.html` (new)

Same skeleton as `add_expense.html`; only the title, heading, subtitle, form
`action`, submit label and `expense_id` differ.

```jinja
{% extends "base.html" %}

{% block title %}Edit expense — Spendly{% endblock %}

{% block content %}

<section class="auth-section">
    <div class="auth-container">

        <div class="auth-header">
            <h1 class="auth-title">Edit expense</h1>
            <p class="auth-subtitle">Fix the details — your ledger updates in place.</p>
        </div>

        <div class="auth-card">
            {% if error %}
            <div class="auth-error" role="alert">{{ error }}</div>
            {% endif %}

            <form method="POST" action="{{ url_for('edit_expense', id=expense_id) }}">
                <div class="form-group">
                    <label for="amount">Amount (₹)</label>
                    <input type="number" id="amount" name="amount"
                           class="form-input" placeholder="250.00"
                           step="0.01" min="0.01" inputmode="decimal"
                           value="{{ amount or '' }}" required autofocus>
                </div>
                <div class="form-group">
                    <label for="category">Category</label>
                    <select id="category" name="category" class="form-input" required>
                        {% for option in categories %}
                        <option value="{{ option }}"
                            {%- if option == category %} selected{% endif %}>{{ option }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label for="date">Date</label>
                    <input type="date" id="date" name="date" class="form-input"
                           value="{{ date or '' }}" required>
                </div>
                <div class="form-group">
                    <label for="description">Description <span>(optional)</span></label>
                    <input type="text" id="description" name="description"
                           class="form-input" placeholder="Lunch with friends"
                           maxlength="200" value="{{ description or '' }}">
                </div>
                <button type="submit" class="btn-submit">Save Changes</button>
            </form>
        </div>

        <p class="auth-switch">
            <a href="{{ url_for('profile') }}">Cancel and go back</a>
        </p>

    </div>
</section>

{% endblock %}
```

No new CSS: `.auth-*`, `.form-group`, `.form-input`, `.btn-submit` all reused.

### 4.4 `templates/profile.html` — Actions column

Header (line ~76) — append one header cell:

```jinja
                                <th scope="col" class="tx-amount">Amount</th>
                                <th scope="col" class="tx-actions">Actions</th>
```

Body (line ~85) — append one cell to the existing row:

```jinja
                                <td class="tx-amount">₹{{ "%.2f"|format(t.amount) }}</td>
                                <td class="tx-actions">
                                    <a class="tx-action-link" href="{{ url_for('edit_expense', id=t.id) }}">Edit</a>
                                </td>
```

Empty state (line 89) — **required** or the cell won't span the table:

```jinja
                                <td class="empty-note" colspan="5">No transactions in this range.</td>
```

Loop variable stays `t`; `t.id` only exists because of §4.1b.

### 4.5 `static/css/style.css` — one block after `.tx-amount`

```css
.tx-table th.tx-actions,
.tx-table td.tx-actions {
    text-align: right;
    white-space: nowrap;
}

.tx-action-link {
    color: var(--ink-muted);
    text-decoration: none;
    font-size: var(--text-sm);
    font-weight: 500;
}

.tx-action-link:hover {
    color: var(--accent);
    text-decoration: underline;
}
```

Tokens only — no new hex, radius, spacing value, or shadow. The global
`:focus-visible` ring already covers the link.

### 4.6 `tests/test_backend_connection.py` — the one assertion that breaks

Line 58:

```python
        assert set(item) == {"id", "date", "description", "category", "amount"}
```

Optionally strengthen the same test with `assert item["id"] == ordered_ids[i]`
(ordering is `date DESC, id DESC`), but the key-set change is the mandatory part.

### 4.7 `AGENTS.md` — keep the map honest

- Route table: `| GET /expenses/<id>/edit |` → change route to
  `` `GET` / `POST /expenses/<id>/edit` `` and status to
  `Implemented — Step 8 (owned fetch, 404 for foreign/missing, 400 on invalid, redirects to /profile)`.
- Gotchas: the placeholder-route bullet must now name only
  `/expenses/<id>/delete`.
- `database/queries.py` bullet: add `get_expense_by_id` / `update_expense` and
  change "plus `insert_expense`, the single write path" to "plus
  `insert_expense` / `update_expense`, the two write paths".
- Commands block: update the pytest count after the new module lands.
- Add one line to the `/profile` gotcha list: transaction rows carry Edit links
  built from `get_recent_transactions[].id` (latest 10 only).

---

## 5. Tests — `tests/test_edit_expense.py`

Reuse the `test_add_expense.py` helper style (regex parsers, `_redirect_path`,
`_expenses_for`) instead of ad-hoc string checks. Local helper for the ownership
cases — a second user who owns one expense:

```python
def _other_user_expense():
    """Create a second user with one expense; return (user_id, expense_id)."""
    conn = db_module.get_db()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Other User", "other@spendly.com", "x"),
            )
            user_id = cursor.lastrowid
            cursor = conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, 7.0, "Other", "2026-03-01", "Someone else's"),
            )
        return user_id, cursor.lastrowid
    finally:
        conn.close()
```

| # | Test | Assertion |
|---|---|---|
| 1 | `get_expense_by_id` own row | dict with keys exactly `{id, amount, category, date, description}`; values match the stored row |
| 2 | `get_expense_by_id` wrong user | `None` |
| 3 | `get_expense_by_id` missing id | `None` |
| 4 | `update_expense` own row | returns `1`; amount/category/date/description all updated; `id`/`user_id` unchanged |
| 5 | `update_expense` wrong user | returns `0`; every column of the row unchanged |
| 6 | `update_expense` `description=None` | returns `1`; stored `description IS NULL` |
| 7 | `get_recent_transactions` includes id | each dict's `id` matches a real row; ordering and key set unchanged otherwise |
| 8 | GET unauthenticated | 302, path `/login` |
| 9 | GET own expense | 200; `<form method="POST">`; `amount` is `"12.50"` for a `12.5` row; date/description values present; exactly one `selected` option and it is the stored category |
| 10 | GET other user's expense | 404 |
| 11 | GET missing id | 404 |
| 12 | GET `/expenses/abc/edit` | 404 (converter) |
| 13 | POST unauthenticated | 302 to `/login`; row unchanged |
| 14 | POST valid | 302 to `/profile`; all four fields updated; flash `Expense updated.` queued; other rows untouched |
| 15 | POST other user's expense | 404; that row unchanged |
| 16 | POST missing id | 404 |
| 17 | POST missing amount | 400; amount error in body; submitted category/date still rendered |
| 18 | POST `amount=0` | 400 + amount error |
| 19 | POST `amount=-5` | 400 + amount error |
| 20 | POST `amount=abc` | 400 + amount error |
| 21 | POST `amount=nan` | 400 + amount error |
| 22 | POST `amount=12.344` | 302; stored `12.34` |
| 23 | POST invalid category `Pets` | 400 + category error; row unchanged |
| 24 | POST invalid date `20-03-2026` | 400 + date error |
| 25 | POST unpadded date `2026-3-5` | 302; stored `2026-03-05` |
| 26 | POST blank description | 302; stored `NULL` |
| 27 | POST 201-char description | 400 + description error |
| 28 | profile shows edit links | body contains `/expenses/<id>/edit` for each seeded row |
| 29 | profile empty state | contains `colspan="5"` |

Plus the mandatory change in `tests/test_backend_connection.py` (§4.6). Shipped
as 34 test cases (parametrised): 139 total, all green.

Deliberately **not** tested: Flask's default 404 page markup, flash styling,
link CSS, ownership-guard behaviour of `insert_expense` (already covered).

---

## 6. Verification

```bash
# 1. Refactor checkpoint — Step 7 must be untouched behaviourally
uv run pytest tests/test_add_expense.py tests/test_backend_connection.py

# 2. Full suite
uv run pytest

# 3. Dev server (only if port 5001 is free)
uv run python app.py
```

Manual smoke (`demo@spendly.com` / `demo123`):

1. `/profile` → each row shows an "Edit" link on the right; the Amount column
   still lines up and the empty-state user (blank@spendly.com, if seeded via a
   test) shows a full-width "No transactions" cell.
2. Edit a row → amount `12.50`, category pre-selected, date + description
   filled; change to `99.00 / Health / today / "Edited"` → back on `/profile`
   with the success flash, totals and breakdown updated.
3. Submit amount `0` → 400 re-render with the error and the other fields as
   submitted (**not** the original values).
4. Log out → `/expenses/1/edit` (GET and POST) → `/login`.
5. Log in as a different account (or use `blank_user_id`) and hit
   `/expenses/<demo row>/edit` → 404 on both methods.
6. Narrow to ~360 px → the fifth column does not force horizontal scroll on
   the card (`.table-wrap` scrolls instead); phone-width form unchanged.

---

## 7. Risks / out of scope

| Item | Note |
|---|---|
| Step 7 refactor (§4.2) | The only behavioural risk in the plan. The extracted helper keeps rule order and strings identical; `test_add_expense.py` (40 tests) is the safety net — run it before touching the edit route. |
| Actions column placement (D6) | Right-aligned Actions sits to the right of the right-aligned Amount, so Amount moves inboard. If review dislikes it, swap the two cells — template-only change. |
| `get_recent_transactions` key change | Only one existing assertion breaks (verified by grep: `set(item)` at `test_backend_connection.py:58`). The regex-based profile tests only read `tx-date`/`tx-amount` cells. |
| 404 vs 403 | 404 is deliberate (no id enumeration). Documented in the spec; no UI copy involved. |
| Filter lost after save | Redirect is a bare `/profile` (parity with Step 7); a filtered view is not restored. Accepted trade-off, spec §"Out of scope". |
| No CSRF tokens | Consistent with every existing form in this codebase; still a real gap, out of scope for Step 8. |
| Out of scope | Step 9 delete, `updated_at`/audit columns, optimistic locking, "unsaved changes" prompt, pagination, custom 404 template, carrying `next`/filters through login. |

---

## 8. Definition of done → evidence

| DoD bullet | Where it is proven |
|---|---|
| Logged-out GET/POST → `/login` | tests 8, 13 |
| Missing / malformed / foreign id → 404 | tests 10–12, 15, 16 |
| GET prefilled (2-dp amount, selected category, date, description) | test 9 |
| Valid POST updates in place, flashes, redirects | test 14 + manual smoke 2 |
| Other users' rows untouchable (SQL guard both statements) | tests 2, 5, 10, 15 |
| Bad amount variants → 400 + sticky values | tests 17–21 |
| Invalid category / date → 400 | tests 23, 24 |
| Optional / over-long description | tests 26, 27 |
| Canonical date, 2-dp stored amount | tests 22, 25 |
| Actions column with correct links + `colspan="5"` | tests 28, 29 + manual smoke 1 |
| `uv run pytest` green incl. updated key-set test | §6 step 2, §4.6 |
| `AGENTS.md` accurate | §4.7 |
