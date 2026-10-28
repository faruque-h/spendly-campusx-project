# Spec: Registration

## Overview

The registration step turns the `GET /register` page into a working sign-up flow.
A visitor submits their name, email, and password; the server validates the input, rejects duplicates, hashes the password with werkzeug, and inserts a new row into the existing `users` table. This is the first write path in Spendly and the prerequisite for every logged-in feature that follows (login, profile, expenses). On success the user is shown with a success message and then redirected to the login page. This is the entry point for all authenticated features that follow.
Authentication/session state itself is out of scope here — that is Step 3.

## Depends on

- Step 1 — Database setup (`database/db.py` with `users`, `expenses`, `get_db()`,
  `init_db()`, `seed_db()`). Confirmed implemented.
- `templates/register.html` and `GET /register` already exist and only need behaviour wired up.

## Routes

- `GET /register` — render the sign-up form — public *(already exists)*
- `POST /register` — validate the submitted form, create the user, redirect on
  success — public *(new)*

No other routes are added. `/login`, `/logout`, and `/profile` stay untouched.

## Database changes

No database changes.

Verified against `database/db.py`: the `users` table already has `id`, `name`,
`email` (`NOT NULL UNIQUE`), `password_hash` (`NOT NULL`), and `created_at`
(default `datetime('now')`). Registration only inserts into it.

## Templates

- **Create:** none
- **Modify:** `templates/register.html`
  - The `error` block stays, but must be reachable on `POST` validation failure.
    Give it `role="alert"` so screen readers announce it.
  - Repopulate the `name` and `email` fields with the previously submitted values
    (`value="{{ name or '' }}"`, `value="{{ email or '' }}"`) so users don't
    retype them after an error.
  - Add `minlength="8"` on the password input to match the server-side rule
    (the attribute does not exist yet).
  - Do **not** change the layout, classes, or add new CSS; the existing
    `auth-section` / `auth-card` / `form-group` classes are reused as-is.
- **Modify:** `templates/base.html`
  - Add one `get_flashed_messages(with_categories=true)` block inside
    `<main class="main-content">` so the post-registration success message is
    visible on `/login`. Nothing else in the template changes.
- **Modify:** `static/css/style.css`
  - Add `.flash-stack`, `.flash`, and `.flash--success` rules only.
  - Use existing `:root` variables (`--max-width`, `--accent`, `--accent-light`,
    `--radius-sm`); no new hex values.

## Files to change

- `app.py` — import `os`, `re`, `sqlite3`, `flash`, `request`, `redirect`,
  `url_for` (and `generate_password_hash`), add the `POST` method to the
  `register` view, and set
  `app.config["SECRET_KEY"] = os.environ.get("SPENDLY_SECRET_KEY", <dev fallback>)`
  so flash/session machinery works. The literal fallback is for local
  development only.
- `templates/register.html` — sticky values, `minlength`, `role="alert"`.
- `templates/base.html` — flash message block.
- `static/css/style.css` — flash styles using variables.

## Files to create

- None

## New dependencies

No new dependencies. `flask` and `werkzeug` are already declared in
`pyproject.toml`; `sqlite3` is in the standard library.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders, never f-strings or `%` in SQL)
- Passwords hashed with werkzeug (`generate_password_hash`); never store or log
  plaintext passwords
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Stub routes outside this step's scope must stay untouched
  (`/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`)
- Use `get_db()` and always close the connection in a `finally` block
- Normalise email with `email.strip().lower()` before the duplicate check and insert
- Do not auto-login the new user; session handling belongs to Step 3
- Duplicate detection must be case-insensitive: normalise with
  `.strip().lower()` and check `SELECT 1 FROM users WHERE lower(email) = ?`
  (SQLite's default `UNIQUE` collation is BINARY and would allow case variants)
- No CSRF protection is added in this step (no Flask-WTF dependency); this is an
  accepted risk to be revisited in a later hardening step
- No new length caps, no hand-rolled CSRF tokens, no extra dependencies

### Validation contract for `POST /register`

| Field | Rule | Error message |
|---|---|---|
| `name` | required, non-empty after strip | "Please enter your name." |
| `email` | required, must match a simple `local@domain.tld` pattern | "Please enter a valid email address." |
| `email` | must not already exist in `users`, compared case-insensitively (`lower(email) = ?`) | "An account with this email already exists." |
| `password` | required, at least 8 characters | "Password must be at least 8 characters." |

On any validation failure: re-render `register.html` with status `400`, passing
`error` plus the cleaned `name` and `email` back to the template.

On success: insert with
`INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)`,
commit, then `redirect(url_for("login"))`.

Race-condition guard: wrap the insert in `try/except sqlite3.IntegrityError` and
surface the duplicate-email error rather than a 500.

## Definition of done

- [ ] `GET /register` still renders the sign-up page at `http://localhost:5001/register`
- [ ] Submitting the form with a valid new name/email/password creates exactly one
      row in `users`, with a `password_hash` starting `pbkdf2:` or `scrypt:` (never
      the plaintext), and redirects to `/login`
- [ ] The `/login` page shows "Account created successfully. Please sign in."
      after that redirect (flash rendered from `base.html`)
- [ ] `sqlite3 spendly.db "SELECT name, email FROM users WHERE email='you@example.com'"`
      shows the new account
- [ ] Submitting with a password shorter than 8 characters re-renders the form with
      "Password must be at least 8 characters." and status 400
- [ ] Submitting with a malformed email re-renders the form with
      "Please enter a valid email address." and status 400
- [ ] Registering `demo@spendly.com` again shows
      "An account with this email already exists." and does not create a duplicate row
- [ ] Registering `DEMO@Spendly.com` (mixed case) is also rejected as a duplicate
- [ ] After a validation error, the name and email fields still show what was typed
      but the password field is empty
- [ ] The app starts with `uv run python app.py` on port 5001 with no traceback
- [ ] `git diff` shows no changes to `/logout`, `/profile`, or any `/expenses/...` stub,
      no changes to `database/db.py`, and the only other touched files are
      `templates/base.html` and `static/css/style.css` (flash support)
