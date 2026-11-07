# AGENTS.md

Spendly is a Flask/Jinja expense tracker built as a step-by-step course scaffold. The real app is at the repo root, **not** in `src/`.

## Layout

- `app.py` — Flask app and all routes; the entrypoint. A `@app.context_processor` injects `current_user` (`id`, `name`, `email`) into every template (Step 3), so templates can branch on the signed-in state.
- `templates/` — Jinja pages. Every page extends `base.html`, which owns the navbar, footer, and `head` / `content` / `scripts` blocks.
- `static/css/style.css` — the single shared stylesheet. Design tokens live in `:root`; reuse them instead of hardcoding colors/fonts.
- `static/js/main.js` — empty stub. The only JS currently is inline in `landing.html` (hero video modal).
- `database/db.py` — SQLite helpers: `get_db()` (connection with `sqlite3.Row` and foreign keys ON), `init_db()` (creates `users` and `expenses`), `seed_db()` (one-time demo data). Database file is `spendly.db` in the repo root.
- `database/queries.py` — query helpers used by views (`get_user_by_id`, `get_summary_stats`, `get_recent_transactions`, `get_category_breakdown`, `get_expense_by_id`, plus `insert_expense` / `update_expense`, the two write paths). The three read expense helpers take optional `date_from` / `date_to` ISO bounds (inclusive) via the shared `_date_filter()`. No Flask imports; each opens and closes its own connection. Add new SQL here, not inline in `app.py`.
- `tests/` — pytest suite. `conftest.py` points `database.db.DATABASE` at a `tmp_path` DB and imports `app` lazily, so tests never touch `spendly.db`.
- `src/expense_tracker_campusx_project/` — uv build package only; its `main()` prints a greeting. Do not put Flask app code here.

## Commands

```bash
uv sync                        # install dependencies
uv run python app.py           # dev server on port 5001 (not 5000)
uv run pytest                  # full suite (currently 139 tests, all passing)
uv run pytest path/to/test.py::test_name   # single test
```

If port 5001 is already in use, a dev server is likely already running — don't start a duplicate.

```bash
rm -f spendly.db               # delete local DB; demo data is reseeded on next startup
```

## Design system

- Design tokens live in `:root` in `static/css/style.css`; hex literals are allowed only there. Reuse `--space-*`, `--text-*`, `--radius-*`, `--cat-*`, and `--dur-*` when building new UI; do not introduce new colors, radii, or spacing values.
- Fonts: **Fraunces** is display-only (wordmark, page titles, money figures); **DM Sans** is all UI/body text. Both load in `base.html`.
- No box-shadows for hierarchy (borders + surface steps instead); one global `:focus-visible` ring in `--accent`.
- Pass 2 of `.pi/plans/04.1-design-tokens.md` is still pending: landing hero/mock + features, profile summary/table/breakdown, auth layout + custom inputs, 1120px container, and applying the text/spacing scales. Implement those while building Steps 5–7 rather than retrofitting later.

## Database

- `spendly.db` is created in the repo root on first import/startup. `app.py` calls `init_db()` then `seed_db()` inside an `app.app_context()` at module load, before any route runs.
- Tables: `users` (`id`, `name`, `email` UNIQUE, `password_hash`, `created_at`) and `expenses` (`id`, `user_id` FK → `users.id`, `amount` REAL, `category`, `date` as `YYYY-MM-DD`, `description` nullable, `created_at`).
- `seed_db()` inserts only when `users` is empty, so it is safe on every startup. Demo login: `demo@spendly.com` / `demo123`.
- Categories are a fixed list in `CATEGORIES` (`db.py`): Food, Transport, Bills, Health, Entertainment, Shopping, Other.
- Raw SQL with `?` placeholders only — no ORM. `get_db()` returns a new connection per call; callers must close it.
- Route-level queries live in `database/queries.py` (pure helpers, no Flask imports); views call them instead of writing SQL inline. Dates stay ISO (`YYYY-MM-DD`) in the helpers and are formatted in templates via the `display_date` filter.
- See `.pi/specs/01-database-setup.md` for the schema contract.

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET /register` | Implemented — renders `register.html` |
| `GET /login` | Implemented — renders `login.html` |
| `GET /logout` | Implemented — Step 3 (`session.clear()` + flash) |
| `GET /profile` | Implemented — Steps 5–6 (login-guarded; live per-user queries + `date_from`/`date_to` filter via `database/queries.py`) |
| `GET /expenses/add` | Implemented — Step 7 (`GET` form + `POST` validate/insert, redirects to `/profile`) |
| `GET` / `POST /expenses/<id>/edit` | Implemented — Step 8 (`GET` prefilled form + `POST` validate/update; 404 for missing/foreign id, redirects to `/profile`) |
| `GET /expenses/<id>/delete` | Stub — Step 9 |

**Do not implement a stub route unless the active task explicitly targets that step.**

## Gotchas

- The placeholder route in `app.py` (`/expenses/<id>/delete`) intentionally returns plain text; it is a course step to implement, not a bug.
- `/expenses/add` and `/expenses/<id>/edit` share `_parse_expense_form()` in `app.py`; both reject validation failures with status **400** and sticky fields, store amounts rounded to 2 dp, and normalise dates to zero-padded ISO. The edit route additionally returns 404 for a missing or foreign-owned id (ownership is enforced in SQL on both the `SELECT` and the `UPDATE`).
- Tests live in `tests/` (`uv run pytest`). There is no lint, formatter, typecheck, or CI config. Tests use a `tmp_path` database and must never write to `spendly.db`.
- Dependencies are managed with uv (`pyproject.toml` + `uv.lock`); `requirements.txt` duplicates the pinned deps. Update pyproject/uv.lock as the source of truth.
- Vanilla JS only — no frontend frameworks or page libraries. The landing modal sets its YouTube iframe to `about:blank` on close to stop playback; preserve that.
- The landing modal's CSS and JS live in `landing.html`'s `head`/`scripts` blocks. Shared styling stays in `style.css`.
- `/profile` filter: `date_from` / `date_to` are parsed and normalised in `app.py` (`_parse_iso_date`), one-sided ranges are allowed, an inverted range flashes and falls back to unfiltered, and presets (`PROFILE_PRESETS` / `_build_presets`) all end today. Query-string-only, no session state.
- Successful login redirects to `/profile` (not `/`), and `GET /login` while already signed in does the same. `/logout` still returns to `/`.
- `.env` and SQLite `*.db` files are gitignored. No dotenv loader exists; `app.py` reads only `SPENDLY_SECRET_KEY` (plus opt-in `SPENDLY_DEBUG` and `SPENDLY_SECURE_COOKIES`), falling back to dev-only values. `spendly.db` is generated, not source — schema and seed data live in `database/db.py`.
- `README.md` is empty — use this file and `app.py` as the source of truth.
