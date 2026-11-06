# Spec: Date Filter for Profile Page

## Overview
Step 6 adds a date-range filter to the existing `/profile` route so users can
narrow the transaction list, summary stats, and category breakdown to a specific
period. The filter is driven entirely by query-string parameters (`date_from` and
`date_to`) on `GET /profile`, requiring no new routes. A compact filter bar with
four quick-select presets ("This Month", "Last 3 Months", "Last 6 Months",
"All Time") and two `<input type="date">` fields lets users pick any custom range.
All three data sections (summary stats, recent transactions, category breakdown)
respect the active date filter.

The filter is server-rendered and works with JavaScript disabled: presets are
plain `<a href>` links, the custom range is a `method="get"` form, and the active
state is computed in `app.py` per request.

## Depends on
- Step 1: Database setup (`expenses` table with a `date` column must exist)
- Step 4: Profile page UI (template with all four sections must exist)
- Step 5: Backend connection (`get_summary_stats`, `get_recent_transactions`,
  `get_category_breakdown` in `database/queries.py` must exist and be wired to
  the `/profile` route)

## Routes
No new routes. The existing `GET /profile` route (login-guarded, stale-session
handling unchanged) is modified to read optional query parameters:
- `date_from` — ISO date string `YYYY-MM-DD`, inclusive lower bound
- `date_to`   — ISO date string `YYYY-MM-DD`, inclusive upper bound

Behaviour:
- Params are stripped; empty/whitespace/missing values count as absent.
- Each param is validated independently with
  `datetime.strptime(value, "%Y-%m-%d")`. On `ValueError` that param alone is
  treated as absent.
- A valid param is **normalised** to `.date().isoformat()` before use (e.g.
  `2026-1-5` → `2026-01-05`). This is required because SQLite compares the TEXT
  `date` column lexicographically — only zero-padded ISO strings compare
  chronologically.
- If `date_from > date_to` after validation, **both** are dropped (unfiltered
  view) and an error is flashed:
  `flash("Start date must be before end date.", "error")`
  (`"error"` matches the `flash--error` style already used by login/registration.)
  Equal dates (`date_from == date_to`) are valid and mean a single day.
- One-sided ranges are supported: `?date_from=…` alone filters `date >= …`,
  `?date_to=…` alone filters `date <= …`. Only when both are absent does the
  route behave exactly like Step 5.
- Only the `date` column is filtered — never `created_at`. Future-dated expenses
  are therefore visible only under "All Time" or a custom `date_to` that reaches
  them.
- Preset date math is computed in `app.py` via a month-rollover-safe helper (no
  `dateutil`, no new dependencies), using `date.today()` (local server date, same
  basis as `seed_db()`). All presets end **today**, so future rows stay hidden:

  | Preset | `date_from` | `date_to` |
  |---|---|---|
  | This Month | first day of current month | today |
  | Last 3 Months | first day of the month 2 months back (calendar months incl. current) | today |
  | Last 6 Months | first day of the month 5 months back | today |
  | All Time | — (no params, clean `/profile` URL) | — |

  Month arithmetic must use integer maths (`year * 12 + month - 1 - n`, then
  `divmod`) so January/March rollovers stay correct; never subtract 30-day
  approximations.
- The view passes to the template: `user`, `summary`, `transactions`,
  `categories`, `date_from`, `date_to`, and a `presets` list of dicts
  (`{"key", "label", "date_from", "date_to", "active"}`). `active` is true when
  the normalised request range equals that preset's range; "All Time" is active
  when both params are absent (including after a validation fallback).

## Database changes
No database changes. The `expenses.date` column (`TEXT`, `YYYY-MM-DD`) already
supports `>=` / `<=` / `BETWEEN` comparison in SQLite.

## Templates
- **Modify**: `templates/profile.html`
  - Add a filter bar section between the user card and `.profile-stats`:
    - `.filter-bar` wrapper containing `.filter-presets` (four
      `.filter-preset` links, each `url_for("profile", date_from=…,
      date_to=…)`, or bare `url_for("profile")` for "All Time") and a
      `.filter-range` form (`method="get"`, `action=url_for("profile")`).
    - Preset links are anchors, not `<button>`s — they are navigations, not
      form submissions. The active one gets `.filter-preset--active` plus
      `aria-current="page"`; inactive ones must not emit `aria-current`.
    - The range form has two labelled inputs (`<label for="date_from">Start
      date</label>` + `id="date_from" name="date_from" type="date"`, same for
      `date_to`), an "Apply" submit, and a "Clear" link to bare
      `url_for("profile")`. Inputs are prefilled with the normalised active
      values so a custom range visually indicates what is applied.
    - Use `url_for` for every URL; never hardcode `"/profile?..."` strings.
  - Update the header subtitle from "A snapshot of where your money went this
    month." to period-neutral copy (e.g. "A snapshot of where your money
    went.") — the default view is All Time, so "this month" is now wrong.
  - Empty states (small muted note, class `.empty-note`): when `transactions` is
    empty render a `<tr><td colspan="4">No transactions in this range.</td></tr>`;
    when `categories` is empty render "No spending in this range." inside
    `.breakdown`. Existing unfiltered markup stays otherwise unchanged.
  - No other structural changes; only the Jinja variables fed to existing
    sections change.

## Files to change
- `app.py`
  - `profile()`: parse/normalise/order-check `date_from` and `date_to`, flash on
    inverted range, build the preset list, pass the filter values to all three
    query helpers and back to the template.
  - Add two small module-level helpers: `_parse_iso_date(value)` (returns
    normalised ISO string or `None`) and `_month_start(day, months_back=0)`.
    Keep preset definitions in one place so template and tests agree.
- `database/queries.py`
  - Add a private helper `_date_filter(date_from=None, date_to=None)` returning
    `("", ())` when no bounds, otherwise `(" AND date >= ? AND date <= ?", (…,))`
    (or the single-bound variant). Keeps parameterisation identical across all
    three helpers.
  - `get_summary_stats(user_id, date_from=None, date_to=None)` — apply the
    clause to **both** queries, including the top-category aggregate (easy to
    miss; otherwise "Top category" can contradict the filtered totals).
  - `get_recent_transactions(user_id, limit=10, date_from=None, date_to=None)` —
    same pattern; ordering (`date DESC, id DESC`) and `limit` unchanged, so a
    filtered view still shows at most 10 newest rows in range.
  - `get_category_breakdown(user_id, date_from=None, date_to=None)` — same
    pattern; percentage recalculation/rounding remainder logic unchanged.
  - New params are trailing and default `None`, so existing positional and
    keyword call sites (including `limit=3`) keep working.
- `templates/profile.html` — filter bar, neutral subtitle, empty states.
- `static/css/style.css` — add the filter bar styles in the existing
  `/* Profile page */` block using tokens only (`.filter-bar`,
  `.filter-presets`, `.filter-preset`, `.filter-preset--active`,
  `.filter-range`, `.empty-note`), plus responsive rules in the existing
  `@media (max-width: 900px)` / `(max-width: 600px)` blocks so the bar stacks
  cleanly on narrow screens.

  There is **no** `static/css/profile.css` — all shared styling lives in
  `style.css`; do not create a second stylesheet.

## Files to create
- `tests/test_date_filter.py` — see Tests below.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format or f-string dates into SQL;
  use `?` placeholders even for the date-range bounds
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables from `:root` — never hardcode hex values, radii, or spacing.
  Available tokens: `--ink`, `--ink-soft`, `--ink-muted`, `--ink-faint`,
  `--paper`, `--paper-sunk`, `--paper-card`, `--accent`, `--accent-strong`,
  `--accent-light`, `--border`, `--border-soft`, `--border-strong`,
  `--text-xs|sm|base|lg`, `--space-1…8`, `--radius-sm|md|lg|full`, `--dur-1|2`,
  `--ease`, `--font-display`/`--font-body`
- All templates extend `base.html`
- No new inline styles. (The existing `style="width: {{ c.pct }}%"` on
  `.bar-fill` is data-driven and stays as-is; do not copy that pattern for the
  filter bar.)
- Active preset styling must be a token-based surface/border change consistent
  with the rest of the page (borders + surface steps, no box-shadows)
- No JavaScript required; `static/js/main.js` stays untouched
- Currency stays ₹ everywhere, filtered or not
- Query helpers keep opening/closing their own connection and must not import
  Flask

## Tests to write
File: `tests/test_date_filter.py`. Use a dedicated fixture (e.g. `dated_user_id`)
that inserts a fresh user plus expenses with **explicit fixed dates relative to
`date.today()`** — do not rely on seed rows, because `seed_db()` only generates
current-month dates. Include rows at: today, first day of current month, ~40
days ago, ~100 days ago, ~200 days ago, and one future date (e.g. today + 15
days). Keep `tests/test_backend_connection.py` untouched; its 15 tests must
still pass.

### Query-helper tests
| Call | Expected |
|---|---|
| `get_summary_stats(uid)` | identical to Step 5 unfiltered result |
| `get_summary_stats(uid, date_from, date_to)` | only in-range totals/count, `top_category` computed from the filtered set |
| `get_summary_stats(uid, date_from=None, date_to=…)` | one-sided upper bound applied |
| `get_recent_transactions(uid, date_from=…, date_to=…)` | only in-range rows, newest-first, `limit` honoured |
| `get_category_breakdown(uid, date_from=…, date_to=…)` | only in-range categories, `pct` ints summing to 100 |
| any helper with a range containing no rows | `total_spent == 0`, `transaction_count == 0`, empty transactions and breakdown |

### Route tests
- `GET /profile?date_from=&date_to=` (blank values) → 200, unfiltered result,
  "All Time" marked active.
- `GET /profile?date_from=not-a-date` → 200 (no 500), unfiltered result.
- `GET /profile?date_from=<today>&date_to=<today - 1 day>` → 200, flash text
  "Start date must be before end date." in the body, unfiltered result,
  "All Time" active.
- `GET /profile?date_from=<day>&date_to=<same day>` → 200, single-day result.
- Custom valid range → only in-range rows in all three sections (assert on
  rendered amount/row count, not just status).
- Preset links render with resolvable `url_for` query strings; "All Time" href is
  exactly `url_for("profile")`.
- Active preset: exactly one `.filter-preset--active` and one
  `aria-current="page"` per request; range inputs are prefilled.
- Range with no matching rows → `₹0.00`, transaction count 0, no `bar-fill--`
  rows, empty-state notes present, status 200.
- Unauthenticated `GET /profile?date_from=…` still redirects to `/login` (302).

## Non-goals
No per-category filter, no saved/remembered filters, no pagination, no changes
to `get_recent_transactions` ordering or default limit, no new routes, no chart
library, no JS filtering.

## Definition of done
- [ ] Visiting `/profile` with no query params returns the same data as Step 5
  (unfiltered, all expenses) and marks "All Time" active
- [ ] Clicking "This Month" filters all three sections to the current calendar
  month (first day of month through today)
- [ ] Clicking "Last 3 Months" filters to the 3 calendar months ending today
- [ ] Clicking "Last 6 Months" filters to the 6 calendar months ending today
- [ ] Clicking "All Time" removes any active filter and shows all expenses with a
  clean `/profile` URL
- [ ] Submitting a valid custom range shows only expenses within that range in
  all three sections, including "Top category"
- [ ] Submitting a range where `date_from > date_to` flashes "Start date must be
  before end date." and falls back to the unfiltered view
- [ ] Submitting a malformed date (e.g. `date_from=not-a-date`) does not crash —
  that bound is ignored, no 500
- [ ] A one-sided range filters only that bound
- [ ] The active preset (or prefilled custom range) visually indicates which
  filter is applied, and only one preset is marked active
- [ ] All amounts still display ₹ regardless of the active filter
- [ ] A user with no expenses in the selected range sees ₹0.00 total spent, 0
  transactions, an empty breakdown, and the empty-state notes — no errors
- [ ] The filter bar is keyboard-usable (labelled inputs, visible focus ring from
  the global `:focus-visible` rule) and stacks on mobile widths
- [ ] `uv run pytest` passes: the existing 15 tests plus the new
  `tests/test_date_filter.py`
