# Implementation Plan — Step 1: Database Setup

**Spec:** `.pi/specs/01-database-setup.md`
**Files to change:** `database/db.py`, `app.py`
**Files to create:** none
**Status:** plan only — no code changed

---

## 1. Objective

Replace the stub in `database/db.py` with a working SQLite data layer (`get_db`, `init_db`, `seed_db`) and wire startup initialization into `app.py`, per the spec. No routes are added or changed.

---

## 2. Current state (verified)

- `database/db.py` — 5-line comment stub only; no imports, no code.
- `database/__init__.py` — present and empty, so `from database.db import ...` resolves from the repo root.
- `app.py` — `Flask(__name__)`, six implemented routes (`/`, `/register`, `/login`, `/terms`, `/privacy`), five placeholder routes, `app.run(debug=True, port=5001)`. No imports from `database`.
- `pyproject.toml` — `flask==3.1.3`, `werkzeug>=3.1.3,<4.0`, `pytest`, `pytest-flask`. No new dependency needed.
- `.gitignore` — already ignores `*.db`, so the SQLite file will not be committed.
- No tests exist (`uv run pytest` exits 5), no linter/formatter/CI.

---

## 3. Decisions and assumptions

| # | Decision | Rationale |
|---|---|---|
| D1 | Database filename: **`spendly.db`** in the repo root | Spec permits `spendly.db` or `expense_tracker.db`; app name is Spendly, and `.gitignore`'s `*.db` already covers it. |
| D2 | Resolve the path from the module, not the CWD: `BASE_DIR = Path(__file__).resolve().parent.parent` | Works under `uv run python app.py`, Flask's reloader, and pytest regardless of working directory. Avoids coupling `db.py` to `current_app`. |
| D3 | `get_db()` returns a **fresh connection per call**; no `flask.g` caching, no teardown handler | Exactly what the spec asks for. Keeps this step minimal; `g` + `teardown_appcontext` can be introduced later only if a step needs it. Callers own closing. |
| D4 | No extra schema beyond the spec: no indexes, no `CHECK` constraints, no `ON DELETE CASCADE` | Spec defines the schema precisely. Cascades/checks are a later product decision. |
| D5 | Seed dates computed at runtime from `date.today()`, clamped to today's day-of-month | Satisfies "spread across the current month" without hardcoded dates that go stale, and avoids seeding future-dated expenses. |
| D6 | `seed_db()` gates on `SELECT COUNT(*) FROM users > 0` and returns early | Straight from the spec. Consequence: if a real user registers before the seed ever runs, demo data is skipped. Acceptable and documented. |
| D7 | Do **not** catch/swallow `sqlite3.IntegrityError` | Spec §13 expects duplicate email and bad `user_id` to fail loudly. Only transaction rollback is handled. |

---

## 4. Proposed implementation

### 4.1 `database/db.py`

Structure (top to bottom):

1. Module docstring.
2. Imports: `sqlite3`, `date` from `datetime`, `Path` from `pathlib`, `generate_password_hash` from `werkzeug.security`.
3. Constants: `BASE_DIR`, `DATABASE`, `CATEGORIES`, `SCHEMA`.
4. `get_db()`
5. `init_db()`
6. Seed data constants + date helper + `seed_db()`

Reference sketch:

```python
"""SQLite helpers for Spendly (no ORM)."""

import sqlite3
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE = BASE_DIR / "spendly.db"

CATEGORIES = ("Food", "Transport", "Bills", "Health",
              "Entertainment", "Shopping", "Other")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    description TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users (id)
);
"""


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        with conn:                      # commits on success
            conn.executescript(SCHEMA)
    finally:
        conn.close()
```

Key points to preserve during implementation:

- `users` must be created **before** `expenses` (FK target).
- `PRAGMA foreign_keys = ON` runs on every connection inside `get_db()` — it is per-connection, not persistent.
- `row_factory = sqlite3.Row` is set before any query so `row["email"]` works.
- `DEFAULT (datetime('now'))` stores **UTC** text timestamps.

### 4.2 Seed data

Demo user (hashed with `generate_password_hash`, default Werkzeug method):

| name | email | plaintext password |
|---|---|---|
| `Demo User` | `demo@spendly.com` | `demo123` |

Eight expenses covering all seven categories (one category repeats), all linked to the demo user, amounts as `REAL`:

| # | Category | Amount | Description |
|---|---|---|---|
| 1 | Food | 12.50 | Lunch at the campus cafe |
| 2 | Transport | 3.75 | Bus fare |
| 3 | Bills | 60.00 | Electricity bill |
| 4 | Health | 25.40 | Pharmacy purchase |
| 5 | Entertainment | 15.99 | Streaming subscription |
| 6 | Shopping | 45.30 | New backpack |
| 7 | Other | 8.00 | Misc. stationery |
| 8 | Food | 9.25 | Coffee and snacks |

Dates: spread across the current month, ascending, none later than today.

```python
def _current_month_dates(count):
    today = date.today()
    if today.day == 1:
        days = [1] * count
    else:
        days = [1 + round(i * (today.day - 1) / (count - 1))
                for i in range(count)]
    return [date(today.year, today.month, day).isoformat() for day in days]
```

Note: when `today.day < 8`, `round()` yields some duplicate days — still valid, same-month, non-future dates, and the spec only requires "spread across the current month". Dates use `isoformat()` so they are always `YYYY-MM-DD`.

`seed_db()` flow:

1. `conn = get_db()`
2. `with conn:` transaction:
   - `SELECT COUNT(*) AS count FROM users` → if `> 0`, return early (idempotency gate).
   - `INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)` with the hashed password; capture `cursor.lastrowid`.
   - `conn.executemany("INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)", rows)` where each row uses the captured `user_id`.
3. `finally: conn.close()`
4. Let `sqlite3.Error` propagate uncaught.

Reference sketch:

```python
def seed_db():
    conn = get_db()
    try:
        with conn:
            existing = conn.execute(
                "SELECT COUNT(*) AS count FROM users"
            ).fetchone()["count"]
            if existing:
                return

            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Demo User", "demo@spendly.com",
                 generate_password_hash("demo123")),
            )
            user_id = cursor.lastrowid

            dates = _current_month_dates(len(SEED_EXPENSES))
            conn.executemany(
                "INSERT INTO expenses "
                "(user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (user_id, amount, category, dates[i], description)
                    for i, (category, amount, description)
                    in enumerate(SEED_EXPENSES)
                ],
            )
    finally:
        conn.close()
```

### 4.3 `app.py`

Add the import near the top and a startup block immediately after `app = Flask(__name__)`, before the routes:

```python
from database.db import get_db, init_db, seed_db

app = Flask(__name__)

# Ensure the database and demo data exist before any route is used.
with app.app_context():
    init_db()
    seed_db()
```

Notes:

- `get_db` is imported per spec §6 even though startup does not call it; later steps (auth, profile, expenses) use it. There is no linter, so the unused import is intentional and harmless.
- `app.app_context()` is not strictly required today because `db.py` resolves its path from `__file__` (D3), but it matches the spec and future-proofs against a later switch to `current_app.config`.
- Flask's debug reloader imports the module twice; `init_db()` is idempotent and `seed_db()` is gated, so no duplicate rows.
- Importing `app` (including from pytest) performs DB init as a side effect. That is the behavior the spec mandates.

---

## 5. Verification plan

Run from the repo root.

### 5.1 Startup and schema

```bash
rm -f spendly.db                      # clean slate
uv run python - <<'PY'
from database.db import get_db

conn = get_db()
print("db file:", conn.execute("PRAGMA database_list").fetchone()["file"])
print("fk_enabled:", conn.execute("PRAGMA foreign_keys").fetchone()[0])
for row in conn.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='table' "
    "AND name IN ('users','expenses') ORDER BY name"
):
    print(row["name"], "->", row["sql"])
conn.close()
PY
```

Expected: `spendly.db` in the repo root, `fk_enabled: 1`, both tables present with the columns/constraints from spec §4.

### 5.2 Seed contents

```bash
uv run python - <<'PY'
import re
from datetime import date
from werkzeug.security import check_password_hash
from database.db import get_db, CATEGORIES

conn = get_db()
users = conn.execute("SELECT * FROM users").fetchall()
expenses = conn.execute("SELECT * FROM expenses ORDER BY date").fetchall()

assert len(users) == 1, users
u = users[0]
assert (u["name"], u["email"]) == ("Demo User", "demo@spendly.com")
assert u["password_hash"] != "demo123"
assert check_password_hash(u["password_hash"], "demo123")

assert len(expenses) == 8, len(expenses)
assert {e["category"] for e in expenses} == set(CATEGORIES)
assert {e["user_id"] for e in expenses} == {u["id"]}
month = date.today().strftime("%Y-%m")
for e in expenses:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["date"]), e["date"]
    assert e["date"].startswith(month), e["date"]
    assert isinstance(e["amount"], float) and e["amount"] > 0
print("seed OK:", len(users), "user,", len(expenses), "expenses")
conn.close()
PY
```

### 5.3 Idempotency

```bash
uv run python - <<'PY'
from database.db import seed_db, get_db
seed_db(); seed_db()
conn = get_db()
print("users:", conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
print("expenses:", conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0])
conn.close()
PY
```

Expected: still `1` and `8`.

### 5.4 Constraint enforcement

```bash
uv run python - <<'PY'
import sqlite3
from database.db import get_db

conn = get_db()
try:
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Dup", "demo@spendly.com", "x"),
    )
    print("FAIL: duplicate email accepted")
except sqlite3.IntegrityError as exc:
    print("unique OK:", exc)
conn.rollback()

try:
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date) "
        "VALUES (?, ?, ?, ?)",
        (99999, 1.0, "Food", "2026-10-01"),
    )
    print("FAIL: bad user_id accepted")
except sqlite3.IntegrityError as exc:
    print("fk OK:", exc)
conn.rollback()
conn.close()
PY
```

Expected: both print `OK` with an `IntegrityError` (UNIQUE constraint / FOREIGN KEY constraint).

### 5.5 App integration

```bash
uv run python -c "from app import app; c = app.test_client(); print(c.get('/').status_code, c.get('/login').status_code, c.get('/register').status_code)"
```

Expected: `200 200 200`, no traceback, and `spendly.db` created if it did not exist.

Optionally run the dev server once (`uv run python app.py`, port 5001) and confirm it boots cleanly; stop it afterward. Do not leave a duplicate server on 5001.

`uv run pytest` will still exit 5 (no tests exist) — do **not** report tests as passing.

---

## 6. Edge cases and risks

| Risk | Handling |
|---|---|
| Debug reloader imports `app` twice | `init_db()` uses `IF NOT EXISTS`; `seed_db()` early-returns when users exist. |
| `with conn:` commits but does **not** close | Every function has an explicit `finally: conn.close()`; do not rely on `with` for closing. |
| CWD differs (pytest, IDE run config) | Path is anchored to `Path(__file__)`, not `os.getcwd()`. |
| Seed runs before a real registration | Demo user always exists in dev; Step 2's register route must handle a non-empty `users` table (unique email is the only conflict). |
| Real user exists, demo user never seeded | Acceptable per spec; seed gate is user-count based. |
| `today.day < 8` yields repeated expense dates | Still current-month, non-future, valid `YYYY-MM-DD`. |
| `REAL` money is binary floating point | Mandated by spec §11; format with `:,.2f` at render time in later steps. |
| `sqlite3.Row` lacks `.get()` | Later steps must use `row["col"]` or `dict(row)`. |
| Timestamps are UTC | `datetime('now')` is UTC; display conversion, if wanted, is a later concern. |
| Password hashing cost on startup | One scrypt hash (~tens of ms) on first boot only; subsequent boots return early. |

---

## 7. Out of scope

- No new routes; all placeholder routes stay as they are (per `AGENTS.md`).
- No changes to templates, CSS, JS, `src/`, or dependencies.
- No tests added (spec lists no test file); verification is manual/scripted as in §5.
- No `flask.g` caching, connection pooling, teardown handler, indexes, migrations, or ORM.
- `AGENTS.md` will be stale after this step (it describes `database/db.py` as a stub). Updating it is optional and outside the spec's "Files to Change" list — flag for a follow-up if desired.

---

## 8. Definition-of-Done mapping

| Spec §14 item | Covered by |
|---|---|
| Database file created on app startup | §4.3 startup block; verified §5.5 |
| Both tables with correct schema/constraints | §4.1 `SCHEMA`; verified §5.1 |
| Demo user with hashed password | §4.2; verified §5.2 (`check_password_hash`) |
| 8 expenses across categories | §4.2 table; verified §5.2 |
| No duplicate seed on repeated runs | §4.2 count gate; verified §5.3 |
| App starts without errors | §4.3; verified §5.5 |
| Foreign key enforcement works | `PRAGMA` in `get_db()`; verified §5.1 + §5.4 |
| All queries parameterized | All inserts/selects use `?` placeholders; schema DDL is static |

---

## 9. Execution order

1. Write `database/db.py` (§4.1 → §4.2).
2. Wire `app.py` (§4.3).
3. Run §5.1–§5.5; delete `spendly.db` and re-run §5.1 once to confirm a clean first boot.
4. Report results, including any deviation from this plan.
