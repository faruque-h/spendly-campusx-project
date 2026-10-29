# Spec: Profile Page

## Overview
This feature replaces the `/profile` stub with a fully designed profile page showing static, hardcoded expense data. The goal is to establish the complete UI layout — user info card, transaction history table, summary stats, and category breakdown — before any real expense queries are wired up in Step 5. Building the UI first lets the team validate the design in isolation and ensures the templates are ready for the backend-connection step.

## Depends on
- Step 1: Database setup (schema must exist)
- Step 2: Registration (user accounts must be creatable)
- Step 3: Login + Logout — `session["user_id"]` is set on login and the
  `current_user` context processor in `app.py` already exposes `id` / `name` /
  `email` to every template. The route guard for `/profile` is added in *this*
  step (Step 3 deliberately left route protection out of scope).

## Routes
- GET /profile — render the profile page — logged-in only
  - `user_id = session.get("user_id")`; if absent, `redirect(url_for("login"))` (302)
  - no `POST`, no query parameters, no DB writes

## Context passed to the template
| Variable | Shape | Source |
|---|---|---|
| `summary` | dict: `total_spent`, `transaction_count`, `top_category` | hardcoded in `app.py` |
| `transactions` | list of dicts: `date`, `description`, `category`, `amount` | hardcoded in `app.py` |
| `categories` | list of dicts: `name`, `total`, `percent` | hardcoded in `app.py` |
| `member_since` | display string, e.g. `"March 2024"` | hardcoded in `app.py` |
| `current_user` | dict: `id`, `name`, `email` | existing context processor |

Name, email, and avatar initials come from `current_user`, so the page never
shows a name that disagrees with the navbar. Everything expense-shaped is fake
until Step 5.

## Database changes
No database changes. The existing `users` and `expenses` tables are sufficient,
and this step reads from neither (beyond the existing `current_user` lookup).

## Templates
- Create: `templates/profile.html` — full profile page extending `base.html`;
  contains four sections:
  1. **User info card** — avatar initials (derived from `current_user.name`), name, email, member-since date
  2. **Summary stats row** — total spent, number of transactions, top category
  3. **Transaction history table** — list of recent expenses with date, description, category badge, amount
  4. **Category breakdown** — per-category totals as progress-bar rows (reuse the existing `.bar-track` / `.bar-fill` pattern or add profile equivalents)
- Modify: `templates/base.html` — link the signed-in user name to
  `url_for("profile")` (Step 3 explicitly deferred this link to this step). Keep
  the `.nav-user` style and the Sign out link as they are, and keep both visible
  in the ≤600 px navbar (they are currently hidden by the
  `.nav-links a:not(.nav-cta)` rule).
- Modify: `static/css/style.css` — add the profile page rules (container, card,
  stats, table, badges, progress rows) to the shared stylesheet, not to a
  `<style>` block. Add category colour tokens under `:root` if the existing
  `--accent` / `--accent-2` / `--danger` families are not enough.

## Files to change
- `app.py` — replace the `/profile` stub with a real view function that:
  - Redirects unauthenticated users to `/login`
  - Passes the hardcoded context variables above to `profile.html`
- `templates/base.html` — navbar link to `/profile`
- `static/css/style.css` — profile styles, plus any new `:root` tokens

## Files to create
- `templates/profile.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw sqlite3 via `get_db()` if any DB call is ever needed
- Parameterised queries only — never string-format SQL
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values; new `style.css` rules may only
  reference `:root` tokens. `:root` is the one place a hex literal is allowed.
- All templates extend `base.html`
- No `<style>` block and no inline colour/layout styles in `profile.html` — page
  CSS belongs in `style.css`. The one allowed `style=` attribute is the
  data-driven breakdown bar width (`style="width: {{ percent }}%"`).
- Authentication guard: check `session.get("user_id")`; if absent, `redirect(url_for("login"))`
- Expense, stat, and category data must be hardcoded Python dicts/lists in
  `app.py` — no expense queries in this step; identity comes from `current_user`.
  Deriving `summary` from those literals is fine and preferred.
- Hardcoded data must be internally consistent: `total_spent`,
  `transaction_count`, and `top_category` must match the rows in `transactions`
  and `categories`
- Category names must come from `CATEGORIES` in `database/db.py` (Food,
  Transport, Bills, Health, Entertainment, Shopping, Other)
- Category badges must use a CSS class, not inline colour styles
- Money is rendered as `₹` with two decimals (e.g. `₹12.50`), matching the
  "Track every rupee" copy
- Table markup: `<thead>` with `<th scope="col">`, wrapped in an overflow-x
  container so narrow screens scroll instead of breaking the layout
- Leave the `/expenses/...` stubs, `database/db.py`, and the auth routes untouched

## Definition of done
- [ ] Visiting `/profile` without being logged in redirects (302) to `/login`
- [ ] Visiting `/profile` while logged in returns HTTP 200
- [ ] The user card shows the signed-in account's name and email plus a
      member-since date, and they match the navbar
- [ ] The page displays at least three summary stat values (total spent, transaction count, top category)
- [ ] The page displays a transaction history table with at least three hardcoded rows
- [ ] The page displays a category breakdown section with at least three categories, all from `CATEGORIES`
- [ ] The navbar shows the logged-in state and the user name links to `/profile`
- [ ] No hex values appear in `profile.html`, which has no `<style>` block and no
      inline colours; the only `style=` attributes are the breakdown bar widths
- [ ] The page has no horizontal overflow at 375 px width (the table scrolls
      inside its container) and the signed-in navbar still shows the profile link
      and Sign out
- [ ] `git diff` shows no changes to `database/db.py`, the `/expenses/...` stubs,
      or the auth routes; only `app.py`, `templates/base.html`,
      `templates/profile.html` (new), and `static/css/style.css` are touched
      (plus docs: this spec, the plan, and `AGENTS.md`)
