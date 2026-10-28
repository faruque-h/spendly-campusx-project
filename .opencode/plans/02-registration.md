# Implementation Plan — Step 2: Registration

**Spec:** `.opencode/specs/02-registration.md`
**Branch:** `feature/registration-01`
**Files to change:** `app.py`, `templates/register.html`, `templates/base.html`,
`static/css/style.css`
**Files to create:** none
**Status:** plan only — no application code changed
**Locked decisions:** F1 = Option A (flash rendered from `base.html`); CSRF
deferred; no length caps or busy-timeout tuning added.

---

## 1. Objective

Turn the existing `GET /register` page into a working sign-up flow: validate
`name` / `email` / `password`, reject duplicates (case-insensitively), hash the
password with werkzeug, insert one row into the existing `users` table, flash a
success message, and redirect to `/login`. No session/login behaviour (that is
Step 3). No schema change. No changes to other routes.

---

## 2. Current state (verified on this branch)

| Item | Verified state |
|---|---|
| `app.py` | 56 lines. `@app.route("/register")` is GET-only and just renders the template. Imports are `Flask, render_template` + `get_db, init_db, seed_db`. No `request`, `redirect`, `url_for`, `flash`, no `SECRET_KEY`. |
| `database/db.py` | Fully implemented (Step 1). `users(id, name, email NOT NULL UNIQUE, password_hash NOT NULL, created_at)`. `get_db()` returns a new `sqlite3.Row` connection with `PRAGMA foreign_keys = ON`; callers must close. |
| `templates/register.html` | 45 lines: `auth-section` → `auth-container` → `auth-header` → `auth-card` with `{% if error %}` block → form `POST /register` with `name`, `email`, `password`. **No** `value=` repopulation, **no** `minlength`. |
| Flask / Werkzeug | Flask 3.1.3, Werkzeug 3.1.9. Default hash from `generate_password_hash()` is **`scrypt:32768:...`** (matches the DoD's `scrypt:` expectation; `pbkdf2:` only if a method is passed explicitly). |
| Flash / session infra | **None anywhere.** `grep` for `flash\|session\|SECRET_KEY` across `.py`/`.html` returns nothing. `base.html` has no message block; `login.html` only renders `{{ error }}`. |
| CSS | `.auth-error` exists (`--danger-light` / `--danger`, but hardcodes border `#f5c6c2`). **No `.flash`, `.alert`, or success class exists.** `:root` tokens: `--accent`, `--accent-light`, `--danger`, `--danger-light`, `--border`, `--radius-sm/md`, fonts. |
| DB file | `spendly.db` present, gitignored, seeded with `demo@spendly.com` (lowercase). `sqlite3` **CLI binary is not installed** — verification uses Python's `sqlite3` module. |
| Tests | No test suite; `uv run pytest` exits 5. Nothing here should claim tests pass. |
| Port 5001 | Free right now. No dev server running. |
| Working tree | Clean except untracked spec/plan files under `.opencode/`. |

---

## 3. Findings and resolutions (decided)

### F1 — Success message needs a renderer → **Option A (chosen)**

The spec Overview requires a success message after redirecting to `/login`, but
nothing renders flashed messages. Decision: flash the message in `app.py` and
render flashes once, in `templates/base.html`, styled with two CSS rules that use
`:root` variables only. Step 3 and later reuse the same markup for free.

Consequences: `templates/base.html` and `static/css/style.css` join the file
list, and `.opencode/specs/02-registration.md` is updated to say so.

Only `.flash` and `.flash--success` are added in this step. No `.flash--error`
rule — Step 3 adds error styling when it actually has an error flash to show.

### F2 — `SECRET_KEY` source → **env var with dev fallback**

Nothing loads `.env`; `python-dotenv` is not installed and no dependency is
added. Use:

```python
app.config["SECRET_KEY"] = os.environ.get("SPENDLY_SECRET_KEY", "dev-only-change-me")
```

Production sets `SPENDLY_SECRET_KEY`; the literal fallback is explicitly
commented as dev-only. Required regardless of flash, because Step 3 needs it.

### F3 — Duplicate detection must be case-insensitive → **`lower(email)` pre-check**

New submissions are normalised with `.strip().lower()`, and the lookup is:

```sql
SELECT 1 FROM users WHERE lower(email) = ?
```

SQLite's default `UNIQUE` collation is BINARY, so `UNIQUE` alone would accept
`Demo@Spendly.com` next to `demo@spendly.com`. The `sqlite3.IntegrityError`
handler remains as a guard for two concurrent identical submissions.

Accepted limitation: SQLite `lower()` folds ASCII only. Non-ASCII case variants
(Turkish `İ`, Greek sigma variants) are out of scope for this course app; no
`casefold()`/`unicodedata` normalisation is added.

### F4 — `minlength` is absent, not "kept" → **add it**

`register.html` gets `minlength="8"` on the password input, plus
`autocomplete="name"`, `autocomplete="email"`, `autocomplete="new-password"`.
Client-side checks are convenience only; the server rule (`len < 8`) is the real
gate.

### F5 — DoD assumes the `sqlite3` CLI → **verify via Python**

`sqlite3` is not installed here. Verification uses:

```bash
uv run python -c "import sqlite3;print(sqlite3.connect('spendly.db').execute('SELECT id,name,email,substr(password_hash,1,6) FROM users').fetchall())"
```

### F6 — No CSRF protection → **accepted risk, deferred**

The app has no Flask-WTF/token mechanism and this step adds no dependency. The
route ships without CSRF; note it in the commit message and revisit in a later
hardening step. No half-measures (no hand-rolled token) — that would be more
complex than the step warrants.

### F7 — Validation failures return 400 → **keep, and make the error noticeable**

Re-render with status 400 and sticky fields, per spec. Also add `role="alert"`
to the existing `.auth-error` div so screen readers announce the message. No
other accessibility rework.

### D8 — No length caps on `name` / `email` / `password`

Accepted: the spec's contract defines only required/non-empty, email shape, and
minimum password length. Adding max-length rules would ripple into the spec's
error-message table for no course value. No caps added.

### D9 — No SQLite busy-timeout tuning

Default 5 s timeout is adequate for a single-process dev app; `database is
locked` handling is out of scope.

### D10 — No test suite

No tests are added; verification is the manual matrix in §5, matching
`AGENTS.md` ("don't claim tests pass until tests actually exist").

---

## 4. Proposed implementation

### 4.1 `app.py` — imports and config

```python
import os
import re
import sqlite3

from flask import (Flask, flash, redirect, render_template, request, url_for)
from werkzeug.security import generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)

# Flash/session signing key. Set SPENDLY_SECRET_KEY in production; the
# fallback is for local development only.
app.config["SECRET_KEY"] = os.environ.get("SPENDLY_SECRET_KEY", "dev-only-change-me")

# Simple, deliberately permissive email shape: local@domain.tld
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
```

Keep the existing `with app.app_context(): init_db(); seed_db()` block and route
ordering unchanged.

### 4.2 `app.py` — the `register` view

```python
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""   # never strip passwords

        error = None
        if not name:
            error = "Please enter your name."
        elif not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."

        if error is None:
            conn = get_db()
            try:
                existing = conn.execute(
                    "SELECT 1 FROM users WHERE lower(email) = ?", (email,)
                ).fetchone()

                if existing is not None:
                    error = "An account with this email already exists."
                else:
                    try:
                        with conn:      # commits, rolls back on error
                            conn.execute(
                                "INSERT INTO users (name, email, password_hash) "
                                "VALUES (?, ?, ?)",
                                (name, email, generate_password_hash(password)),
                            )
                    except sqlite3.IntegrityError:
                        error = "An account with this email already exists."
                    else:
                        flash("Account created successfully. Please sign in.",
                              "success")
                        return redirect(url_for("login"))
            finally:
                conn.close()

        # Validation / duplicate failure: 400 + sticky fields.
        return render_template("register.html", error=error,
                               name=name, email=email), 400

    return render_template("register.html", name="", email="")
```

Review notes:

- Same function keeps the endpoint name `register`, so `url_for('register')` in
  `base.html` / `landing.html` / `login.html` keeps working.
- `finally: conn.close()` runs on the early `return redirect(...)` too.
- `with conn:` commits on success and rolls back on `IntegrityError`; the
  exception becomes a user-facing message, never a 500.
- First failing rule wins (name → email → password), matching the single
  `error` block.
- Password is never stripped, never logged, never echoed back.
- No `session[...]` writes — auto-login is Step 3.

### 4.3 `templates/register.html` — sticky values, `minlength`, `role="alert"`

```html
{% if error %}
<div class="auth-error" role="alert">{{ error }}</div>
{% endif %}
...
<input type="text" id="name" name="name"
       class="form-input" placeholder="Nitish Kumar"
       value="{{ name or '' }}" autocomplete="name"
       required autofocus>
...
<input type="email" id="email" name="email"
       class="form-input" placeholder="nitish@example.com"
       value="{{ email or '' }}" autocomplete="email"
       required>
...
<input type="password" id="password" name="password"
       class="form-input" placeholder="Min. 8 characters"
       minlength="8" autocomplete="new-password"
       required>
```

`{{ name or '' }}` is safe when the variable is undefined (the GET path passes
`""`) and Jinja auto-escapes it, so a crafted form value cannot inject markup.
The password field is never repopulated. Layout, classes, and copy are unchanged.

### 4.4 `templates/base.html` — one flash block (F1, decided)

Immediately inside `<main class="main-content">`:

```html
{% with messages = get_flashed_messages(with_categories=true) %}
{% if messages %}
<div class="flash-stack">
    {% for category, message in messages %}
    <div class="flash flash--{{ category }}">{{ message }}</div>
    {% endfor %}
</div>
{% endif %}
{% endwith %}
```

### 4.5 `static/css/style.css` — two rules, variables only

```css
.flash-stack { max-width: var(--max-width); margin: 1.5rem auto 0; padding: 0 2rem; }
.flash {
    border: 1px solid var(--accent-light);
    border-radius: var(--radius-sm);
    padding: 0.75rem 1rem;
    font-size: 0.875rem;
    margin-bottom: 0.75rem;
}
.flash--success { background: var(--accent-light); color: var(--accent); }
```

No new hex values. `.auth-error`'s pre-existing hardcoded `#f5c6c2` is left
alone (out of scope).

---

## 5. Verification plan

### 5.1 Startup and GET

```bash
uv run python app.py            # port 5001, no traceback
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5001/register   # 200
```

### 5.2 Happy path (302 → /login, success message visible)

```bash
rm -f /tmp/spendly.jar
curl -s -i -c /tmp/spendly.jar -X POST http://localhost:5001/register \
  -d 'name=Test User&email=Test@Example.com&password=secret123' | head -12
curl -s -b /tmp/spendly.jar http://localhost:5001/login \
  | grep -o 'Account created successfully[^<]*'
```

Expected: `HTTP/1.1 302 FOUND`, `Location: /login`, then the message text.

### 5.3 Database row + hash

```bash
uv run python -c "import sqlite3;print(sqlite3.connect('spendly.db').execute(\"SELECT id,name,email,substr(password_hash,1,7) FROM users WHERE email='test@example.com'\").fetchall())"
uv run python -c "import sqlite3;print(sqlite3.connect('spendly.db').execute(\"SELECT COUNT(*) FROM users WHERE password_hash LIKE '%secret123%'\").fetchone())"
```

Expected: one row, email stored lowercase, hash prefix `scrypt:`, and `(0,)`
plaintext matches.

### 5.4 Failure cases (400 + exact message)

```bash
# short password
curl -s -i -X POST http://localhost:5001/register \
  -d 'name=Short&email=short@example.com&password=short' | grep -E 'HTTP/|Password must'
# malformed email
curl -s -i -X POST http://localhost:5001/register \
  -d 'name=Bad&email=not-an-email&password=secret123' | grep -E 'HTTP/|valid email'
# whitespace-only name
curl -s -i -X POST http://localhost:5001/register \
  -d 'name=%20%20&email=blank@example.com&password=secret123' | grep -E 'HTTP/|enter your name'
# duplicate (seeded demo user)
curl -s -i -X POST http://localhost:5001/register \
  -d 'name=Demo&email=demo@spendly.com&password=secret123' | grep -E 'HTTP/|already exists'
# duplicate, different case
curl -s -i -X POST http://localhost:5001/register \
  -d 'name=Demo&email=DEMO@Spendly.com&password=secret123' | grep -E 'HTTP/|already exists'
# row count unchanged after the duplicate attempts
uv run python -c "import sqlite3;print(sqlite3.connect('spendly.db').execute('SELECT COUNT(*) FROM users').fetchone())"
```

### 5.5 Sticky fields + alert role

```bash
curl -s -X POST http://localhost:5001/register \
  -d 'name=Keep Me&email=keep@example.com&password=short' \
  | grep -E 'role="alert"|name="name"|name="email"' -A1
```

Expected: `role="alert"` on the error div, `value="Keep Me"`,
`value="keep@example.com"`, and no value on the password input.

### 5.6 Regression / scope guard

```bash
git diff --stat        # app.py, register.html, base.html, style.css only
curl -s http://localhost:5001/logout             # still "Logout — coming in Step 3"
curl -s http://localhost:5001/profile            # still "Profile page — coming in Step 4"
git diff -- database/db.py                       # empty
git diff -- templates/login.html templates/landing.html templates/terms.html templates/privacy.html   # empty
```

### 5.7 Cleanup

```bash
rm -f spendly.db    # reseeded on next startup (demo user + 8 expenses)
```

---

## 6. DoD mapping

| DoD item | How it is proven |
|---|---|
| GET /register renders | §5.1 |
| Valid submit → one row, scrypt hash, redirect /login | §5.2, §5.3 |
| Success message shown on the login page | §5.2 |
| Row visible via SQL | §5.3 |
| Short password → 400 + message | §5.4 |
| Malformed email → 400 + message | §5.4 |
| Duplicate `demo@spendly.com` rejected, no new row | §5.4 |
| Mixed-case duplicate rejected | §5.4 |
| Sticky name/email, empty password, `role="alert"` | §5.5 |
| App starts without traceback on 5001 | §5.1 |
| Stub routes + `db.py` untouched | §5.6 |

---

## 7. Execution order

1. `app.py` — imports, `SECRET_KEY`, `EMAIL_RE`, rewrite `register`.
2. `templates/register.html` — sticky values, `minlength`, autocomplete,
   `role="alert"`.
3. `templates/base.html` — flash block.
4. `static/css/style.css` — `.flash-stack`, `.flash`, `.flash--success`.
5. Run §5.1–§5.6; fix anything that fails.
6. Reset the DB (§5.7).
7. Commit on `feature/registration-01`; include the spec and plan docs in the
   same commit.

---

## 8. Out of scope

- Login, logout, sessions/`session[...]`, `@login_required`, redirect-back
  (`next`), remember-me — Step 3.
- Profile page — Step 4.
- Any `/expenses/...` route.
- CSRF tokens, rate limiting, email verification, password reset, password
  strength meters, uniqueness beyond email.
- Length caps, Unicode case folding, SQLite busy-timeout tuning (D8, F3, D9).
- Changes to `database/db.py`, `pyproject.toml`, `uv.lock`, `requirements.txt`.
- JS in `static/js/main.js`.
- A pytest suite (D10).

---

## 9. Risks and edge cases

| Risk | Mitigation |
|---|---|
| Flash rendered twice | `get_flashed_messages` clears after one render; single block in `base.html`. |
| `SECRET_KEY` fallback ships to prod | Read from `SPENDLY_SECRET_KEY`; comment marks the fallback dev-only. |
| Case-variant duplicate email | `WHERE lower(email) = ?` pre-check (F3); `UNIQUE` alone is BINARY. |
| Concurrent identical registration | `sqlite3.IntegrityError` → friendly message, no 500. |
| Non-ASCII case variants | Accepted limitation (F3); documented, not fixed. |
| Whitespace-only name/email | `.strip()` before validation; email also `.lower()`. |
| 8-char boundary off-by-one | `len(password) < 8` — exactly 8 passes; test 7 and 8. |
| Error page reloaded/resubmitted | 400 + same form; no writes happen before validation passes. |
| Multi-error submissions | Only first message shown by design. |
| Connection leak | `get_db()` wrapped in `try/finally: conn.close()` on every path. |
| DB left dirty after manual testing | `rm -f spendly.db` in §5.7. |
| `sqlite3` CLI absent | Verify via `uv run python -c` (F5). |
