# Implementation Plan — Step 3: Login and Logout

**Spec:** `.pi/specs/03-login-and-logout.md`
**Branch:** `feature/login-logout-01` (create from current `main`)
**Files to change:** `app.py`, `templates/login.html`, `templates/base.html`,
`static/css/style.css`
**Files to create:** none
**Status:** plan only — no application code changed (planning mode)
**Locked decisions:** session holds `user_id` only; `current_user` via
`context_processor`; no `@login_required`; no CSRF/rate limiting/`next=`.

---

## 1. Objective

Give `GET /login` a working `POST` counterpart and replace the `GET /logout`
placeholder with a real sign-out:

1. `POST /login` validates email/password, verifies with `check_password_hash`,
   writes `session["user_id"]`, flashes a welcome, redirects to `/`.
2. `GET /logout` clears the session (before flashing), flashes, redirects to `/`.
3. A `context_processor` exposes `current_user` to every template so the navbar
   switches between anonymous and signed-in states.
4. `login.html` gets sticky email, autocomplete hints, `role="alert"`.

No schema change. `/profile` and all `/expenses/...` stubs stay untouched.

---

## 2. Current state (verified on this branch)

| Item | Verified state |
|---|---|
| `app.py` | Imports `Flask, flash, redirect, render_template, request, url_for` from flask and `generate_password_hash` from werkzeug. `SECRET_KEY` already set from `SPENDLY_SECRET_KEY` with a dev fallback. **`session` and `check_password_hash` are NOT imported.** |
| `GET /login` | `@app.route("/login")` — GET only, `return render_template("login.html")`. No session guard, no `POST` method. |
| `GET /logout` | Still the placeholder `return "Logout — coming in Step 3"` at the bottom of the file, in the "Placeholder routes" section (lines ~86–90), *after* `terms`/`privacy`. |
| `register` view | Fully implemented (Step 2): normalises `email.strip().lower()`, `WHERE lower(email) = ?`, never strips password, flashes `success`, redirects to `/login`. **Do not touch.** |
| `database/db.py` | `users(id, name, email NOT NULL UNIQUE, password_hash NOT NULL, created_at)`; `get_db()` returns a `sqlite3.Row` connection, caller closes. **No change needed.** |
| Live DB | 2 users: `demo@spendly.com` (name `Demo User`, hash prefix `scrypt:32768:8:1$`), `nitish@gmail.com`. The DoD's `demo123` login is valid — `check_password_hash` will accept `scrypt`. |
| Flash CSS | **Already exists from Step 2**: `.flash-stack`, `.flash`, `.flash--success` (style.css ~473–491), all using `:root` vars. No new flash rules required. |
| `base.html` | Flash block already renders inside `<main>` using `get_flashed_messages(with_categories=true)`. Navbar `.nav-links` is hardcoded to "Sign in" + "Get started" CTA. **No `current_user` anywhere in the project yet** (`grep` returns nothing). |
| `login.html` | `action="/login"` hardcoded, no `value=` repopulation, no `autocomplete`, `.auth-error` has no `role="alert"`. |
| `.auth-error` CSS | Exists; hardcodes border `#f5c6c2` (pre-existing, out of scope). |
| Navbar CSS | `.nav-links` = flex, `gap: 1.5rem`, `font-size: 0.9rem`, `font-weight: 500`; `.nav-links a` = `var(--ink-muted)` → `var(--ink)` on hover. **No `.nav-user` rule exists.** |
| Tests | None. `uv run pytest` exits 5. Verification is manual/curl only. |
| Port 5001 | Free — no dev server running. |
| Working tree | Clean except untracked `.pi/specs/03-login-and-logout.md`. |

---

## 3. Findings and resolutions

### F1 — Session payload → **`user_id` only**

The spec says `session["user_id"] = user["id"]`, "optionally
`session["user_name"]`". Decision: store **`user_id` only**. The name comes from
the `context_processor` DB lookup, so a renamed user sees the new name without a
re-login, and there is exactly one source of truth. `session["user_name"]` is
not added.

### F2 — `current_user` shape → **dict, not a row**

The spec says "return a dict". Implement literally: return
`dict(row)` (or an explicit `{"id": ..., "name": ..., "email": ...}`) so
templates use attribute-style access (`current_user.name`) that Jinja supports
for dicts. Returning the raw `sqlite3.Row` would work in Jinja but is not a dict
and would break `current_user is none` clarity. Use an explicit dict built from
the fetched columns — cheapest and most predictable, and it cannot leak
`password_hash`.

### F3 — Where the "already signed in" guard lives → **inside `login`, GET only**

`GET /login` while `session.get("user_id")` is set → `redirect(url_for("landing"))`.
The check runs only on `GET` (i.e. before/instead of rendering), never on `POST`,
so a stale-but-invalid session cannot block a real sign-in attempt; the POST path
re-validates credentials and overwrites the session anyway.

### F4 — Deleted user with a live cookie → **clear and continue**

`context_processor` fetches the row; if it is `None` (user deleted from the DB),
`session.clear()` and return `None`. Note the ordering constraint: the
context processor also runs while rendering the *flash* page after logout — the
session is already cleared there, so it returns `None` and the navbar correctly
reverts to anonymous.

### F5 — Logout order → **`session.clear()` → `flash()` → `redirect()`**

`flash()` writes into `session["_flashes"]`. Clearing after flashing would
destroy the message (and the logout flash would never appear). The spec states
this; it is the single easiest bug to introduce here.

### F6 — Status codes 400 vs 401 → **return tuples from the view**

Missing field → `(render_template(...), 400)`; bad credentials → same render
with `, 401`. Same shape as the `register` view, so error HTML and status stay in
one `return`.

### F7 — `check_password_hash` timing / malformed hash

A row with a `password_hash` that `check_password_hash` cannot parse raises
`ValueError` in Werkzeug 3.x. Wrap the verification in `try/except ValueError`
and treat it as a credential mismatch (401), never a 500. No user enumeration is
introduced: same generic message.

### F8 — No user enumeration → **single generic message**

Unknown email and wrong password both return exactly `Invalid email or password.`
with `401`. No timing equalisation is attempted (accepted risk; matches spec's
"no rate limiting in this step").

### F9 — Navbar markup for the signed-in state

```html
{% if current_user %}
    <span class="nav-user">Hi, {{ current_user.name }}</span>
    <a href="{{ url_for('logout') }}" class="nav-signout">Sign out</a>
{% else %}
    <a href="{{ url_for('login') }}">Sign in</a>
    <a href="{{ url_for('register') }}" class="nav-cta">Get started</a>
{% endif %}
```

The name is **not** linked to `/profile` (plain-text stub until Step 4), per
spec. `.nav-signout` is added only so the sign-out link can be styled without
hitting the `.nav-cta` rule; it inherits the existing `.nav-links a` colours.

### F10 — CSS additions are tiny and variable-only

`.nav-user` (non-interactive label, `var(--ink-muted)`, same `0.9rem` /
`500` scale as `.nav-links`) and `.nav-links a.nav-signout:hover` (only needed if
the generic `.nav-links a:hover` is insufficient — **check first**; it likely is
sufficient, in which case add no hover rule at all). **No new hex values.**

### F11 — `url_for('login')` keeps working

The view function name stays `login`; only `methods` and the body change. Same
for `logout`. `base.html`, `login.html`, and `register`'s redirect stay valid.

### D12 — No CSRF, no "remember me", no `next=` — **accepted, deferred**

Consistent with Step 2. `POST /login` is a state-*creating* endpoint (sets a
cookie), so CSRF is a real gap, but it is explicitly out of scope. Record it in
the commit message for the later hardening step.

### D13 — No `login_required` decorator

Explicitly out of scope. `/profile` and the expense stubs keep returning plain
text, signed in or not.

---

## 4. Proposed implementation

### 4.1 `app.py` — imports

```python
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,          # NEW
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
```

### 4.2 `app.py` — `current_user` context processor

Place it after the module-level `init_db()/seed_db()` block (or immediately
before the routes section) so it is registered before the first request:

```python
@app.context_processor
def inject_current_user():
    """Expose the signed-in user to every template as `current_user`."""
    user_id = session.get("user_id")
    if user_id is None:
        return {"current_user": None}

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        # Stale cookie for a deleted user: drop it and treat as anonymous.
        session.clear()
        return {"current_user": None}

    return {"current_user": {"id": row["id"], "name": row["name"],
                             "email": row["email"]}}
```

Notes: `finally: conn.close()` per the spec; explicit column list (never
`SELECT *`, so `password_hash` never reaches a template); parameterised query.

### 4.3 `app.py` — the `login` view

```python
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET" and session.get("user_id") is not None:
        return redirect(url_for("landing"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""   # never strip passwords

        if not email or not password:
            return render_template("login.html", email=email,
                                   error="Please enter your email and password."), 400

        conn = get_db()
        try:
            user = conn.execute(
                "SELECT id, name, password_hash FROM users WHERE lower(email) = ?",
                (email,),
            ).fetchone()
        finally:
            conn.close()

        verified = False
        if user is not None:
            try:
                verified = check_password_hash(user["password_hash"], password)
            except ValueError:       # malformed/unsupported stored hash
                verified = False

        if not verified:
            return render_template("login.html", email=email,
                                   error="Invalid email or password."), 401

        session.clear()              # start a clean session (no fixation leftovers)
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user['name']}.", "success")
        return redirect(url_for("landing"))

    return render_template("login.html", email="")
```

Review notes:

- `email` is normalised identically to `register` (`.strip().lower()` +
  `WHERE lower(email) = ?`); password is passed through untouched.
- `session.clear()` before setting `user_id` avoids carrying any pre-login
  session state into the authenticated session.
- The `finally: conn.close()` covers the early 400 return path? **No** — the
  connection is opened *after* the 400 check, so nothing leaks. On the 401 path
  the connection is already closed by `finally` before rendering.
- Generic message only. The password is never echoed back to the template.

### 4.4 `app.py` — the `logout` view (replaces the placeholder)

Move/replace the placeholder — keep it in the placeholder section or promote it
above; either is fine, but the endpoint name must stay `logout`:

```python
@app.route("/logout")
def logout():
    session.clear()                              # clear FIRST
    flash("You have been signed out.", "success")
    return redirect(url_for("landing"))
```

Idempotent: with no session, `session.clear()` is a no-op, the flash still
renders, and the redirect succeeds — no traceback. No `methods` needed (GET only,
matching the existing link in the navbar and the spec).

### 4.5 `templates/login.html`

```html
{% if error %}
<div class="auth-error" role="alert">{{ error }}</div>
{% endif %}

<form method="POST" action="{{ url_for('login') }}">
    <div class="form-group">
        <label for="email">Email address</label>
        <input type="email" id="email" name="email"
               class="form-input" placeholder="nitish@example.com"
               value="{{ email or '' }}" autocomplete="email"
               required autofocus>
    </div>
    <div class="form-group">
        <label for="password">Password</label>
        <input type="password" id="password" name="password"
               class="form-input" placeholder="Your password"
               autocomplete="current-password" required>
    </div>
    <button type="submit" class="btn-submit">Sign in</button>
</form>
```

Exactly four deltas: `value="{{ email or '' }}"`, `autocomplete="email"`,
`autocomplete="current-password"`, `role="alert"` — plus `url_for` on `action`.
Password input stays empty (no `value`), layout/classes/copy unchanged.
`{{ email or '' }}` is safe on the GET path when `email` is undefined and is
auto-escaped by Jinja.

### 4.6 `templates/base.html` — split `.nav-links`

```html
<div class="nav-links">
    {% if current_user %}
    <span class="nav-user">Hi, {{ current_user.name }}</span>
    <a href="{{ url_for('logout') }}" class="nav-signout">Sign out</a>
    {% else %}
    <a href="{{ url_for('login') }}">Sign in</a>
    <a href="{{ url_for('register') }}" class="nav-cta">Get started</a>
    {% endif %}
</div>
```

The `.flash-stack` block already in `base.html` is not touched — it renders both
the login welcome and the logout message with no change.

### 4.7 `static/css/style.css` — after `.nav-cta:hover`

```css
.nav-user {
    color: var(--ink-muted);
    font-size: 0.9rem;
    font-weight: 500;
}
```

Add `.nav-links a.nav-signout:hover { color: var(--ink); }` **only if** the
existing `.nav-links a:hover` rule turns out not to apply (it should, and
duplicating it would be noise). Variables only; no new tokens.

---

## 5. Verification plan

No test suite exists, so all verification is curl + a browser pass.
Start the server once: `uv run python app.py` (port 5001 — confirmed free).

### 5.1 Startup, GET, and anonymous navbar

```bash
uv run python app.py &
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5001/login          # 200
curl -s http://localhost:5001/login | grep -c 'action="/login"\|url_for\|name="password"' 
curl -s http://localhost:5001/ | grep -o 'Sign in\|Get started\|Hi, ' | sort -u
# → "Sign in", "Get started"; no "Hi, "
```

### 5.2 Happy path (session set, welcome flash, navbar flips)

```bash
rm -f /tmp/spendly.jar
curl -s -i -c /tmp/spendly.jar -X POST http://localhost:5001/login \
  -d 'email=demo@spendly.com&password=demo123' | head -10
# → HTTP/1.1 302, Location: /
curl -s -b /tmp/spendly.jar http://localhost:5001/ | grep -o 'Welcome back, Demo User\.'
curl -s -b /tmp/spendly.jar http://localhost:5001/ | grep -o 'Hi, Demo User\|Sign out\|nav-user'
```

### 5.3 Session persists; GET /login while signed in redirects

```bash
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  -b /tmp/spendly.jar http://localhost:5001/login      # → 302 http://localhost:5001/
curl -s -b /tmp/spendly.jar http://localhost:5001/ | grep -c 'Welcome back'   # 0 (flash consumed once)
```

### 5.4 Case-insensitive email

```bash
rm -f /tmp/spendly2.jar
curl -s -o /dev/null -w '%{http_code}\n' -c /tmp/spendly2.jar \
  -X POST http://localhost:5001/login -d 'email=DEMO@Spendly.com&password=demo123'   # 302
curl -s -b /tmp/spendly2.jar http://localhost:5001/ | grep -o 'Hi, Demo User'
```

### 5.5 Failure cases — exact messages and status

```bash
# wrong password → 401, generic message, sticky email, empty password field
curl -s -i -X POST http://localhost:5001/login \
  -d 'email=demo@spendly.com&password=wrong' | grep -E 'HTTP/|Invalid email or password'
curl -s -X POST http://localhost:5001/login \
  -d 'email=demo@spendly.com&password=wrong' \
  | grep -E 'value="demo@spendly.com"|name="password"|role="alert"' -A1
# → value kept on email, NO value on password, role="alert" present

# unknown email → identical 401 + same message (no enumeration)
curl -s -i -X POST http://localhost:5001/login \
  -d 'email=nobody@example.com&password=demo123' | grep -E 'HTTP/|Invalid email or password'

# empty email / empty password / both → 400
curl -s -i -X POST http://localhost:5001/login -d 'email=&password=demo123' \
  | grep -E 'HTTP/|Please enter your email and password'
curl -s -i -X POST http://localhost:5001/login -d 'email=demo@spendly.com&password=' \
  | grep -E 'HTTP/|Please enter your email and password'
curl -s -i -X POST http://localhost:5001/login -d '' \
  | grep -E 'HTTP/|Please enter your email and password'
# whitespace-only email counts as empty (strip) → 400
curl -s -i -X POST http://localhost:5001/login -d 'email=%20%20&password=x' \
  | grep -E 'HTTP/|Please enter your email and password'

# password is not stripped: " demo123" must FAIL (401), not succeed
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:5001/login \
  -d 'email=demo@spendly.com&password=%20demo123'      # → 401
```

### 5.6 Logout

```bash
curl -s -i -b /tmp/spendly.jar http://localhost:5001/logout | grep -E 'HTTP/|Location'
# → 302, Location: /
curl -s -b /tmp/spendly.jar http://localhost:5001/ \
  | grep -o 'You have been signed out\.\|Sign in\|Get started\|Hi, '
# → signed-out message + "Sign in"/"Get started", NO "Hi, "
# second visit stays signed out on the next request
curl -s -b /tmp/spendly.jar http://localhost:5001/ | grep -c 'Sign out'      # 0
# idempotent: logout with no session
curl -s -i http://localhost:5001/logout | grep -E 'HTTP/|Location'           # 302, no traceback
```

### 5.7 No database writes

```bash
uv run python -c "import sqlite3;print(sqlite3.connect('spendly.db').execute('SELECT COUNT(*),MAX(id) FROM users').fetchone())"
# run before and after a full login+logout cycle → identical values
```

### 5.8 Stale cookie for a deleted user (F4)

```bash
# with /tmp/spendly2.jar holding a live session, delete that user in a scratch
# copy of spendly.db, restart, then GET / → anonymous navbar, no 500
```

### 5.9 Scope guard

```bash
git diff --stat
# → app.py, templates/login.html, templates/base.html, static/css/style.css only
git diff -- database/db.py                                      # empty
curl -s http://localhost:5001/profile                           # "Profile page — coming in Step 4"
curl -s http://localhost:5001/expenses/add                      # "Add expense — coming in Step 7"
git diff -- templates/register.html templates/landing.html \
            templates/terms.html templates/privacy.html         # empty
```

### 5.10 Browser pass (the parts curl cannot see)

At `http://localhost:5001/login`: sign in as `demo@spendly.com` / `demo123` →
lands on `/` with "Welcome back, Demo User." and navbar "Hi, Demo User / Sign
out"; hard refresh stays signed in; "Sign out" returns to `/` with the
signed-out flash and the anonymous CTA back. Confirm the `.nav-user` label does
not look clickable (no pointer cursor, muted colour).

### 5.11 Cleanup

```bash
kill %1; rm -f /tmp/spendly.jar /tmp/spendly2.jar
```

---

## 6. DoD mapping

| DoD item | How it is proven |
|---|---|
| App starts on 5001, no traceback | §5.1 |
| `GET /login` renders the form | §5.1 |
| `demo@spendly.com`/`demo123` → `/`, navbar shows "Hi, Demo User" + "Sign out" | §5.2, §5.10 |
| Landing shows "Welcome back, Demo User." | §5.2 |
| `DEMO@Spendly.com` also works | §5.4 |
| Wrong password → 401 "Invalid email or password.", email sticky, password empty | §5.5 |
| Unknown email → same 401 message | §5.5 |
| Empty email/password → 400 "Please enter your email and password." | §5.5 |
| Refresh after login stays signed in | §5.3, §5.10 |
| `GET /login` while signed in redirects to `/` | §5.3 |
| `/logout` clears session, redirects, shows message, reverts navbar | §5.6 |
| `/logout` while signed out redirects without error | §5.6 |
| Stays signed out after logout | §5.6 |
| `users` row count unchanged by login/logout | §5.7 |
| `git diff` limited to the four files; `db.py`/stubs untouched | §5.9 |

---

## 7. Execution order

1. `app.py` — add `session` + `check_password_hash` imports.
2. `app.py` — add `inject_current_user` context processor.
3. `app.py` — rewrite `login` (GET guard + POST contract).
4. `app.py` — replace the `logout` placeholder.
5. `templates/login.html` — sticky email, autocomplete, `role="alert"`,
   `url_for` action.
6. `templates/base.html` — conditional `.nav-links`.
7. `static/css/style.css` — `.nav-user` (+ hover rule only if needed).
8. Run §5.1–§5.9; fix failures.
9. Browser pass §5.10, then clean up §5.11.
10. Commit on `feature/login-logout-01`, including this plan and the spec;
    note the deferred CSRF/rate-limiting risk in the message.

---

## 8. Out of scope

- `@login_required` / route protection, `/profile` content — Step 4.
- Add/edit/delete expenses and owner scoping — Steps 7–9.
- CSRF, "remember me", password reset, rate limiting, `next=` redirects.
- Session expiry tuning and disabling Flask 3 cookie defaults (keep `HTTPOnly`,
  `SameSite=Lax`).
- Any `database/db.py` change — none is needed.

---

## 9. Risks / watch-outs

| Risk | Mitigation |
|---|---|
| Flash lost on logout | `session.clear()` strictly before `flash()` (§4.4). |
| `current_user` leaking `password_hash` | Explicit column list + explicit dict (§4.2). |
| Malformed stored hash → 500 | `try/except ValueError` around `check_password_hash` (F7). |
| Cookie set without `SECRET_KEY` | Already configured in `app.py` since Step 2. |
| Email enumeration | One generic 401 message for both failure modes (§5.5). |
| Touching stub routes out of habit | §5.9 scope guard asserts their plain-text bodies. |
