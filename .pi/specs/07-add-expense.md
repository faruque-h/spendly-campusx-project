# Spec: Add Expense

## Overview
Step 7 lets a logged-in user submit a new expense through a dedicated form page
at `/expenses/add`. The GET-only placeholder route in `app.py` becomes a
GET + POST handler that validates the form, inserts one row into the `expenses`
table, and redirects to `/profile` (post/redirect/get). A small
`insert_expense` helper is added to `database/queries.py`, and an "Add Expense"
link is added to `profile.html` so the form is reachable.

The form is plain server-rendered HTML with no JavaScript: validation errors
re-render the page with the submitted values still in the fields.

## Depends on
- Step 1: Database setup (`expenses` table with `user_id`, `amount`, `category`,
  `date`, `description`, `created_at`)
- Step 3: Login / Logout (`session["user_id"]` is set and checked)
- Step 5: `/profile` renders live per-user data (`database/queries.py` wired up)

Step 6 (date filter) is **not** a dependency: the success redirect goes to a
bare `/profile`, so the new expense is always visible in the transaction list.

## Routes
One view function, `add_expense`, with `methods=["GET", "POST"]`:

- `GET /expenses/add` — render the empty form — logged-in only
- `POST /expenses/add` — validate and insert — logged-in only

Auth guard (both methods, first line of the view, mirroring `/profile`):

```python
if session.get("user_id") is None:
    return redirect(url_for("login"))
```

No `next`/return-to-URL parameter and no flash on the guard — keep parity with
`/profile` rather than inventing a redirect-back flow.

## Database changes
None. The `expenses` table already has every required column, `user_id` is a
foreign key with `PRAGMA foreign_keys = ON` in `get_db()`, and `created_at`
defaults to `datetime('now')`.

## Query helper
Add to `database/queries.py`:

```python
def insert_expense(user_id, amount, category, date, description=None):
    """Insert one expense for `user_id`; return the new row id."""
```

- One `INSERT INTO expenses (user_id, amount, category, date, description)
  VALUES (?, ?, ?, ?, ?)` — placeholders only, never string interpolation.
- Opens `get_db()`, uses `with conn:` to commit, closes the connection in
  `finally` (same shape as the helpers in `app.py`/`queries.py`).
- `description` is stored exactly as passed; `None` becomes SQL `NULL`.
- Returns `cursor.lastrowid`.
- No Flask imports.

The module docstring currently says "Read-only query helpers"; update it to say
the module holds query helpers and note that `insert_expense` is the single
write path (see AGENTS update below).

## Validation (POST)
Follow the `register`/`login` convention: compute a single `error` string
(first failing rule wins), then either re-render with `error` or insert. Do not
flash validation errors — flash is reserved for the success message.

Submitted values are read with `request.form.get(..., "")` and used for the
re-render so the form stays sticky.

| Field | Rule | Error message |
|---|---|---|
| `amount` | strip; `float()` (catch `ValueError`); must be finite (`math.isfinite`) and `> 0` | `Please enter an amount greater than 0.` |
| `category` | must be in `CATEGORIES` from `database.db` | `Please choose a valid category.` |
| `date` | strip; `datetime.strptime(value, "%Y-%m-%d")` | `Please enter a valid date (YYYY-MM-DD).` |
| `description` | strip; blank → `None`; `len > 200` rejected | `Description must be 200 characters or fewer.` |

Notes:
- Reject non-finite amounts explicitly: `float("nan")` and `float("1e999")`
  parse without raising, and `nan > 0` is silently false while `inf` would be
  stored as a junk `REAL`.
- Normalise the date before inserting: `datetime.strptime(...).date().isoformat()`.
  `strptime` accepts unpadded input (`2026-3-5`), but the profile queries compare
  the TEXT `date` column lexicographically, so only zero-padded ISO may be stored.
- Store `round(amount, 2)` so the stored `REAL` matches the input's
  `step="0.01"`.
- Future dates are allowed on purpose (no `max` on the input, no server check).
  They simply show up under the profile's unfiltered "All Time" view.

Failure response: `render_template("add_expense.html", ..., error=error), 400`
— 400 matches `register`/`login` on this codebase (not 200).

Success response: `flash("Expense added.", "success")` then
`redirect(url_for("profile"))` — never render the form again after a write.

If the session points at a user row that no longer exists, the INSERT raises
`sqlite3.IntegrityError` (FK); catch it, `session.clear()`, and redirect to
`/login` instead of returning a 500.

## Templates

- **Create**: `templates/add_expense.html`
  - Extends `base.html`; sets `{% block title %}Add expense — Spendly{% endblock %}`
  - Reuses the existing centred auth layout (`.auth-section` / `.auth-container`
    / `.auth-card`) exactly like `register.html` — no new section/card styles
  - `{% if error %}<div class="auth-error" role="alert">{{ error }}</div>{% endif %}`
  - `<form method="POST" action="{{ url_for('add_expense') }}">` with
    `.form-group` + `.form-input` fields:
    - `amount` — `<input type="number" name="amount" step="0.01" min="0.01"
      inputmode="decimal" class="form-input" required autofocus
      value="{{ amount or '' }}">`
    - `category` — `<select name="category" class="form-input" required>`,
      looping `categories` (passed from the route as `CATEGORIES`); keep all 7
      options and no placeholder option, so the template and the constant can
      never drift apart
    - `date` — `<input type="date" name="date" class="form-input" required
      value="{{ date or '' }}">`; the route passes `date` pre-set to
      `date.today().isoformat()` on GET and to the submitted value on a
      validation failure (no separate `today` variable — one sticky field
      covers both cases)
    - `description` — `<input type="text" name="description" maxlength="200"
      class="form-input" value="{{ description or '' }}">` (optional, no
      `required`; `maxlength` mirrors the server-side 200-char rule)
  - Buttons (as shipped): submit is `class="btn-submit"` labelled "Save
    Expense" — full width, matching `register.html`/`login.html` inside the same
    `.auth-card`. Cancel is an `.auth-switch` paragraph link ("Cancel and go
    back") to `url_for('profile')`; there is no `.btn-ghost` button
  - Only if the native `<select>` looks visibly off with `.form-input`, add one
    `.form-select` rule built from existing tokens — no new colors, radii,
    spacing values, or shadows (not needed as shipped)
- **Modify**: `templates/profile.html`
  - Add an "Add Expense" link (`class="btn-primary profile-add"`, `href="{{`
    `url_for('add_expense') }}"`) in the page header (`.profile-header`), i.e.
    the page-level primary action, not inside the transactions card. The
    title/subtitle get wrapped in a plain `<div>` so the header can be a row
- **Modify**: `static/css/style.css`
  - `.profile-header` becomes a flex row (`display: flex`, `flex-wrap: wrap`,
    `align-items: flex-start`, `justify-content: space-between`, `gap:
    var(--space-3)`) so the button sits beside the title and wraps under it on
    narrow screens — no media query needed
  - `.profile-add` only tightens padding (`var(--space-2) var(--space-4)`)

No `base.html` change: the profile page is the app's hub, and a second navbar
CTA would duplicate the same action. The navbar keeps identity + sign out.

## Files to change
- `app.py`
  - Replace the `/expenses/add` placeholder with the GET + POST view described
    above and move it out of the "Placeholder routes" section; leave the
    `/expenses/<id>/edit` and `/expenses/<id>/delete` placeholders untouched
  - Import `insert_expense` from `database.queries` and `CATEGORIES` from
    `database.db`
- `database/queries.py` — add `insert_expense`, update the module docstring
- `templates/profile.html` — add the "Add Expense" link in `.profile-header`
- `static/css/style.css` — flex `.profile-header`, smaller `.profile-add`
- `AGENTS.md` — mark `/expenses/add` implemented in the route table and drop
  the "read-only" wording for `database/queries.py`

## Files to create
- `templates/add_expense.html`

## New dependencies
None.

## Rules for implementation
- No ORM — raw `sqlite3` through `get_db()`, `?` placeholders only
- Both GET and POST require a session; unauthenticated → `redirect(url_for("login"))`
- Category list comes from `CATEGORIES`; never re-declare it (template, view, or tests)
- Re-render with `error` + sticky values and status 400 on validation failure;
  redirect only after a successful insert
- All templates extend `base.html`; no inline styles; CSS tokens only (hex
  literals stay in `:root`)
- Currency is always ₹ — never £ or $ (the form itself shows no money figures,
  but the profile it redirects to must)
- Do not implement Steps 8–9

## Tests to write
File: `tests/test_add_expense.py` (uses the existing `temp_db`, `client`,
`demo_user_id`, `blank_user_id` fixtures; authenticate via
`client.session_transaction()`).

### Unit tests (helper)
| Function | Input | Expected output |
|---|---|---|
| `insert_expense` | `user_id`, `50.0`, `"Food"`, `"2026-03-20"`, `"Lunch"` | returns the new row id; a direct query returns the row with those values |
| `insert_expense` | `description=None` | row inserted with `description` stored as `NULL` |

### Route tests
`GET /expenses/add`
- unauthenticated → 302 to `/login`
- authenticated → 200; body contains all 7 category options; contains a
  `<form` with `method="POST"`; date input is pre-filled with today's ISO date

`POST /expenses/add`
- unauthenticated → 302 to `/login` (and no row is written)
- valid data (`amount=50.00`, `category=Food`, `date=2026-03-20`,
  `description=Lunch`) → 302 to `/profile`; one new row exists for that user
- missing amount → 400, body contains the amount error and the submitted
  category/date still pre-filled
- `amount=0` → 400 with error
- `amount=abc` → 400 with error
- `amount=nan` → 400 with error (non-finite guard)
- invalid category (`"Pets"`) → 400 with error
- invalid date (`"20-03-2026"`) → 400 with error
- no description → 302 to `/profile`; row stored with `description IS NULL`
- description longer than 200 chars → 400 with error

## Definition of done
- [ ] Logged-out `GET`/`POST /expenses/add` redirect to `/login`
- [ ] Logged-in `/expenses/add` shows amount, category, date (today), description
- [ ] Category dropdown is driven by `CATEGORIES` (Food, Transport, Bills,
      Health, Entertainment, Shopping, Other)
- [ ] A valid POST redirects to `/profile`, flashes a success message, and the
      expense appears in the transaction list
- [ ] Missing / zero / non-numeric / non-finite amount → 400, error shown,
      previous values retained
- [ ] Invalid category → 400 with error
- [ ] Invalid date → 400 with error
- [ ] Description is optional; over-200-char description → 400 with error
- [ ] The stored date is canonical `YYYY-MM-DD` and the amount is rounded to 2 dp
- [ ] "Add Expense" on `/profile` navigates to the form
- [ ] `uv run pytest` passes (existing 65 tests untouched)
