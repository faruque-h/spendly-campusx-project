# Spec: Login and Logout

## Overview

This step turns `GET /login` into a working sign-in flow and replaces the
`GET /logout` placeholder with a real sign-out. A registered user submits their
email and password; the server looks the user up case-insensitively, verifies the
password against the stored werkzeug hash, and stores the user's id in Flask's
signed session cookie. The navbar then reflects the authenticated state (user
name plus a sign-out link), and `/logout` clears the session and returns the
visitor to the public landing page. This is the first step that introduces
authentication state, and it is the prerequisite for every owner-scoped feature
that follows (profile in Step 4, adding/editing/deleting expenses in Steps 7–9).
Route protection (`login_required` guards) is deliberately out of scope here.

## Depends on

- Step 1 — Database setup: `users` table with `password_hash`, `get_db()`.
- Step 2 — Registration: `POST /register` creates users with
  `generate_password_hash`, and the existing `SECRET_KEY` config plus the
  `get_flashed_messages` block in `base.html` are already in place.
- Existing `templates/login.html` and `GET /login` route, which only need
  behaviour wired up.

## Routes

- `GET /login` — render the sign-in form; if a user is already in the session,
  redirect to the landing page — public *(exists, gets a guard)*
- `POST /login` — validate credentials, set the session, redirect on success —
  public *(new behaviour on the existing route)*
- `GET /logout` — clear the session and redirect to the landing page — public
  (safe when already signed out) *(replaces the Step 3 placeholder)*

No other routes are added. `/profile` and all `/expenses/...` stubs stay exactly
as they are.

## Database changes

No database changes.

Verified against `database/db.py`: `users` already stores `id`, `name`, `email`
(`NOT NULL UNIQUE`), `password_hash` (`NOT NULL`), and `created_at`. Login only
reads from it; logout touches no tables. Session data lives in the signed cookie,
not in the database.

## Templates

- **Create:** none
- **Modify:** `templates/login.html`
  - Repopulate the email field after a failed attempt:
    `value="{{ email or '' }}"`, and add `autocomplete="email"`.
  - Add `autocomplete="current-password"` to the password input.
  - Add `role="alert"` to the existing `.auth-error` block so the error is
    announced by screen readers.
  - Point the form at `action="{{ url_for('login') }}"` (no hardcoded path).
  - Change nothing else: layout, classes, and copy stay as they are; the
    password field must remain empty on re-render.
- **Modify:** `templates/base.html`
  - Split `.nav-links` on `current_user`:
    - signed out → existing "Sign in" link and "Get started" CTA;
    - signed in → `<span class="nav-user">Hi, {{ current_user.name }}</span>` and
      `<a href="{{ url_for('logout') }}">Sign out</a>`.
  - Do not link the user name to `/profile`; that route is still a stub until
    Step 4.
- **Modify:** `static/css/style.css`
  - Add `.nav-user` (muted, non-interactive label matching `.nav-links` type
    scale) and a `.nav-links a.nav-signout` hover rule if needed.
  - Reuse existing `:root` variables only (`--ink-muted`, `--ink`,
    `--font-body`); no new hex values, no new tokens.

## Files to change

- `app.py`
  - Import `session` and `check_password_hash` (alongside the existing
    `generate_password_hash`).
  - `login` view: add `POST` to `methods`, keep the `GET` render, and implement
    the validation contract below; on success
    `session["user_id"] = user["id"]`, optionally `session["user_name"]`, then
    `flash(...)` and `redirect(url_for("landing"))`.
  - `logout` view: replace the placeholder with
    `session.clear()`, then `flash("You have been signed out.", "success")`, then
    `redirect(url_for("landing"))` (clear before flashing or the flash is lost).
  - Add a `@app.context_processor` that exposes `current_user` to every
    template: return `None` when there is no `user_id`; otherwise query
    `SELECT id, name, email FROM users WHERE id = ?` with `get_db()` (connection
    closed in `finally`) and return a dict. If the row is gone, `session.clear()`
    and return `None`.
  - Leave `register`, `landing`, `terms`, `privacy`, and all placeholder routes
    untouched.
- `templates/login.html` — sticky email, autocomplete hints, `role="alert"`,
  `url_for` action.
- `templates/base.html` — authenticated vs. anonymous navbar.
- `static/css/style.css` — `.nav-user` (and sign-out hover) styles.

## Files to create

- None

## New dependencies

No new dependencies. `flask` (session, flash) and `werkzeug`
(`check_password_hash`) are already declared in `pyproject.toml`. Do not run
`uv add` for this step.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders, never f-strings or `%` in SQL)
- Passwords hashed with werkzeug — verify with `check_password_hash`; never
  store, compare, or log plaintext passwords
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Stub routes outside this step's scope must stay untouched (`/profile`,
  `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`)
- Use `get_db()` and always close the connection in a `finally` block
- Normalise the submitted email with `.strip().lower()` and look up with
  `WHERE lower(email) = ?`, matching the registration step
- Do not strip the password; validate the raw value
- Redirect after login to `url_for("landing")`. `/profile` is a plain-text stub
  until Step 4, so it must not be the target yet
- Do not add CSRF protection, "remember me", password reset, rate limiting, or
  `next=` redirect handling in this step; consistent with Step 2, these are
  accepted risks for a later hardening step
- No new config keys are required; reuse the existing `SECRET_KEY`. Do not
  disable the cookie defaults in Flask 3 (`HTTPOnly`, `SameSite=Lax`)
- Logout must be idempotent: visiting it while signed out still redirects
  cleanly with no traceback

### Login contract for `POST /login`

| Field | Rule | Result |
|---|---|---|
| `email` | required, non-empty after strip | missing → re-render with "Please enter your email and password." and status `400` |
| `password` | required, non-empty (never stripped) | missing → same message and status `400` |
| both | email must match an existing user (case-insensitive) **and** `check_password_hash(password_hash, password)` must pass | any mismatch → single generic "Invalid email or password." and status `401` |

- Always show the same generic message for unknown email and wrong password to
  avoid revealing which accounts exist.
- On any failure, re-render `login.html` with `error` and the cleaned `email`;
  never echo the password back.
- On success: set the session, flash
  "Welcome back, {{ user name }}." with category `success`, and redirect.
- `GET /login` while already signed in redirects to `url_for("landing")`
  instead of rendering the form.

## Definition of done

- [ ] `uv run python app.py` starts on port 5001 with no traceback
- [ ] `GET /login` renders the sign-in form at `http://localhost:5001/login`
- [ ] Signing in with `demo@spendly.com` / `demo123` redirects to `/` and the
      navbar shows "Hi, Demo User" and a "Sign out" link instead of
      "Sign in"/"Get started"
- [ ] The landing page shows the flash "Welcome back, Demo User." after login
- [ ] Signing in with `DEMO@Spendly.com` / `demo123` also succeeds (case-insensitive
      email lookup)
- [ ] Signing in with the correct email and a wrong password re-renders the form
      with "Invalid email or password." and status `401`, and the email field
      keeps the submitted value while the password field is empty
- [ ] Signing in with an unknown email shows the same generic error and status
      `401`
- [ ] Submitting an empty email or password shows
      "Please enter your email and password." and status `400`
- [ ] Refreshing the page after login stays signed in (session cookie persists)
- [ ] Visiting `GET /login` while signed in redirects to `/` instead of showing
      the form
- [ ] `GET /logout` clears the session, redirects to `/`, shows
      "You have been signed out.", and reverts the navbar to
      "Sign in"/"Get started"
- [ ] Visiting `GET /logout` while already signed out redirects to `/` without
      an error
- [ ] After logout, a browser refresh / new request stays signed out (no stale
      session)
- [ ] `sqlite3 spendly.db "SELECT COUNT(*) FROM users"` is unchanged by a
      login/logout cycle (no writes)
- [ ] `git diff` shows no changes to `database/db.py`, `register.html`,
      `/profile`, or any `/expenses/...` stub; only `app.py`,
      `templates/login.html`, `templates/base.html`, and `static/css/style.css`
      are touched
