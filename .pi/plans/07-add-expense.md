# Implementation Plan — Step 7: Add Expense

**Spec:** `.pi/specs/07-add-expense.md`
**Branch:** `feature/add-expense` (already checked out — no branch work needed)
**Files to change:** `app.py`, `database/queries.py`, `templates/profile.html`,
`static/css/style.css` (one existing rule), `AGENTS.md`
**Files to create:** `templates/add_expense.html`, `tests/test_add_expense.py`
**Status:** plan only — no application code changed (planning mode)
**Locked decisions:** one view `add_expense` with `GET, POST`; auth guard mirrors
`/profile` (no `next` param, no flash); validation failures re-render with
`error` + sticky values at **400** (same as `register`/`login`); success uses
flash + `redirect(url_for("profile"))`; category options come from `CATEGORIES`;
`insert_expense` is the only write helper in `database/queries.py`; form reuses
the auth card + `.form-input` / `.btn-primary` / `.btn-ghost` — **no new CSS
component**; Step 8/9 placeholders stay untouched.

---

## 1. Objective

Let a signed-in user record an expense from a dedicated page, without adding a
dependency, a client-side framework, or a new styling system.

1. `database/queries.py` — `insert_expense(...)` (parameterised insert, returns
   the new row id) + docstring fix (`read-only` → query helpers, one write path).
2. `app.py` — replace the `GET /expenses/add` placeholder with a `GET, POST`
   view: guard → validate → insert → flash + redirect; on failure re-render.
3. `templates/add_expense.html` — new page reusing the register/login auth card.
4. `templates/profile.html` — "Add Expense" button; `static/css/style.css` —
   one-line layout tweak to `.profile-header` so the button sits on the title row.
5. `tests/test_add_expense.py` — 2 helper unit tests + route tests covering
   every DoD bullet. Existing 65 tests stay green.

---

## 2. Current state (verified)

| Item | Verified state |
|---|---|
| Branch / git | On `feature/add-expense`; working tree has one untracked file (`.pi/specs/07-add-expense.md`). |
| Test baseline | `uv run pytest` → **65 passed**: 15 located in `test_backend_connection.py`, 50 in `test_date_filter.py` (many parametrised). No other test files. |
| `app.py` — placeholder | `@app.route("/expenses/add")` → `return "Add expense — coming in Step 7"`, inside the "Placeholder routes — students will implement these" block (edit/delete stubs below it). |
| `app.py` — imports | `sqlite3`, `re`, and `from datetime import date, datetime` already imported. `flash`, `redirect`, `render_template`, `request`, `session`, `url_for` already imported. `get_db` imported. **`math` is not imported** — needed for `isfinite`. |
| `app.py` — conventions | `register()` / `login()` both compute a single `error`, return `render_template(..., error=error, ...), 400` and keep submitted values. `_parse_iso_date()` already does the "strptime → `.date().isoformat()`" normalisation the new route needs for the same lexicographic-SQLite reason. |
| `database/queries.py` | Module docstring says "Read-only query helpers for Spendly." Four helpers, each `get_db()` → `try/finally: conn.close()`, `?` placeholders. No insert path. |
| `database/db.py` | `CATEGORIES = ("Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other")` — module-level tuple, importable. `expenses.created_at` defaults to `datetime('now')`. |
| `templates/register.html` | `.auth-section` → `.auth-container` → `.auth-header` → `.auth-card` (`{% if error %}<div class="auth-error" role="alert">`) → `<form method="POST" action="/register">` → `.form-group` + `.form-input` → `.btn-submit`. Direct blueprint for the new page. |
| `templates/profile.html` | `.profile-header` contains only `<h1 class="profile-title">` + `<p class="profile-subtitle">`. Transactions card header is a bare `<h2 class="profile-card-title">` (no wrapper element). |
| `static/css/style.css` | `.profile-header { margin-bottom: 2rem; }` (line ~688) — currently a plain block, no flex. `.btn-primary` (358) and `.btn-ghost` (375) are `inline-block` and button-safe. `.auth-error` (508), `.form-group` (538), `.form-input` (548) all reusable as-is. No `.form-select` rule exists; a `<select class="form-input">` inherits border/padding/radius fine. |
| Test fixtures | `tests/conftest.py` provides `temp_db`, `app`, `client`, `demo_user_id`, `blank_user_id`. `test_date_filter.py` defines the login idiom: `with client.session_transaction() as sess: sess["user_id"] = user_id`. |

---

## 3. Decisions taken while planning

| # | Decision | Why |
|---|---|---|
| D1 | "Add Expense" lives in the **page header**, not the transactions card header | The card has no header wrapper; nesting a button next to the `<h2>` would need a new `.profile-card-head` class. `.profile-header` only needs `display: flex` + `flex-wrap: wrap` on an existing rule, and a page-level primary action is the more conventional spot. (Spec's DoD says "the Add Expense button on the profile page" — still satisfied.) |
| D2 | Success flash is `"Expense added."`, reuse the existing `flash-stack` | Matches the short, past-tense tone of `"Account created successfully…"` / `"Welcome back, …"`. No new template markup. |
| D3 | `description` stays `<input type="text" maxlength="200">`, not a `<textarea>` | One-line expense notes; keeps it inside `.form-input`'s styling and mirrors the server-side 200-char rule. |
| D4 | Redirect to bare `/profile` (no date params carried over) | Simplest; the unfiltered view is the default, so the new row is guaranteed visible even if the user had a filter active before. Carrying filter state would need hidden fields or session state — over-engineering for Step 7. |
| D5 | Category `<select>` defaults to the first category (`Food`), no placeholder option | Keeps the option list exactly the 7 `CATEGORIES` values (simple test assertion) and no extra validation branch. |
| D6 | Amount is `round(x, 2)` before insert; `math.isfinite` guard | `float("nan")`/`1e999` parse without raising; `nan > 0` is false but `inf` would be stored as a junk `REAL`. Rounding keeps the stored `REAL` aligned with `step="0.01"`. |

---

## 4. Implementation steps (in order)

### 4.1 `database/queries.py` — `insert_expense`

Append after `get_category_breakdown`; adjust the module docstring first line.

```python
def insert_expense(user_id, amount, category, date, description=None):
    """Insert one expense for `user_id`; return the new row id."""
    conn = get_db()
    try:
        with conn:  # commits on success, rolls back on error
            cursor = conn.execute(
                "INSERT INTO expenses "
                "(user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, category, date, description),
            )
        return cursor.lastrowid
    finally:
        conn.close()
```

Docstring header change:

```python
"""Query helpers for Spendly. No Flask imports.

Every function opens its own connection via get_db() and closes it before
returning, so callers never manage connections. Optional date_from/date_to
(ISO YYYY-MM-DD, inclusive) narrow every read helper to that range.
insert_expense() is the single write path.
"""
```

### 4.2 `app.py` — the view

- Add `import math` next to `import os`, `import re`, `import sqlite3`.
- Add `insert_expense` to the `from database.queries import (...)` block (keep
  alphabetical) and `from database.db import CATEGORIES, get_db, init_db, seed_db`.
- Delete the placeholder `add_expense` from the placeholder block and place the
  real view **above** that banner, right after `profile()` (route order reads
  landing → auth → legal → logout → profile → add → stubs).

```python
@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    # Pre-filled values: blank on GET (date defaults to today), sticky on error.
    form = {
        "amount": "",
        "category": CATEGORIES[0],
        "date": date.today().isoformat(),
        "description": "",
    }

    if request.method == "POST":
        form = {
            "amount": (request.form.get("amount") or "").strip(),
            "category": request.form.get("category") or "",
            "date": (request.form.get("date") or "").strip(),
            "description": (request.form.get("description") or "").strip(),
        }

        error = None
        amount = None
        try:
            amount = float(form["amount"])
        except ValueError:
            error = "Please enter an amount greater than 0."
        else:
            if not math.isfinite(amount) or amount <= 0:
                error = "Please enter an amount greater than 0."

        if error is None and form["category"] not in CATEGORIES:
            error = "Please choose a valid category."

        iso_date = None
        if error is None:
            try:
                iso_date = (datetime.strptime(form["date"], "%Y-%m-%d")
                            .date().isoformat())
            except ValueError:
                error = "Please enter a valid date (YYYY-MM-DD)."

        if error is None and len(form["description"]) > 200:
            error = "Description must be 200 characters or fewer."

        if error is None:
            try:
                insert_expense(
                    session["user_id"],
                    round(amount, 2),
                    form["category"],
                    iso_date,
                    form["description"] or None,
                )
            except sqlite3.IntegrityError:
                # Stale session for a user that no longer exists.
                session.clear()
                flash("Please sign in again.", "error")
                return redirect(url_for("login"))
            flash("Expense added.", "success")
            return redirect(url_for("profile"))

        return render_template("add_expense.html", categories=CATEGORIES,
                               error=error, **form), 400

    return render_template("add_expense.html", categories=CATEGORIES,
                           error=None, **form)
```

Notes for the implementer:
- `**form` supplies template vars `amount`, `category`, `date`, `description`
  — the same names the template reads, so sticky values need no extra mapping.
- Rejecting before insert is the only validation point; the template's
  `required`/`min`/`step`/`maxlength` are UX sugar, not the contract.
- Future dates are accepted on purpose (no `max`, no server check).

### 4.3 `templates/add_expense.html` (new)

Mirror `register.html`'s structure exactly; reuse classes only.

```jinja
{% extends "base.html" %}

{% block title %}Add expense — Spendly{% endblock %}

{% block content %}

<section class="auth-section">
    <div class="auth-container">

        <div class="auth-header">
            <h1 class="auth-title">Add an expense</h1>
            <p class="auth-subtitle">Log what you spent — it lands in your ledger.</p>
        </div>

        <div class="auth-card">
            {% if error %}
            <div class="auth-error" role="alert">{{ error }}</div>
            {% endif %}

            <form method="POST" action="{{ url_for('add_expense') }}">
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
                <button type="submit" class="btn-submit">Save Expense</button>
            </form>
        </div>

        <p class="auth-switch">
            <a href="{{ url_for('profile') }}">Cancel and go back</a>
        </p>

    </div>
</section>

{% endblock %}
```

- `.auth-title` is serif (display font) — consistent with "page titles are
  display font".
- Submit uses `.btn-submit` (full-width, same as register/login) so the card
  reads as one form family; the spec's `.btn-primary` would be visually odd
  inside a `.auth-card`.
- Cancel as an `.auth-switch` link keeps the card footprint tight (cancel +
  submit on one row would need a new flex rule).
- No new CSS. If the `<select>` height differs from the inputs on review, fix
  with one `select.form-input { ... }` rule built from existing tokens — do not
  touch `:root`.

### 4.4 `templates/profile.html` — the button

Wrap the title/subtitle and add the link:

```jinja
<header class="profile-header">
    <div>
        <h1 class="profile-title">Your profile</h1>
        <p class="profile-subtitle">A snapshot of where your money went.</p>
    </div>
    <a class="btn-primary profile-add" href="{{ url_for('add_expense') }}">Add Expense</a>
</header>
```

### 4.5 `static/css/style.css` — one rule

`.profile-header` gains flex + wrap (no new selectors, no new tokens):

```css
.profile-header {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-3);
    margin-bottom: 2rem;
}
```

`flex-wrap` handles the ≤600px case without a media-query entry. `.profile-add`
gets **no** rule — it is a marker class only; if vertical rhythm next to the
2rem title needs a nudge, add `padding: var(--space-2) var(--space-4);` under it
using existing tokens.

### 4.6 `AGENTS.md` — keep the map honest

- Implemented-vs-stub table: `GET /expenses/add` → `Implemented — Step 7
  (logged-in form, `POST` inserts + redirects to `/profile`)`.
- `database/queries.py` bullet: replace "read-only query helpers" with "query
  helpers" and mention `insert_expense` as the single write path.
- Commands block: update the pytest count after the new file lands.

---

## 5. Tests — `tests/test_add_expense.py`

Reuse `conftest.py` fixtures. Add a local login helper (same as
`test_date_filter.py`) plus a small row-count helper:

```python
def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client

def _expense_count(user_id):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
    finally:
        conn.close()
```

| # | Test | Assertion |
|---|---|---|
| 1 | `test_insert_expense_round_trip` | returned id is truthy; SELECT returns `50.0`/`Food`/`2026-03-20`/`Lunch` |
| 2 | `test_insert_expense_null_description` | `description` is `None` in a fresh SELECT |
| 3 | `test_add_page_requires_login` (GET) | 302, `Location` ends `/login` |
| 4 | `test_add_page_renders_form` | 200; all 7 categories in body; `method="POST"`; `date` value == `date.today().isoformat()` |
| 5 | `test_post_requires_login` | 302 to `/login` and `_expense_count` unchanged |
| 6 | `test_post_valid_expense_redirects_and_saves` | 302 to `/profile`; count +1; row has `amount == 50.0`, canonical date |
| 7 | `test_post_missing_amount` | 400; body contains "amount greater than 0"; submitted category/date still in body |
| 8 | `test_post_zero_amount` | 400 + error text |
| 9 | `test_post_nonnumeric_amount` | 400 + error text (`abc`) |
| 10 | `test_post_nan_amount` | 400 + error text (`nan`) |
| 11 | `test_post_invalid_category` | 400 + "valid category"; no row inserted |
| 12 | `test_post_invalid_date` | 400 + "valid date" (`20-03-2026`) |
| 13 | `test_post_without_description` | 302; `description IS NULL` |
| 14 | `test_post_long_description` | 400 + "200 characters or fewer" |

Deliberately **not** tested: HTML escaping of the description (Jinja default),
button CSS, flash wording, unpadded-date input normalisation (already covered by
`test_parse_iso_date` for the same helper logic). Keep the suite focused on the
contract.

---

## 6. Verification

```bash
uv run pytest                      # 65 existing tests + the new module, all green
uv run python app.py               # port 5001 — check only if no server running
```

Manual smoke (logged in as `demo@spendly.com` / `demo123`):
1. `/profile` → "Add Expense" → form with today's date and `Food` selected.
2. Submit `12.34 / Health / today / "Chai"` → back on `/profile`, success flash,
   row at the top of Recent transactions, totals and breakdown updated.
3. Submit `0` → 400-style re-render with the error and the other fields intact.
4. Logged out → `/expenses/add` (GET and POST) → `/login`.
5. Narrow the window to ~360px → header button wraps under the title, no
   overflow; table and form unchanged.

---

## 7. Risks / out of scope

| Item | Note |
|---|---|
| Header button placement (D1) | Deviates from the spec's "transactions card header". One extra flex rule vs a new card-head component — say the word if you want the card-header variant instead. |
| `.profile-header` flex change | Only `templates/profile.html` uses the class (verified by grep), so the rule change is contained. |
| Native `<select>` styling | `.form-input` was written for `<input>`; height/arrow rendering differs per browser. Cosmetic only; fix with a single token-based rule if it looks off. |
| No `next`-param return flow | A logged-out POST is lost (redirect to login). Intentional: same as `/profile`, and no user data is silently dropped mid-write. |
| Out of scope | Steps 8–9 edit/delete routes, editing/undo of a saved expense, CSRF tokens (none of the existing forms have them), server-side pagination. |

---

## 8. Definition of done → evidence

| DoD bullet | Where it is proven |
|---|---|
| Logged-out GET/POST → `/login` | tests 3, 5 |
| Logged-in form with 4 fields, date = today | tests 4, 6 |
| Dropdown from `CATEGORIES` (7 options) | test 4 + template loop |
| Valid POST redirects, flashes, row visible | test 6 + manual smoke 2 |
| Bad amount → error + sticky values | tests 7–10 + manual smoke 3 |
| Invalid category / date → error | tests 11, 12 |
| Description optional / >200 rejected | tests 13, 14 |
| Canonical date, 2-dp amount stored | test 6 |
| Profile button navigates to form | `.profile-header` link + test 4 (route exists) |
| `uv run pytest` green | §6, 65 existing untouched |
