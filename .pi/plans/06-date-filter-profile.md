# Implementation Plan — Step 6: Date Filter for Profile Page

**Spec:** `.pi/specs/06-date-filter-profile.md`
**Branch:** `feature/date-filter-profile` (already checked out — no branch work needed)
**Files to change:** `app.py`, `database/queries.py`, `templates/profile.html`,
`static/css/style.css`, `AGENTS.md`
**Files to create:** `tests/test_date_filter.py`
**Status:** plan only — no application code changed (planning mode)
**Locked decisions:** filter lives in `GET /profile` query params only, no new
routes; presets are anchors, the custom range is a `GET` form, active state is
computed server-side per request (`presets` list with `active` flags); all four
presets end **today**; one-sided ranges are supported; dates are normalised to
canonical zero-padded ISO before hitting SQL; the query layer gets one shared
`_date_filter()` helper; no JS, no new deps, no schema change, no new stylesheet.

---

## 1. Objective

Let the signed-in user scope `/profile` to a date range, without adding a route,
a dependency, or any client-side state.

1. `database/queries.py` — `get_summary_stats`, `get_recent_transactions`,
   `get_category_breakdown` accept optional `date_from` / `date_to` and apply a
   shared, fully parameterised `date` clause (including the top-category
   aggregate).
2. `app.py` — `profile()` validates and normalises both params, rejects inverted
   ranges with a flash, computes the four preset windows, and passes
   `date_from`, `date_to`, `presets` to the template.
3. `templates/profile.html` — filter bar (presets + custom range), neutral
   subtitle, empty-state rows.
4. `static/css/style.css` — `.filter-*` and `.empty-note` rules in the existing
   Profile block, tokens only, responsive stacking.
5. `tests/test_date_filter.py` — helper unit tests, query-layer range tests, and
   route tests for every DoD bullet. Existing 15 tests stay untouched and green.

---

## 2. Current state (verified)

| Item | Verified state |
|---|---|
| Branch / git | On `feature/date-filter-profile`. Working tree has exactly one untracked file: `.pi/specs/06-date-filter-profile.md`. |
| `app.py` — `profile()` | Login guard `session.get("user_id") is None → redirect(url_for("login"))`; stale-user guard clears session + flashes `"Please sign in again."`; renders `profile.html` with `user`, `summary`, `transactions`, `categories`. No query-string handling yet. |
| `app.py` — imports | `from datetime import datetime` already present (used by `display_date`). `request`, `flash`, `url_for` already imported. `date` is **not** imported yet — needed. |
| `app.py` — helper space | `EMAIL_RE` sits above the routes; a good home for `_parse_iso_date` / `_month_start` / `_build_presets` is right under it, above the "Template globals" banner. |
| `database/queries.py` | Four helpers, each `get_db()` → `try/finally: conn.close()`. SQL uses `?` placeholders. `get_recent_transactions(user_id, limit=10)` orders `date DESC, id DESC`; breakdown rounds `pct` then gives the remainder to the largest row; `total <= 0 → []` guard exists. |
| Existing call sites | `app.py` lines ~216-218 call all three with `(user_id)` only. `tests/test_backend_connection.py` calls them positionally (`get_recent_transactions(demo_user_id)`, `get_category_breakdown(blank_user_id)`) and once with `limit=3`. Trailing `date_from=None, date_to=None` keeps every call site valid. |
| `templates/profile.html` | Four sections: user card → `.profile-stats` → `.profile-columns` (table + breakdown). One sanctioned inline style: `style="width: {{ c.pct }}%"`. Subtitle currently reads "…this month." (now inaccurate). `₹` on all three money fields. |
| `static/css/style.css` | 899 lines. Profile block starts line 681; `.profile-user-card` ends ~line 712, `.profile-stats` begins line 727 → **insert the filter bar rules between them**. Responsive blocks: `@media (max-width: 900px)` (834) and `(max-width: 600px)` (846). Reusable rules: `.btn-primary` (358), `.btn-ghost` (375), `.flash--success` (532) — **no `.flash--error` rule exists**, so the error flash falls back to the neutral `.flash` border (same as today for login errors rendered through `auth-error`). Tokens: `--ink*`, `--paper*`, `--accent*`, `--border*`, `--text-*`, `--space-*`, `--radius-*`, `--dur-*`, `--ease`, `--font-*`. No `.filter-*` or `.empty-note` rules exist. |
| `tests/` | `tests/conftest.py` (patches `database.db.DATABASE` to `tmp_path` **before** importing `app`) + `tests/test_backend_connection.py` with **15 tests**, all passing. Fixtures: `temp_db`, `app`, `client`, `demo_user_id`, `blank_user_id`. |
| `database/db.py` | `_current_month_dates(8)` spreads the 8 seed rows across the **current month only** → seed data cannot distinguish "This Month" from "Last 6 Months". Filter tests need their own dated rows. |
| Live `spendly.db` (read-only) | User 1 `demo@spendly.com` → 8 expenses, all **2026-10-01 … 2026-10-28**, total **₹180.19**. User 2 `nitish@gmail.com` → 5 expenses in 2026-05 / 2026-07 / 2026-10. `date` is today **2026-11-05**. |
| Dependency versions | `flask==3.1.3`, `pytest==8.3.5`, `pytest-flask==1.3.0`, `werkzeug>=3.1.3,<4.0`. Nothing to add. |
| `url_for` behaviour (checked live) | `url_for("profile", date_from=None, date_to=None)` → `/profile`; with values → `/profile?date_from=…&date_to=…`; with `""` → `/profile?date_from=&date_to=` (empty params are **kept**). |

---

## 3. Findings and resolutions

### F1 — `static/css/profile.css` does not exist → `style.css`
The spec's first draft pointed at a per-page stylesheet; the repo has exactly one
(`static/css/style.css`, loaded by `base.html`). All filter styles go in the
Profile block there, using the existing tokens; **do not create**
`static/css/profile.css`.

### F2 — `url_for` keeps empty strings → presets must use `None`
Verified: `date_from=""` renders `?date_from=&date_to=`, which is not the "clean
`/profile` URL" the spec requires for All Time. Therefore `presets` carries
`None` for All Time, and route logic normalises `""`/whitespace to `None` before
it reaches the template. Input `value` attributes use `{{ date_from or '' }}`
(that is an attribute, not a URL).

### F3 — SQLite TEXT comparison is lexical → normalise before querying
`expenses.date` is `TEXT`. `strptime("%Y-%m-%d")` happily accepts `2026-1-5`,
which would compare wrongly (`"2026-1-5" > "2026-12-31"` lexically). So
`_parse_iso_date()` returns `.date().isoformat()` (`2026-01-05`), never the raw
input. This also means the template echoes a canonical value, so the active-range
comparison in `_build_presets` is a plain string equality.

### F4 — The top-category query must be filtered too
`get_summary_stats` runs two statements (SUM/COUNT and the top-category
aggregate). The spec's wording ("the `expenses` queries") is easy to read as
"the totals query". Applying the clause to only one produces a page where the
total is filtered but "Top category" names an out-of-range category. Both
statements get the clause.

### F5 — Clause concatenation order matters (`GROUP BY`, `ORDER BY`, `LIMIT`)
`_date_filter` returns a fragment that must be appended directly after
`WHERE user_id = ?` and **before** any `GROUP BY` / `ORDER BY` / `LIMIT`:

```python
"SELECT … FROM expenses WHERE user_id = ?" + clause + " GROUP BY category …"
```

A fragment appended after `GROUP BY` would be a syntax error, so the helper
returns an empty string when unfiltered (no stray leading `AND`).

### F6 — Presets end today, so future rows are invisible
Seed data can contain future-dated rows (users may back/forward-date expenses in
Steps 7–9). All four presets set `date_to = date.today().isoformat()` per the
spec table, so only All Time (or a custom `date_to` past today) can surface them.
Tests pin this with a deliberate `today + 15 days` row.

### F7 — Month arithmetic must roll over correctly
"Last 3 Months" = first day of the month **two months back** → needs integer
maths, not 30-day subtraction:

```python
total = day.year * 12 + day.month - 1 - months_back
year, month = divmod(total, 12)          # month is 0-based here
return date(year, month + 1, 1)          # → 1-based first day
```

The helper is a separate function so rollover can be unit-tested with fixed
dates (Jan/Mar, leap Feb) instead of today's clock.

### F8 — One-sided ranges, and independent validation
The spec requires per-parameter validation: a malformed `date_from` must not
discard a valid `date_to`. So `_parse_iso_date` is called per param, and
`_date_filter` emits `date >= ?`, `date <= ?`, or both. Inverted ranges are the
only cross-parameter error path (`date_from > date_to` → both cleared + flash);
`date_from == date_to` is a valid single day.

### F9 — Flash must be rendered in the *same* response
The inverted-range request is not a redirect: `flash(...)` then `render_template`
in the same view call. `base.html` renders `get_flashed_messages()` from the same
request context, so the message appears in the `client.get(...)` body — that is
what the route test asserts. No need for `follow_redirects`.

### F10 — Test rows must not come from the seed
`seed_db()` puts all 8 demo rows inside the current calendar month, so
"This Month" vs "Last 6 Months" would look identical. `tests/test_date_filter.py`
therefore creates a **dedicated user** whose expenses sit on month boundaries
relative to `date.today()` (today, first-of-month ×4 at −0/−2/−5/−7, and one
future row). Expected totals are computed from that fixture row list, never
hardcoded, and the live DB is untouched.

### F11 — Helper unit tests need the temp DB first
`app.py` runs `init_db()` + `seed_db()` at import. Importing `app` at module
scope in the new test file would seed the **real** `spendly.db`. Helper tests
(`_parse_iso_date`, `_month_start`) therefore `import app` **inside the test
body** with the `temp_db` fixture requested in the signature — same discipline as
the existing lazy import in `conftest.py`'s `app` fixture.

### F12 — HTML-escaped ampersands in links
`url_for` output is HTML-escaped by Jinja: `?date_from=2026-09-01&date_to=…`
renders as `&amp;`. Tests must assert on substrings (`date_from=2026-09-01`), not
on the whole URL. If a test needs to *follow* a preset href, `html.unescape()` it
first.

### F13 — Empty states, without touching existing assertions
Jinja `{% for %} … {% else %} … {% endfor %}` handles both empty cases:

- table: `<tr><td class="empty-note" colspan="4">No transactions in this range.</td></tr>`
- breakdown: `<p class="empty-note">No spending in this range.</p>`

Step 5's `test_profile_blank_user` asserts `"bar-fill" not in body` and
`'<td class="tx-date">' not in body` — neither string appears in the new markup,
so it keeps passing.

### F14 — Reuse existing button styles
`.btn-primary` (ink fill) and `.btn-ghost` (bordered) already exist and are
token-based. The filter bar reuses them (`class="btn-primary filter-apply"`,
`class="btn-ghost filter-clear"`) instead of inventing a fourth button style.
New CSS is limited to layout/active-state rules.

### F15 — Error flash has no dedicated rule
`.flash--error` is not styled (`base.html` emits the class; only `.flash` and
`.flash--success` exist). Login/register errors use `.auth-error` instead. Leave
the flash visuals alone this step (the message still renders legibly with the
neutral `.flash` border) — restyling flashes is the pending 04.1 pass, not Step 6.

### F16 — `AGENTS.md` goes stale again
Update: `/profile` route row (Steps 5–6), query-helper note (accepts
`date_from`/`date_to`), test count, and the "implemented vs stub" table stays
otherwise intact.

---

## 4. Proposed implementation

### 4.1 `app.py` — imports, date helpers, preset builder

Change the import line to `from datetime import date, datetime`.

Insert directly below `EMAIL_RE` (module level, above the template globals):

```python
ISO_DATE_FORMAT = "%Y-%m-%d"

# Filter presets: (key, label, months back for the first day, end today).
PROFILE_PRESETS = (
    ("this_month", "This Month", 0),
    ("last_3_months", "Last 3 Months", 2),
    ("last_6_months", "Last 6 Months", 5),
)


def _parse_iso_date(value):
    """Normalise 'YYYY-MM-DD' to canonical ISO; None for missing/invalid input.

    strptime accepts unpadded input ('2026-1-5'), but SQLite compares the TEXT
    `date` column lexicographically, so only zero-padded values may reach SQL.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), ISO_DATE_FORMAT).date().isoformat()
    except (AttributeError, ValueError):
        return None


def _month_start(day, months_back=0):
    """First day of the month `months_back` months before `day`'s month."""
    total = day.year * 12 + day.month - 1 - months_back
    year, month = divmod(total, 12)
    return date(year, month + 1, 1).isoformat()


def _build_presets(today, date_from, date_to):
    """Preset windows for the filter bar, each annotated with `active`."""
    presets = [
        {
            "key": key,
            "label": label,
            "date_from": _month_start(today, months_back),
            "date_to": today.isoformat(),
        }
        for key, label, months_back in PROFILE_PRESETS
    ]
    presets.append(
        {"key": "all_time", "label": "All Time",
         "date_from": None, "date_to": None}
    )
    for preset in presets:
        preset["active"] = (
            preset["date_from"] == date_from and preset["date_to"] == date_to
        )
    return presets
```

### 4.2 `app.py` — `profile()` view

Everything above the render call is unchanged (login guard, stale-session
guard). Then:

```python
    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))

    # An inverted range is a user error: fall back to the unfiltered view.
    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.", "error")
        date_from = date_to = None

    today = date.today()
    return render_template(
        "profile.html",
        user=user,
        summary=get_summary_stats(user_id, date_from=date_from, date_to=date_to),
        transactions=get_recent_transactions(
            user_id, date_from=date_from, date_to=date_to
        ),
        categories=get_category_breakdown(
            user_id, date_from=date_from, date_to=date_to
        ),
        date_from=date_from,
        date_to=date_to,
        presets=_build_presets(today, date_from, date_to),
    )
```

Keyword arguments (not positional) for the query helpers: `get_recent_transactions`
signature is `(user_id, limit=10, date_from=None, date_to=None)`, so
`get_recent_transactions(uid, date_from, date_to)` would bind `date_from` to
`limit`. No `today` variable is passed to the template — nothing needs it.

### 4.3 `database/queries.py` — shared clause + three signatures

Add above the helpers:

```python
def _date_filter(date_from=None, date_to=None):
    """Inclusive `date` bounds as a SQL fragment + params; empty when unfiltered.

    Returns e.g. (" AND date >= ? AND date <= ?", ("2026-09-01", "2026-11-05")).
    """
    clauses, params = [], []
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)
    if not clauses:
        return "", ()
    return " AND " + " AND ".join(clauses), tuple(params)
```

`get_summary_stats` becomes (clause appended in **both** statements, before
`GROUP BY`):

```python
def get_summary_stats(user_id, date_from=None, date_to=None):
    clause, date_params = _date_filter(date_from, date_to)
    params = (user_id, *date_params)
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
            "FROM expenses WHERE user_id = ?" + clause,
            params,
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?" + clause +
            " GROUP BY category ORDER BY SUM(amount) DESC, category ASC LIMIT 1",
            params,
        ).fetchone()
    finally:
        conn.close()
    ...  # unchanged return dict
```

`get_recent_transactions` — clause before `ORDER BY`, `LIMIT ?` stays last:

```python
def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    clause, date_params = _date_filter(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ?" + clause +
            " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *date_params, int(limit)),
        ).fetchall()
    finally:
        conn.close()
    ...  # unchanged list comprehension
```

`get_category_breakdown` — same pattern (clause before `GROUP BY`); the
`if not rows: return []` / `total <= 0` / remainder logic is untouched:

```python
def get_category_breakdown(user_id, date_from=None, date_to=None):
    clause, date_params = _date_filter(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ?" + clause +
            " GROUP BY category ORDER BY total DESC, category ASC",
            (user_id, *date_params),
        ).fetchall()
    finally:
        conn.close()
    ...  # unchanged pct/remainder logic
```

Docstring at module top gains one line: "Optional `date_from`/`date_to` (ISO
`YYYY-MM-DD`, inclusive) narrow every helper to that range."

### 4.4 `templates/profile.html` — filter bar, subtitle, empty states

Insert between `</div>` of `.profile-user-card` and `<div class="profile-stats">`:

```html
        <div class="filter-bar">
            <nav class="filter-presets" aria-label="Date range presets">
                {% for preset in presets %}
                <a class="filter-preset{% if preset.active %} filter-preset--active{% endif %}"
                   href="{{ url_for('profile', date_from=preset.date_from, date_to=preset.date_to) }}"
                   {%- if preset.active %} aria-current="page"{% endif %}>{{ preset.label }}</a>
                {% endfor %}
            </nav>
            <form class="filter-range" method="get" action="{{ url_for('profile') }}">
                <div class="filter-field">
                    <label for="date_from">Start date</label>
                    <input type="date" id="date_from" name="date_from"
                           value="{{ date_from or '' }}">
                </div>
                <div class="filter-field">
                    <label for="date_to">End date</label>
                    <input type="date" id="date_to" name="date_to"
                           value="{{ date_to or '' }}">
                </div>
                <button type="submit" class="btn-primary filter-apply">Apply</button>
                <a class="btn-ghost filter-clear" href="{{ url_for('profile') }}">Clear</a>
            </form>
        </div>
```

Subtitle (line 12): `A snapshot of where your money went this month.` →
`A snapshot of where your money went.`

Table body — keep the existing row markup, add the `else` branch:

```html
                        <tbody>
                            {% for t in transactions %}
                            <tr>…unchanged…</tr>
                            {% else %}
                            <tr>
                                <td class="empty-note" colspan="4">No transactions in this range.</td>
                            </tr>
                            {% endfor %}
                        </tbody>
```

Breakdown — same pattern:

```html
                <div class="breakdown">
                    {% for c in categories %}
                    <div class="breakdown-row">…unchanged…</div>
                    {% else %}
                    <p class="empty-note">No spending in this range.</p>
                    {% endfor %}
                </div>
```

No other markup changes; the one `style="width: {{ c.pct }}%"` stays.

### 4.5 `static/css/style.css` — filter bar + empty note

Insert after `.profile-user-card` (line ~712), before `.profile-name`/`.profile-stats`.
Tokens only, no shadows, no hex:

```css
.filter-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-4);
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-4) var(--space-5);
    margin-bottom: var(--space-5);
}

.filter-presets { display: flex; flex-wrap: wrap; gap: var(--space-2); }

.filter-preset {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius-full);
    color: var(--ink-muted);
    font-size: var(--text-sm);
    font-weight: 500;
    text-decoration: none;
    white-space: nowrap;
    transition: background var(--dur-2) var(--ease),
                border-color var(--dur-2) var(--ease),
                color var(--dur-2) var(--ease);
}

.filter-preset:hover { border-color: var(--border-strong); color: var(--ink); }

.filter-preset--active {
    background: var(--accent-light);
    border-color: var(--accent-light);
    color: var(--accent-strong);
}

.filter-range {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-2);
}

.filter-field { display: flex; flex-direction: column; gap: var(--space-1); }

.filter-field label {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--ink-faint);
}

.filter-field input {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-family: var(--font-body);
    font-size: var(--text-sm);
    color: var(--ink);
    background: var(--paper);
}

.filter-apply { padding: var(--space-2) var(--space-4); font-size: var(--text-sm); }

.filter-clear {
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-sm);
    color: var(--ink-muted);
}

.filter-clear:hover { color: var(--ink); }

.empty-note {
    padding: var(--space-3) 0;
    color: var(--ink-faint);
    font-size: var(--text-sm);
}
```

Responsive additions (inside the existing blocks, matching surrounding style):

- `@media (max-width: 900px)`: `.filter-bar { flex-direction: column; align-items: stretch; }`
  and `.filter-range { justify-content: space-between; }`.
- `@media (max-width: 600px)`: `.filter-field { flex: 1 1 45%; }`,
  `.filter-field input { width: 100%; }`, `.filter-range { gap: var(--space-3); }`.

*(Optional, only if the 900px column layout looks cramped in the browser:
`.filter-presets { justify-content: flex-start; }` — no new tokens.)*

### 4.6 `AGENTS.md` — after the code lands

- Route table: `GET /profile` → `Implemented — Step 5–6 (live per-user queries + date filter)`.
- Database/queries paragraph: note that all three helpers accept optional
  `date_from` / `date_to` ISO bounds and share `_date_filter()`.
- Commands: test count `15` → the new total (expected ~39).
- Templates note: filter presets are anchors, the range is a `GET` form, active
  state comes from `presets`.
- Leave the 04.1 pending-pass paragraph as is (filter bar uses the existing
  tokens; the rest of the pass is still pending).

---

## 5. Test plan

New file only: `tests/test_date_filter.py`. `tests/conftest.py`,
`tests/test_backend_connection.py`, `app.py`'s fixtures, and the DB stay as they
are.

### 5.1 Fixtures (in the new file)

```python
from datetime import date, timedelta

import pytest

import database.db as db_module


def _month_start(day, months_back=0):
    """Independent re-implementation of app._month_start (see F7)."""
    total = day.year * 12 + day.month - 1 - months_back
    year, month = divmod(total, 12)
    return date(year, month + 1, 1).isoformat()


@pytest.fixture
def dated_user(temp_db):
    """User whose expenses sit on month boundaries relative to today.

    Returns (user_id, rows) with rows = [(iso_date, amount), ...]:
      today           10.00   (in every preset)
      first-of-month   20.00   (in every preset)
      -2 months first  30.00   (This Month no, Last 3 yes, Last 6 yes)
      -5 months first  40.00   (Last 3 no, Last 6 yes)
      -7 months first  50.00   (presets no, All Time yes)
      today + 15 days  60.00   (presets no, All Time yes)
    """
    today = date.today()
    rows = [
        (today.isoformat(), 10.00),
        (_month_start(today, 0), 20.00),
        (_month_start(today, 2), 30.00),
        (_month_start(today, 5), 40.00),
        (_month_start(today, 7), 50.00),
        ((today + timedelta(days=15)).isoformat(), 60.00),
    ]
    categories = ("Food", "Bills")
    conn = db_module.get_db()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Dated User", "dated@spendly.com", "x"),
            )
            user_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                [(user_id, amount, categories[i % 2], day, "dated")
                 for i, (day, amount) in enumerate(rows)],
            )
    finally:
        conn.close()
    return user_id, rows


def expected(rows, date_from=None, date_to=None):
    """Total/count of fixture rows inside an inclusive ISO range."""
    picked = [
        amount for day, amount in rows
        if (date_from is None or day >= date_from)
        and (date_to is None or day <= date_to)
    ]
    return round(sum(picked), 2), len(picked)


@pytest.fixture
def dated_client(client, dated_user):
    user_id, _ = dated_user
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client
```

Zero-collision notes: `-0`/`-2`/`-5`/`-7` months always differ (even in January),
and the future row is 15 days out, so it can never collide with `today`'s month
boundaries in a way that breaks the expectations (the `expected()` helper derives
everything from the row list anyway).

### 5.2 Helper unit tests (F11: import inside the test, after `temp_db`)

| Test | Assertions |
|---|---|
| `test_parse_iso_date` (parametrised) | `"2026-11-05"` → same; `"2026-1-5"` → `"2026-01-05"`; `" 2026-01-05 "` → `"2026-01-05"`; `""` / `None` → `None`; `"not-a-date"` → `None`; `"2026-02-30"` → `None`. |
| `test_month_start` (parametrised) | `(2026,11,5,0)` → `2026-11-01`; `(2026,1,15,2)` → `2025-11-01`; `(2026,3,31,6)` → `2025-09-01`; `(2024,2,29,1)` → `2024-01-01`. |

### 5.3 Query-layer tests (`dated_user`)

| Test | Assertions |
|---|---|
| `test_summary_unfiltered_matches_step5` | `get_summary_stats(uid)` == `expected(rows)` totals; `transaction_count == 6`; `top_category` from the unfiltered set. |
| `test_summary_date_range` | Range = first-of-month(−2) … today → `expected(rows, lo, hi)`; `top_category` recomputed from that subset (assert it flips to the category of the largest in-range row). |
| `test_transactions_date_range` | Only in-range rows; every dict has exactly `{date, description, category, amount}`; dates sorted desc. |
| `test_transactions_limit_with_filter` | `limit=2` over All Time → the two newest rows (future row first), sum `70.00`; proves `LIMIT ?` still binds last (F5). |
| `test_breakdown_date_range` | Only in-range categories; `pct` ints; `sum(pct) == 100`; `amounts` sorted desc. |
| `test_breakdown_empty_range` | Range `2000-01-01 … 2000-12-31` → `[]`; `get_summary_stats` → `{"total_spent": 0, "transaction_count": 0, "top_category": "—"}`; `get_recent_transactions` → `[]`. |
| `test_one_sided_bounds` | `date_from` only vs `date_to` only, both compared against `expected()` with the matching side. |

### 5.4 Route tests (`dated_client`)

| Test | Assertions |
|---|---|
| `test_profile_no_params_is_unfiltered` | 200; total equals All Time `expected(rows)`; 6 `tx-date` cells; exactly one `.filter-preset--active` and one `aria-current="page"`; that active link is All Time; its `href` is exactly `/profile`. |
| `test_profile_preset_hrefs` | Page contains `date_from=<month0>` / `date_from=<month−2>` / `date_from=<month−5>` and `date_to=<today>` substrings (F12: substring, not full URL). |
| `test_each_preset_filters_all_sections` (parametrised over the three dated presets) | For each preset window from the page href: total + row count match `expected(rows, lo, hi)`; the matching preset is the only active one; no future-row total leaks in. |
| `test_profile_custom_range` | `?date_from=<−4m first>&date_to=<−3m first>`: only in-range rows; **no** preset active; both inputs prefilled with those exact ISO values. |
| `test_profile_single_day_range` | Same `date_from`/`date_to` (today) → 200, total equals `expected(rows, today, today)`. |
| `test_profile_inverted_range_flashes` | `date_from=today&date_to=<today−1d>` → 200; body contains `Start date must be before end date.`; total is the unfiltered All Time total; All Time active. |
| `test_profile_malformed_date_is_ignored` | `date_from=not-a-date&date_to=<today>` → 200 (no 500); total equals `expected(rows, None, today)` (valid upper bound still applied — F8); no flash text. |
| `test_profile_one_sided_from` | `?date_from=<−6m first>` only → total equals `expected(rows, that_date, None)` (future row included). |
| `test_profile_empty_range` | `?date_from=2000-01-01&date_to=2000-12-31` → `₹0.00`, `>0<`, no `bar-fill`, `No transactions in this range.`, `No spending in this range.`, 200. |
| `test_profile_requires_login_with_params` | `client.get("/profile?date_from=…")` → 302 `/login` (unauthenticated client, not `dated_client`). |
| `test_presets_never_emit_empty_params` | Body contains no `date_from=&` / `date_to=&` and no `date_to=None` (F2 guard). |

Use a tiny local helper for the flash assertion:

```python
FLASH = "Start date must be before end date."

def _total(body):
    """Extract the rendered total from the first stat card."""
    return re.search(r"₹([\d,]+\.\d{2})", body).group(1)
```

`₹` formatting is `"%.2f"` today (no thousands separators), so `_total` works; if
formatting changes later the regex still matches.

---

## 6. Verification plan

### 6.1 Automated

```bash
uv run pytest -q                        # existing 15 + new ~24, all green
git status --short -- spendly.db        # unchanged / untracked (gitignored)
```

### 6.2 Manual, live server (port 5001; reuse a running instance)

Today is **2026-11-05** and the demo user's expenses are all October 2026, so the
expected values below are exact — if the plan is executed on a different date,
recompute the "This Month" window (the seed rows stay in October).

```bash
rm -f /tmp/spendly6.jar
curl -s -o /dev/null -c /tmp/spendly6.jar -X POST http://localhost:5001/login \
  -d 'email=demo@spendly.com&password=demo123'

P() { curl -s -b /tmp/spendly6.jar "http://localhost:5001/profile$1"; }

echo "All Time:";   P ""                                  | grep -o '₹[0-9.]*' | head -1   # ₹180.19
echo "This Month:"; P "?date_from=2026-11-01&date_to=2026-11-05" | grep -o '₹[0-9.]*' | head -1   # ₹0.00
echo "Last 3:";     P "?date_from=2026-09-01&date_to=2026-11-05" | grep -o '₹[0-9.]*' | head -1   # ₹180.19
echo "Last 6:";     P "?date_from=2026-06-01&date_to=2026-11-05" | grep -o '₹[0-9.]*' | head -1   # ₹180.19
echo "Custom:";     P "?date_from=2026-10-01&date_to=2026-10-15" | grep -o '₹[0-9.]*' | head -1   # ₹101.65
echo "Rows This Month:"; P "?date_from=2026-11-01&date_to=2026-11-05" | grep -c 'tx-date'          # 0
echo "Rows Custom:";     P "?date_from=2026-10-01&date_to=2026-10-15" | grep -c 'tx-date'          # 4
echo "Empty notes:";     P "?date_from=2026-11-01&date_to=2026-11-05" | grep -o 'No .* in this range.' | sort -u

P "?date_from=2026-10-31&date_to=2026-10-01" | grep -o 'Start date must be before end date.'   # flash
P "?date_from=not-a-date"                   | grep -o '₹[0-9.]*' | head -1                     # ₹180.19
P ""                                        | grep -oE 'filter-preset filter-preset--active|aria-current="page"' | sort | uniq -c   # 1 each
P ""                                        | grep -o 'href="/profile"' | wc -l                # ≥1 (All Time + Clear)
P ""                                        | grep -c 'date_from=&'                            # 0
```

Browser check (keyboard only): Tab through presets → range inputs → Apply →
Clear; confirm the global focus ring, that the active pill is visually distinct
without colour alone (it also carries `aria-current`), and that at ≤900px the bar
stacks instead of overflowing.

### 6.3 Style / spec gates

```bash
grep -nE "f\"|f'|%s|\+ *str\(" database/queries.py        # empty: no built SQL
grep -n "date >= ?" database/queries.py                   # present
grep -n "profile.css" -r static templates app.py           # empty (F1)
grep -nE "#[0-9a-fA-F]{3,6}" templates/profile.html        # empty
grep -c 'style="' templates/profile.html                   # 1 (bar width only)
grep -n "filter-" templates/profile.html static/css/style.css  # expected classes only
grep -n "sqlite3\|flask" database/queries.py               # empty: helpers stay pure
```

### 6.4 Scope guard

```bash
git diff --stat
# app.py, database/queries.py, templates/profile.html, static/css/style.css, AGENTS.md
# + new tests/test_date_filter.py
git diff -- database/db.py tests/conftest.py tests/test_backend_connection.py \
             templates/base.html static/js/main.js        # all empty
curl -s http://localhost:5001/expenses/add | head -1          # Step 7 stub intact
```

### 6.5 Cleanup

```bash
rm -f /tmp/spendly6.jar
```

---

## 7. DoD mapping

| Spec DoD item | Proven by |
|---|---|
| No params → identical to Step 5, All Time active | §5.3 summary test, §5.4 `test_profile_no_params_is_unfiltered`, §6.2 |
| "This Month" filters all three sections | §5.4 parametrised preset test, §6.2 (₹0.00 on live data) |
| "Last 3 Months" / "Last 6 Months" windows end today | §5.4 parametrised preset test + §5.2 `_month_start` rollover cases |
| "All Time" clears the filter, clean URL | §5.4 no-params test (`href="/profile"`, no empty params) |
| Custom valid range filters everything | §5.4 custom-range test, §6.2 (₹101.65 / 4 rows) |
| Inverted range flashes + falls back | §5.4 inverted-range test, §6.2 |
| Malformed date does not crash | §5.4 malformed test (param-independent, upper bound survives) |
| One-sided range works | §5.3 + §5.4 one-sided tests |
| Active preset / prefilled inputs visible | §5.4 active-count and prefill assertions, §6.2 grep |
| ₹ everywhere | template untouched on money fields; §5.4 totals regex uses `₹` |
| No expenses in range → ₹0.00, 0, empty breakdown, no errors | §5.3 + §5.4 empty-range test, §6.2 "This Month" |
| Keyboard/mobile usable | §6.2 browser pass; labels + `aria-current` in §4.4 |
| Existing suite green | §6.1 |

---

## 8. Execution order

1. `database/queries.py` — `_date_filter()` + three signatures (§4.3).
2. `tests/test_date_filter.py` — fixtures + query-layer tests; run
   `uv run pytest tests/test_date_filter.py -q -k "not profile_"` to validate the
   data layer before touching the view.
3. `app.py` — `date` import, `_parse_iso_date`, `_month_start`, `_build_presets`,
   rewrite `profile()` (§4.1, §4.2).
4. `templates/profile.html` — filter bar, subtitle, empty states (§4.4).
5. `static/css/style.css` — filter + empty-note rules, responsive additions (§4.5).
6. Route + helper tests; full `uv run pytest -q`.
7. Manual passes §6.2 (presets, custom, inverted, malformed) and browser check.
8. `AGENTS.md` — §4.6.
9. Commit on `feature/date-filter-profile` (spec + plan + code).

---

## 9. Out of scope

- `GET /expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete` — Steps 7–9
  must keep returning their placeholder text.
- Persisting the filter in the session, cookie, or URL hash; sharing/bookmarking
  beyond the plain query string.
- Per-category, amount, or text filters; pagination; sortable columns.
- JS auto-submit on input change (`static/js/main.js` stays empty).
- Changing `SEED_EXPENSES` or `_current_month_dates()` to spread demo data across
  months (DB scope; tests supply their own rows instead).
- Restyling `.flash--error` (F15) or the `--cat-*` oddities (`bills` →
  `--cat-entertainment`), and the remaining 04.1 token pass (landing hero,
  features, auth layout, 1120px container).
- `dateutil`/`freezegun` or any new dependency; timezone handling beyond the
  server's local `date.today()`.
- A `@login_required` decorator refactor.

---

## 10. Risks / watch-outs

| Risk | Mitigation |
|---|---|
| `get_recent_transactions(uid, date_from, date_to)` binds `date_from` to `limit` | Always call the three helpers with **keyword** args in `profile()` (§4.2). |
| SQL fragment appended after `GROUP BY`/`LIMIT` | Clause is concatenated immediately after `WHERE user_id = ?`, before `GROUP BY` / `ORDER BY` / `LIMIT` (§4.3, F5); `test_transactions_limit_with_filter` guards the limit. |
| Top category disagrees with the filtered total | Clause applied to both statements (§4.3, F4); `test_summary_date_range` asserts the recomputed category. |
| Unpadded dates break SQLite comparison | `_parse_iso_date` canonicalises; `test_parse_iso_date` pins `"2026-1-5"` (§4.1, F3). |
| All Time link gets `?date_from=&date_to=` | Presets carry `None`, never `""`; `url_for` drops `None` (§4.1, F2, F16 test). |
| Test dates collide with the seed month | Tests use a dedicated `dated_user` with month-boundary rows, no demo user (§5.1, F10). |
| New test file seeds the real DB by importing `app` at module scope | Import `app` inside the helper tests only, with `temp_db` requested (§5.2, F11). |
| Empty-state markup breaks Step 5 assertions | Uses `{% else %}` inside existing loops; asserts on `bar-fill` / `tx-date` are unaffected (§5.1, F13). |
| Flash never shown in tests | Flash renders in the same response (no redirect), asserted on the direct `client.get` body (§4.2, F9). |
| Tests compare full hrefs and fail on `&amp;` | Assert substrings or `html.unescape` first (§5.4, F12). |
| `date.today()` drift between test fixture and app | Both call `date.today()` within the same run; expectations are derived, not hardcoded (§5.1). If a test happens to run across midnight, only the `today` row boundary shifts — expectations still derive from the fixture rows, so totals remain correct for the app's own `today` only if both agree; acceptable (no clock freeze needed). |
| Mobile overflow from two date inputs + two buttons | `flex-wrap` + the ≤900/600px rules in §4.5; manual check at 375px. |
| Duplicate dev server on 5001 | Check the port before starting; reuse a running instance. |
| Scope creep into Step 7–9 stubs or the design pass | §6.4 `git diff` allow-list + stub curl check. |
