# AGENTS.md

Spendly is a Flask/Jinja expense tracker built as a step-by-step course scaffold. The real app is at the repo root, **not** in `src/`.

## Layout

- `app.py` — Flask app and all routes; the entrypoint.
- `templates/` — Jinja pages. Every page extends `base.html`, which owns the navbar, footer, and `head` / `content` / `scripts` blocks.
- `static/css/style.css` — the single shared stylesheet. Design tokens live in `:root`; reuse them instead of hardcoding colors/fonts.
- `static/js/main.js` — empty stub. The only JS currently is inline in `landing.html` (hero video modal).
- `database/db.py` — SQLite helpers: `get_db()` (connection with `sqlite3.Row` and foreign keys ON), `init_db()` (creates `users` and `expenses`), `seed_db()` (one-time demo data). Database file is `spendly.db` in the repo root.
- `src/expense_tracker_campusx_project/` — uv build package only; its `main()` prints a greeting. Do not put Flask app code here.

## Commands

```bash
uv sync                        # install dependencies
uv run python app.py           # dev server on port 5001 (not 5000)
uv run pytest                  # currently exits 5: no tests exist yet
uv run pytest path/to/test.py::test_name   # single test, once tests exist
```

If port 5001 is already in use, a dev server is likely already running — don't start a duplicate.

```bash
rm -f spendly.db               # delete local DB; demo data is reseeded on next startup
```

## Database

- `spendly.db` is created in the repo root on first import/startup. `app.py` calls `init_db()` then `seed_db()` inside an `app.app_context()` at module load, before any route runs.
- Tables: `users` (`id`, `name`, `email` UNIQUE, `password_hash`, `created_at`) and `expenses` (`id`, `user_id` FK → `users.id`, `amount` REAL, `category`, `date` as `YYYY-MM-DD`, `description` nullable, `created_at`).
- `seed_db()` inserts only when `users` is empty, so it is safe on every startup. Demo login: `demo@spendly.com` / `demo123`.
- Categories are a fixed list in `CATEGORIES` (`db.py`): Food, Transport, Bills, Health, Entertainment, Shopping, Other.
- Raw SQL with `?` placeholders only — no ORM. `get_db()` returns a new connection per call; callers must close it.
- See `.pi/specs/01-database-setup.md` for the schema contract.

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET /register` | Implemented — renders `register.html` |
| `GET /login` | Implemented — renders `login.html` |
| `GET /logout` | Stub — Step 3 |
| `GET /profile` | Stub — Step 4 |
| `GET /expenses/add` | Stub — Step 7 |
| `GET /expenses/<id>/edit` | Stub — Step 8 |
| `GET /expenses/<id>/delete` | Stub — Step 9 |

**Do not implement a stub route unless the active task explicitly targets that step.**

## Gotchas

- The placeholder routes in `app.py` (`/logout`, `/profile`, `/expenses/...`) intentionally return plain text; they are course steps to implement, not bugs.
- There is no test suite, lint, formatter, typecheck, or CI config. `pytest` and `pytest-flask` are installed, but don't claim tests pass until tests actually exist.
- Dependencies are managed with uv (`pyproject.toml` + `uv.lock`); `requirements.txt` duplicates the pinned deps. Update pyproject/uv.lock as the source of truth.
- Vanilla JS only — no frontend frameworks or page libraries. The landing modal sets its YouTube iframe to `about:blank` on close to stop playback; preserve that.
- The landing modal's CSS and JS live in `landing.html`'s `head`/`scripts` blocks. Shared styling stays in `style.css`.
- `.env` and SQLite `*.db` files are gitignored; nothing currently loads environment variables. `spendly.db` is generated, not source — schema and seed data live in `database/db.py`.
- `README.md` is empty — use this file and `app.py` as the source of truth.
