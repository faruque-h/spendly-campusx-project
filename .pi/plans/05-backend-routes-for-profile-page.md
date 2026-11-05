# Implementation Plan — Step 5: Backend Connection (Profile Routes)

**Spec:** `.pi/specs/05-backend-routes-for-profile-page.md`
**Branch:** `feature/backend-connection` (create from current `main`)
**Files to change:** `app.py`, `templates/profile.html`, `AGENTS.md`
**Files to create:** `database/queries.py`, `tests/conftest.py`,
`tests/test_backend_connection.py`
**Status:** plan only — no application code changed (planning mode)
**Locked decisions:** four pure query helpers in `database/queries.py`; one
`/profile` view consuming them; transaction dates stay ISO in the helper and are
formatted by a Jinja filter; `categories` keys become `amount` / `pct` (template
edit, not a structural change); no zero-filling of categories for empty users; no
schema change, no new dependencies.

---

## 1. Objective

Replace the Step 4 placeholder data in `GET /profile` with live, per-user
`sqlite3` queries, and cover the new data layer with the project's first tests.

1. `database/queries.py` — four pure helpers (`get_user_by_id`,
   `get_summary_stats`, `get_recent_transactions`, `get_category_breakdown`),
   each opening and closing its own connection via `get_db()`.
2. `app.py` — `profile()` calls the helpers instead of reading module constants;
   the constants `PROFILE_TRANSACTIONS` / `PROFILE_CATEGORY_TOTALS` are deleted.
3. `templates/profile.html` — consumes the new keys (`c.amount`, `c.pct`,
   `user.*`), formats dates, renders `₹` everywhere (already true).
4. `tests/` — `conftest.py` plus `tests/test_backend_connection.py`, isolated
   from the repo's `spendly.db`.

No new routes, no schema change, no ORM, no new dependencies, no CSS changes.

---

## 2. Current state (verified)

| Item | Verified state |
|---|---|
| `app.py` / `profile()` | Login-guarded (`session.get("user_id") is None` → `redirect(url_for("login"))`). Renders `profile.html` with `summary`, `transactions`, `categories`, `member_since="March 2024"`. Data comes from module constants `PROFILE_TRANSACTIONS` (8 rows) and `PROFILE_CATEGORY_TOTALS` (7 tuples), defined above the routes under a "Step 4 placeholder" comment. No SQL in the view. |
| Imports in `app.py` | `get_db, init_db, seed_db` already imported from `database.db`. `sqlite3`, `session`, `redirect`, `url_for`, `render_template` all present. |
| Context processor | `inject_current_user()` runs a `SELECT id, name, email FROM users WHERE id = ?`, closes the connection in `finally`, and clears the session if the row is gone. Navbar and user card both read `current_user` today. |
| `database/db.py` | `get_db()` → `sqlite3.connect(DATABASE)`, `row_factory = Row`, `PRAGMA foreign_keys = ON`. `DATABASE` is a module-level `Path` (`BASE_DIR / "spendly.db"`). `init_db()` creates the schema; `seed_db()` inserts the demo user + 8 expenses only when `users` is empty. `CATEGORIES` has exactly 7 entries. |
| `database/__init__.py` | Exists (empty) — `database` is already an importable package. |
| `expenses` columns | `id, user_id, amount, category, date (TEXT 'YYYY-MM-DD'), description (nullable), created_at`. `users.created_at` is `'YYYY-MM-DD HH:MM:SS'`. |
| Seed totals (recomputed) | **₹180.19 across 8 transactions.** Bills 60.00, Shopping 45.30, Health 25.40, Food 21.75 (12.50 + 9.25), Entertainment 15.99, Other 8.00, Transport 3.75. Top category: **Bills**. |
| Live DB snapshot (read-only dry run) | `spendly.db` currently holds **2 users** (demo + one registered during Step 2/3 testing) and 8 expenses for the demo user. Seed dates are `2026-10-01 … 2026-10-28` from `_current_month_dates()`, and the demo `created_at` formats as `October 2026`. The SQL + rounding algorithm in §4.1 were executed against it: summary `180.19 / 8 / Bills`; breakdown pcts `34, 25, 14, 12, 9, 4, 2` = 100; display dates start `28 Oct 2026`. |
| `templates/profile.html` | Four sections already present. Consumes `current_user.name`/`.email`, `member_since`, `summary.total_spent`/`.transaction_count`/`.top_category`, `t.date`/`.description`/`.category`/`.amount`, `c.name`/`c.percent`/`c.total`. `₹` is already used for both money fields (lines 27, 58, 73) and there is no `$`/`£` anywhere in `templates/`. One inline `style="width: {{ c.percent }}%"` (line 72) is the sanctioned exception. |
| `static/css/style.css` | `.profile-*`, `.tx-*`, `.badge`, `.breakdown-*` rules exist; `.bar-fill--{food,transport,bills,health,entertainment,shopping,other}` mapped to `--cat-*` tokens (line 822-828). **No CSS work needed this step.** |
| `tests/` | **Does not exist.** No `conftest.py`, no `pytest.ini`/`setup.cfg`/`[tool.pytest.ini_options]` anywhere. `uv run pytest` currently exits 5. |
| Dependencies | `flask==3.1.3`, `pytest==8.3.5`, `pytest-flask==1.3.0`, `werkzeug>=3.1.3,<4.0`. Nothing to add. |
| Test-relevant side effect | Importing `app` executes `init_db()` + `seed_db()` against the real `spendly.db`. Tests must patch `database.db.DATABASE` **before** the first `import app`. |

---

## 3. Findings and resolutions

### F1 — The spec's `₹346.24` is wrong → **use ₹180.19, correct the spec**

The spec asserts `total_spent` is `346.24` in three places (unit test table, route
test list, DoD). The verified seed data sums to **₹180.19**. The Step 4 plan
(`.pi/plans/04-profile-page.md` §2) independently recorded "₹180.19 across 8
transactions", and the current hardcoded view derives 180.19 from the same
literals.

Changing `SEED_EXPENSES` to reach 346.24 would be a DB change, which this step
explicitly excludes. Resolution:

- Implement against the real data: **₹180.19**, 8 transactions, Bills.
- Update `.pi/specs/05-backend-routes-for-profile-page.md`: replace every
  `346.24` with `180.19`.
- Tests must not hardcode the number in more than one place — derive the
  expected total from `SEED_EXPENSES` (or assert `₹180.19` in exactly one
  route test) so a future seed edit fails loudly.

> **Needs sign-off:** confirm the spec number gets fixed rather than the seed
> data being changed to match it.

### F2 — Category keys change → **template edit is required**

Step 4 contract: `categories` = `{name, total, percent}` (`.pi/specs/04-profile-page.md`
line 24). Step 5 spec: `{name, amount, pct}`. This is a key rename, not a layout
change, so the spec's "no structural changes needed" still holds — but
`templates/profile.html` lines 72–73 **must** be updated or the page renders
empty bars and `₹0.00` for every row.

### F3 — Dates are ISO in the DB but "21 Oct 2026" on screen → **Jinja filter**

`expenses.date` is `YYYY-MM-DD`; the template prints `t.date` verbatim, so
without a change the table would show `2026-10-21`. Options considered:

| Option | Verdict |
|---|---|
| Format inside `get_recent_transactions` | Rejected — puts presentation in the "pure query helper", and makes newest-first assertions parse strings. |
| Slice the string in Jinja | Rejected — unreadable, breaks on any format change. |
| **`@app.template_filter("display_date")` in `app.py`** | **Chosen** — helper stays ISO/pure and sortable; template reads `{{ t.date\|display_date }}`; the filter is unit-testable and reusable by Steps 7–9. |

```python
@app.template_filter("display_date")
def display_date(value):
    """'2026-10-21' -> '21 Oct 2026'; pass anything unparseable through."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return value
```

(`from datetime import datetime` is the only new import in `app.py`.)

### F4 — `member_since` moves from a literal into a query → **user card reads `user.*`**

The spec gives `get_user_by_id` the job of returning `name`, `email`, and
`member_since`, so the view passes the dict and the card renders from it. The
navbar keeps using `current_user` (Step 3 contract, unchanged) — both read the
same row, so they cannot disagree.

- `users.created_at` is `'YYYY-MM-DD HH:MM:SS'` → parse with
  `datetime.fromisoformat`, format `"%B %Y"` → `"March 2026"`.
- Guard the parse: a malformed value falls back to the first 7 characters
  (`"2026-03"`) instead of raising.
- `strftime("%B")` is English under the default `C` locale — fine here, and the
  tests must assert the *shape* (`Member since <Month> <YYYY>`), never a specific
  month, because `seed_db()` stamps `created_at` with `datetime('now')`.
- If `get_user_by_id` returns `None` (stale session for a deleted user), the view
  clears the session and redirects to `/login` — same defensive behaviour as
  `inject_current_user()`.

### F5 — Empty users → **zeros and empty lists, no zero-filled categories**

`get_summary_stats` returns `{"total_spent": 0, "transaction_count": 0,
"top_category": "—"}` (em dash, U+2014, exactly as the spec spells it) and the
other two helpers return `[]`.

The breakdown query groups only categories that actually have rows. Do **not**
zero-fill all 7 `CATEGORIES` — the spec requires `[]` for a user with no
expenses, and 7 zero-height bars for a brand-new account would be worse UI. The
seed user happens to spend in all 7 categories, which is why the DoD's "7
categories" holds; that is data-driven, not an artifact of the query.

### F6 — `pct` must sum to 100 → **round, then give the remainder to the largest**

`round(amount / total * 100)` per row on the seed data yields
33 + 25 + 14 + 12 + 9 + 4 + 2 = **99**. after rounding, compute
`remainder = 100 - sum(pcts)` and add it to the first row (the list is already
sorted by `amount DESC`, so that is the largest category) → Bills becomes 34 and
the row sums to 100. Applies for any negative remainder too (a single dominant
category can overshoot).

Guard: if `total <= 0`, return `[]` before dividing.

### F7 — Test isolation → **patch `database.db.DATABASE`, import `app` lazily**

`get_db()` resolves the module-global `DATABASE` at call time, and `app.py` does
`from database.db import get_db` — the *function* is bound, so monkeypatching
`database.db.DATABASE` still redirects every connection. Importing `app` at module
scope in a test file would, however, seed the real `spendly.db` at import time.
Therefore: **import `app` inside the `app` fixture**, after the DB path is
patched. See §5.1.

### F8 — Ordering ties → **`ORDER BY date DESC, id DESC`**

Seed dates are distinct, but two expenses on one day are normal for a real user.
`id DESC` is the deterministic tie-break and keeps the test assertion stable.

### F9 — `LIMIT` must be parameterised too

`get_recent_transactions(user_id, limit=10)` → `LIMIT ?` with `(int(limit),)`.
Never f-string the value into the SQL, per the spec's parameterisation rule.

### F10 — Nullable `description` → **`{{ t.description or "—" }}`**

The column is nullable; rendering `None` literally would print "None" in the table.

### F11 — `AGENTS.md` will be stale the moment this lands

Update: the route table row for `GET /profile` ("Implemented — Step 5"), the
Database section (mention `database/queries.py` as the query layer), the
Commands section (`uv run pytest` now has tests), and the Gotchas bullet that
says "There is no test suite".

### F12 — Pre-existing quirks left alone

- `.bar-fill--bills` maps to `var(--cat-entertainment)` and `.bar-fill--shopping`
  to `var(--cat-food)` (`style.css` 824, 827). Existing colours, not part of
  this step's scope.
- `AGENTS.md` still lists the 04.1 design-token pass as pending; untouched here.
- No empty-state copy is added to the table/breakdown (see §9).

---

## 4. Proposed implementation

### 4.1 `database/queries.py` (new)

```python
"""Read-only query helpers for Spendly. No Flask imports.

Every function opens its own connection via get_db() and closes it before
returning, so callers never manage connections.
"""

from datetime import datetime

from database.db import get_db


def _format_month(value):
    """'2026-03-18 10:22:31' -> 'March 2026'; degrade to '2026-03'."""
    try:
        return datetime.fromisoformat(value).strftime("%B %Y")
    except (TypeError, ValueError):
        return (value or "")[:7]


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": _format_month(row["created_at"]),
    }


def get_summary_stats(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, "
            "       COUNT(*) AS count "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC, category ASC "
            "LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    return {
        "total_spent": round(row["total"], 2),
        "transaction_count": row["count"],
        "top_category": top["category"] if top else "—",
    }


def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount "
            "FROM expenses WHERE user_id = ? "
            "ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, int(limit)),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


def get_category_breakdown(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY total DESC, category ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    total = sum(row["total"] for row in rows)
    if total <= 0:
        return []

    breakdown = [
        {
            "name": row["category"],
            "amount": round(row["total"], 2),
            "pct": round(row["total"] / total * 100),
        }
        for row in rows
    ]
    breakdown[0]["pct"] += 100 - sum(item["pct"] for item in breakdown)
    return breakdown
```

Notes: `SUM(amount)` returns `NULL` only when there are no rows, which
`COALESCE` handles; `COUNT(*)` is always 0 or more, so no `None` check needed.
The `ORDER BY … , category ASC` tie-breaks make `top_category` and the
breakdown deterministic.

### 4.2 `app.py` — imports, filter, view

Delete the `PROFILE_TRANSACTIONS` / `PROFILE_CATEGORY_TOTALS` block and its
"Step 4 placeholder" comment. Add `from datetime import datetime` and
`from database.queries import (...)`. Add the `display_date` filter from F3 next
to `inject_current_user`.

```python
@app.route("/profile")
def profile():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    if user is None:                     # stale session: user row was deleted
        session.clear()
        flash("Please sign in again.", "error")
        return redirect(url_for("login"))

    return render_template(
        "profile.html",
        user=user,
        summary=get_summary_stats(user_id),
        transactions=get_recent_transactions(user_id),
        categories=get_category_breakdown(user_id),
    )
```

`limit` stays at the helper's default (10 ≥ 8 seed rows, so all 8 render). The
`member_since` template variable disappears — the template reads
`user.member_since`.

### 4.3 `templates/profile.html` — eight line edits, no markup changes

| Line | From | To |
|---|---|---|
| 15 | `{% set name_parts = current_user.name.split() %}` | `{% set name_parts = user.name.split() %}` |
| 18 | `{{ current_user.name }}` | `{{ user.name }}` |
| 19 | `{{ current_user.email }}` | `{{ user.email }}` |
| 20 | `Member since {{ member_since }}` | `Member since {{ user.member_since }}` |
| 55 | `{{ t.date }}` | `{{ t.date\|display_date }}` |
| 56 | `{{ t.description }}` | `{{ t.description or "—" }}` |
| 72 | `style="width: {{ c.percent }}%"` | `style="width: {{ c.pct }}%"` |
| 73 | `{{ c.total }}` | `{{ c.amount }}` |

`₹{{ "%.2f"|format(summary.total_spent) }}`, the badges, the `bar-fill--{{ c.name|lower }}`
hook, and every CSS class stay exactly as they are. No hex, no `<style>`, no new
inline style, no JS.

### 4.4 `AGENTS.md` (after the code lands)

- Route table: `GET /profile` → "Implemented — Step 5 (live per-user queries)".
- Database section: add "Query helpers live in `database/queries.py` (no Flask
  imports); views call them rather than writing SQL inline."
- Commands: note `uv run pytest` runs the suite in `tests/`.
- Gotchas: replace "There is no test suite" with the new state (no lint/formatter
  yet; pytest lives in `tests/`).

---

## 5. Test plan

`tests/test_backend_connection.py`, matching the spec's tables. Use plain
`app.test_client()` — `pytest-flask` is installed but unnecessary, and skipping
it avoids its `app` fixture-name expectations.

### 5.1 `tests/conftest.py` (new)

```python
import pytest

import database.db as db_module


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point every get_db() call at a throwaway database."""
    monkeypatch.setattr(db_module, "DATABASE", tmp_path / "test.db")
    db_module.init_db()
    db_module.seed_db()
    return db_module.DATABASE


@pytest.fixture
def app(temp_db):
    # Import lazily: app.py seeds at import time, and must seed the temp DB.
    from app import app as flask_app
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def demo_user_id(temp_db):
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()
    finally:
        conn.close()
    return row["id"]


@pytest.fixture
def blank_user_id(temp_db):
    """A real user row with no expenses."""
    conn = db_module.get_db()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Blank User", "blank@spendly.com", "x"),
            )
        return cur.lastrowid
    finally:
        conn.close()
```

`SECRET_KEY` is already set on the app (dev fallback), so `session` works under
`TESTING`.

### 5.2 Unit tests (`database/queries.py`)

| Test | Assertion |
|---|---|
| `test_get_user_by_id` | `demo_user_id` → `name == "Demo User"`, `email == "demo@spendly.com"`, `re.fullmatch(r"[A-Z][a-z]+ \d{4}", member_since)` (no fixed month — `created_at` is `now`). |
| `test_get_user_by_id_missing` | `get_user_by_id(999999) is None`. |
| `test_get_summary_stats` | `total_spent == pytest.approx(180.19)`, `transaction_count == 8`, `top_category == "Bills"`. |
| `test_get_summary_stats_blank` | Whole-dict equality with `{"total_spent": 0, "transaction_count": 0, "top_category": "—"}` (`COALESCE` + `round()` keep these ints, so `==` is exact). |
| `test_get_recent_transactions` | 8 items; every item has exactly the keys `date, description, category, amount`; `[t["date"] for t in ...]` equals `sorted(..., reverse=True)`; first row is the latest seed date; sum of `amount` == 180.19. |
| `test_get_recent_transactions_limit` | `limit=3` → 3 items (guards the parameterised `LIMIT`). |
| `test_get_recent_transactions_blank` | `[]`. |
| `test_get_category_breakdown` | 7 rows; `[c["amount"] for c in ...]` sorted desc; `[c["name"] ...]` covers all `CATEGORIES`; every `pct` is `int`; `sum(pct) == 100`; largest is Bills with `pct == 34`. |
| `test_get_category_breakdown_blank` | `[]`. |
| `test_queries_close_connections` | optional: patch `database.db.get_db` with a spy whose `close` records calls; assert one call/per helper. Skip if it adds more than ~10 lines — F7's `finally` blocks already make leaks obvious in code review. |

### 5.3 Route tests

| Test | Assertion |
|---|---|
| `test_profile_requires_login` | `client.get("/profile")` → `302`, `Location` ends with `/login`. |
| `test_profile_seed_user` (logged in) | `200`; body contains `Demo User`, `demo@spendly.com`, `Member since`, `180.19`, `Bills`, `₹`, `Recent transactions`, `Category breakdown`. |
| `test_profile_transaction_rows` | `body.count('<td class="tx-date">') == 8`; the 8 `dd Mon YYYY` strings appear in newest-first order (index of first < index of last). |
| `test_profile_category_rows` | `body.count("bar-fill bar-fill--") == 7`; percentages in the inline widths sum to 100 (regex the `width: (\d+)%` values). |
| `test_profile_blank_user` | log in as `blank@spendly.com` → `200`, contains `₹0.00`, `>0<`, `—`, and **no** `bar-fill` rows. |
| `test_profile_stale_session` | push a `user_id` for a deleted row into the session → `302 /login` (F4 guard). |

Login helper for the route tests: `client.post("/login", data={"email": ..., "password": "demo123"})`
for the seed user. The blank user has no valid hash — log it in by writing
`session_transaction()["user_id"]` instead, or set a real hash with
`generate_password_hash` in the fixture. Prefer `session_transaction()` (no
password plumbing).

---

## 6. Verification plan

### 6.1 Unit + route suite

```bash
uv run pytest tests/ -q                 # all green, no writes to spendly.db
git status --short -- spendly.db         # empty: tests used tmp_path
```

### 6.2 Manual, seed user (server on 5001 — check the port first)

```bash
rm -f /tmp/spendly5.jar
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://localhost:5001/profile
# → 302 http://localhost:5001/login
curl -s -o /dev/null -c /tmp/spendly5.jar -X POST http://localhost:5001/login \
  -d 'email=demo@spendly.com&password=demo123'
PAGE=$(curl -s -b /tmp/spendly5.jar http://localhost:5001/profile)
for s in 'Demo User' 'demo@spendly.com' '180.19' 'Bills' '₹' 'Member since '; do
  echo "$PAGE" | grep -q "$s" && echo "ok: $s"; done
echo "$PAGE" | grep -o '<td class="tx-date">' | wc -l              # 8
echo "$PAGE" | grep -o 'bar-fill bar-fill--' | wc -l               # 7
echo "$PAGE" | grep -oE 'width: [0-9]+%' | grep -oE '[0-9]+' \
  | paste -sd+ | bc                                                # 100
echo "$PAGE" | grep -oE 'tx-date">[0-9]{2} [A-Z][a-z]{2} [0-9]{4}' | head -3
# → 28 Oct 2026 / 24 Oct 2026 / 20 Oct 2026  (formatted, NOT 2026-10-28)
```

### 6.3 Manual, brand-new user

```bash
curl -s -c /tmp/spendly5b.jar -o /dev/null -X POST http://localhost:5001/register \
  -d 'name=Temp User&email=temp5@spendly.com&password=temp1234'
curl -s -b /tmp/spendly5b.jar -o /dev/null -X POST http://localhost:5001/login \
  -d 'email=temp5@spendly.com&password=temp1234'
NEW=$(curl -s -b /tmp/spendly5b.jar http://localhost:5001/profile)
echo "$NEW" | grep -q '₹0.00' && echo 'ok: zero total'
echo "$NEW" | grep -q '>0<' && echo 'ok: zero count'
echo "$NEW" | grep -o 'bar-fill bar-fill--' | wc -l                # 0
echo "$NEW" | grep -c 'Traceback'                                   # 0
```

### 6.4 Spec rules (grep gates)

```bash
grep -nE 'f"|f\x27|\.format\(' database/queries.py   # empty — no string-built SQL
grep -nE '%s|\+' database/queries.py                # empty — no concatenated SQL
grep -n 'sqlite3' database/queries.py               # empty — go through get_db()
grep -n 'flask' database/queries.py                 # empty — pure helpers
grep -nE '#[0-9a-fA-F]{3,6}' templates/profile.html # empty
grep -n 'style=' templates/profile.html             # only the bar-width line
grep -rn '346\.24' app.py templates/ database/      # empty
grep -rn 'current_user' templates/profile.html      # no output after F4? see §4.3
```

(`profile.html` still legitimately has no `current_user` after the card moves to
`user.*`; the navbar in `base.html` keeps it.)

### 6.5 Scope guard

```bash
git diff --stat
# app.py, templates/profile.html, AGENTS.md + new database/queries.py, tests/
git diff -- database/db.py static/css/style.css templates/base.html   # empty
curl -s http://localhost:5001/expenses/add | head -1                  # Step 7 stub
```

### 6.6 Cleanup

```bash
rm -f /tmp/spendly5.jar /tmp/spendly5b.jar
# delete the temp account only if it was created against the real spendly.db:
#   sqlite3 spendly.db "DELETE FROM users WHERE email='temp5@spendly.com';"
```

---

## 7. DoD mapping

| DoD item | How it is proven |
|---|---|
| Seed user sees "Demo User" / "demo@spendly.com" from the DB | §5.3, §6.2 |
| Total spent = ₹180.19 (**spec's 346.24 corrected, F1**) | §5.2, §6.2 |
| Transaction count = 8 | §5.2, §6.2 |
| Top category = Bills | §5.2, §6.2 |
| 8 rows, newest first | §5.3 (`tx-date` count + order), §6.2 |
| 7 categories, percentages sum to 100 | §5.2 + §5.3, §6.2 |
| Every amount uses ₹ | §6.2 grep; template already had `₹` on all three money fields |
| New user → ₹0.00, 0 transactions, empty breakdown, no errors | §5.3, §6.3 |

---

## 8. Execution order

1. `database/queries.py` — four helpers + `_format_month` (§4.1).
2. `tests/conftest.py` + unit tests; run `uv run pytest tests/ -q -k "not profile_"`
   to validate the data layer before touching the view.
3. `app.py` — `datetime` import, `database.queries` import, `display_date`
   filter, delete the Step 4 constants, rewrite `profile()` (§4.2).
4. `templates/profile.html` — the eight edits in §4.3.
5. Route tests; full `uv run pytest tests/ -q`.
6. Manual passes §6.2 and §6.3.
7. `.pi/specs/05-backend-routes-for-profile-page.md` — fix `346.24` → `180.19`
   (F1), subject to sign-off.
8. `AGENTS.md` — §4.4.
9. Commit on `feature/backend-connection` with the spec + this plan.

---

## 9. Out of scope

- `GET /expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete` — Steps 7–9
  (they must keep returning their placeholder text this step).
- Empty-state copy/illustrations for the table and breakdown; that belongs to the
  pending 04.1 design pass. A brand-new user simply sees an empty table and an
  empty breakdown, as the spec requires.
- Pagination, date filters, search, or sorting controls on the transaction table.
- A `@login_required` decorator refactor (the inline guard matches Steps 3–4).
- Month-scoped totals (the page says "this month" but neither the spec nor the
  queries scope by date).
- Fixing the `--cat-*` colour mapping quirks (F12) or the 04.1 token pass.
- CSRF, rate limiting, connection pooling, `DATABASE` env override.

---

## 10. Risks / watch-outs

| Risk | Mitigation |
|---|---|
| Tests assert 346.24 and fail | F1: implement 180.19, correct the spec in step 7, derive the number from seed data where practical. |
| Tests write to the real `spendly.db` | Patch `database.db.DATABASE` **before** importing `app` (lazy import in the fixture, F7); `git status` check in §6.1. |
| `member_since` test flakes | Never assert a month name; assert `[A-Z][a-z]+ \\d{4}` (seed uses `datetime('now')`). |
| Category percentages sum to 99 | `remainder` applied to the largest row (F6); test asserts `sum == 100`. |
| New user divides by zero | `total <= 0 → []` guard before any division (F6). |
| Template renders `₹0.00` for every category | F2 key rename (`c.total` → `c.amount`, `c.percent` → `c.pct`); §6.2 catches it. |
| Dates render as `2026-10-21` | `display_date` filter (F3); grep in §6.2. |
| Page counts `<tr>` and gets 9 (header row) | Count `tx-date` cells, not `<tr>`. |
| Two dev servers on 5001 | Check the port before `python app.py`; reuse a running server. |
| Stale session for a deleted user 500s | `user is None → session.clear() + redirect` (§4.2). |
| Test assumes exactly one user in the DB | The dev `spendly.db` has 2 users; tests always run against a `tmp_path` DB (F7) and look the demo row up by e-mail, never by `id = 1`. |
| Description `None` prints "None" | `or "—"` fallback (F10). |
| Scope creep into Step 7 stubs | §6.5 asserts the stubs still return their placeholder text. |
