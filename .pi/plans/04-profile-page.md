# Implementation Plan — Step 4: Profile Page

**Spec:** `.pi/specs/04-profile-page.md`
**Branch:** `feature/profile-page-design` (create from current `main`)
**Files to change:** `app.py`, `templates/base.html`, `static/css/style.css`,
`AGENTS.md` (route table, after the code lands)
**Files to create:** `templates/profile.html`
**Status:** plan only — no application code changed (planning mode)
**Locked decisions:** identity from `current_user`, expense data hardcoded to
match `SEED_EXPENSES`; `member_since` stays a hardcoded string; existing
`stat-card` / `bar-track` / `bar-fill` classes are reused; 7 new `--cat-*` tokens;
no Lucide/CDN icons; one inline `style="width: …%"` is allowed for bar widths.

---

## 1. Objective

Replace the `GET /profile` plain-text stub with a real, login-protected page:

1. Anonymous request → `302 /login`; signed-in request → `200` with
   `templates/profile.html`.
2. Four sections: user card (initials, name, e-mail, member-since), three summary
   stats, recent-transactions table, category breakdown bars.
3. Transaction/category numbers mirror the Step 1 seed data so Step 5 can swap in
   SQL without the page changing.
4. Navbar user name links to `/profile`, and signed-in users can still reach
   `/profile` + `/logout` on a phone.

No schema change, no new dependencies, no JS, no expense queries.

---

## 2. Current state (verified)

| Item | Verified state |
|---|---|
| `app.py` | `session`, `redirect`, `url_for`, `render_template` already imported. `inject_current_user` context processor exists and exposes `id`/`name`/`email` (explicit dict, never `password_hash`). `/profile` is still `return "Profile page — coming in Step 4"` under the "Placeholder routes" comment. |
| `/logout` | Implemented in Step 3 (`session.clear()` → flash → redirect). The AGENTS.md table claiming it is a stub was stale — now corrected. |
| DB | `spendly.db` (gitignored) has the seeded demo user plus one registered user. `users.created_at` exists (`YYYY-MM-DD HH:MM:SS`); `expenses` rows come from `SEED_EXPENSES` in `database/db.py`. |
| Seed totals | **₹180.19 across 8 transactions.** Food 21.75, Transport 3.75, Bills 60.00, Health 25.40, Entertainment 15.99, Shopping 45.30, Other 8.00. Top category: **Bills**. |
| `CATEGORIES` | `("Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other")` — exactly 7, so the breakdown can cover all of them. |
| `base.html` | Navbar signed-in branch renders `<span class="nav-user">Hi, {name}</span>` + Sign out. Flash block already exists. `title` block exists. |
| CSS | Reusable: `.stat-card`, `.stat-label`, `.stat-value` (tabular numerals), `.bar-track`, `.bar-fill`, `--paper-card`, `--border`, `--border-soft`, `--paper-warm`, `--radius-md`, `--font-display`. **No** table, badge, avatar, or profile rules exist. Landing-only hex values (e.g. `#e8e6e0`, `.bar-food`) are pre-existing and stay untouched. |
| Responsive | At `≤600px`, `.nav-links a:not(.nav-cta) { display: none; }` hides **every** signed-in link — a Step 3 regression that would make `/profile` unreachable on mobile. |
| Icons | No icon library anywhere; the site uses glyphs (`◈`, `₹`, `◎`, `◷`). The `spendly-ui-designer` skill suggests Lucide, but adding a CDN script would break "no new dependencies" and the established look. **Skipped.** |
| Tests / runtime | No test suite (`uv run pytest` exits 5). Dev server may already be running on 5001 — check before starting a second one. |

---

## 3. Design plan (spendly-ui-designer guidance applied)

- **One column, card-based, left-aligned** (auth pages are the only centred
  layouts). Container narrows to ~1000px so the page does not sprawl at 1440px.
- **User card first** as the identity anchor: 56px circular avatar with initials
  on `--accent-light`, name / e-mail / "Member since …" stacked.
- **Three stat cards** reuse the existing `.stat-card`; numbers use tabular
  figures. `₹` prefix, two decimals.
- **Two-column lower row** (`1.6fr 1fr`): recent transactions on the left,
  category breakdown on the right. Stacks to one column at `≤900px`.
- **Table**: uppercase muted column headers, hairline row separators, row hover,
  right-aligned tabular amounts, horizontal scroll inside `.table-wrap` (never
  page overflow).
- **Breakdown**: label + `.bar-track`/`.bar-fill` + amount; each bar coloured by a
  `--cat-*` token. Badges stay **neutral** pills (`--paper-warm`), so the only
  saturated colour on the page is the meaningful data.
- **Restraint**: no gradients, no shadows (borders only), spacing on the existing
  `rem` rhythm (section `3.5rem 2rem 4rem`, cards `1.75rem`, gaps `1rem`/`1.5rem`).
- All new CSS is prefixed `.profile-*`, `.tx-*`, `.badge`, `.breakdown-*` so it
  cannot leak into the landing page.

---

## 4. Findings and resolutions

### F1 — Hardcoded data → **mirror `SEED_EXPENSES` exactly**

Use the same 8 rows (description, category, amount) with display dates in the
current month. This keeps the page credible, makes the DoD arithmetic checkable,
and means Step 5's real query produces the same picture. Data lives in two
module-level constants next to the routes, clearly commented as Step 4
placeholders, so the view stays readable.

### F2 — Summary must not drift → **derive it from the literals**

`total_spent = round(sum(...), 2)`, `transaction_count = len(...)`, and
`top_category = max(totals, key=amount)[0]` are one line each. Deriving removes
the chance that the stats row disagrees with the table (the spec's consistency
rule) without any DB access.

### F3 — Identity → **`current_user`, not hardcoded**

Step 3 already injects the signed-in user. The card's name/e-mail come from
`current_user`, so the page can never contradict the navbar. Avatar initials are
derived in the template with one `{% set %}` on `current_user.name.split()`; the
avatar is `aria-hidden="true"` because the name sits right next to it.

### F4 — `member_since` → **hardcoded this step**

`current_user` exposes only `id`/`name`/`email`. Deriving "March 2024" from
`users.created_at` would mean adding a column to the context processor plus a
date-formatting helper — out of scope for a static-UI step. Keep
`member_since="March 2024"` in the view and note in the commit message that
Step 5/6 can switch to `created_at` once `current_user` carries it.

### F5 — Bar widths → **`style="width: {{ percent }}%"` is the one exception**

"No inline styles" would otherwise force 20 width utility classes or a
cross-browser `<progress>` restyle. The attribute carries *data* (a computed
percentage) and no colours; every other rule remains in `style.css`. The spec has
been updated to allow exactly this.

### F6 — Category colours → **7 `--cat-*` tokens in `:root`**

The existing three families cannot distinguish seven categories. Add one token per
category, reusing the landing bar hues for Food/Transport/Bills so the product
stays coherent: `--cat-food`, `--cat-transport`, `--cat-bills`, `--cat-health`,
`--cat-entertainment`, `--cat-shopping`, `--cat-other`. `:root` remains the only
place a hex literal is allowed (matches AGENTS.md). Badges stay neutral — no
second token per category for tints.

### F7 — Mobile navbar regression → **extend one `:not()` chain**

Signed-in users currently lose both navbar links at `≤600px`. Replace

```css
.nav-links a:not(.nav-cta) { display: none; }
```

with

```css
.nav-links a:not(.nav-cta):not(.nav-signout):not(.nav-user) { display: none; }
```

Guest behaviour is unchanged (only the CTA survives); signed-in users keep the
profile link and Sign out. No markup change, no new class.

### F8 — Styling goes in `style.css`, not a `<style>` block

The spec requires it and AGENTS.md names `style.css` the single stylesheet
(`landing.html` is the documented exception). `profile.html` gets no `<style>`
and no `style=` colours.

### F9 — Route placement

Promote `/profile` out of the "Placeholder routes" block so the file reads
`landing → register → login → terms → privacy → logout → profile`, then the
remaining `/expenses/...` placeholders. Endpoint name stays `profile` so
`url_for('profile')` works from `base.html`.

### F10 — No icons, no JS

The skill's Lucide guidance is overridden: no icon library is loaded today, and
the page needs no interaction. No `{% block scripts %}` content, no `main.js`
change.

### F11 — AGENTS.md is stale

Fixed in this planning pass: `/logout` row (now implemented), the "nothing loads
environment variables" claim (false since Step 2), and a line documenting the
`current_user` context processor. After implementation, flip the `/profile` row
to "Implemented — Step 4".

---

## 5. Proposed implementation

### 5.1 `app.py` — placeholder data (module level, above the routes)

```python
# Step 4 placeholder data — mirrors SEED_EXPENSES in database/db.py so the
# page matches the demo account. Replaced by per-user queries in Step 5.
PROFILE_TRANSACTIONS = [
    {"date": "21 Oct 2026", "description": "Electricity bill",      "category": "Bills",         "amount": 60.00},
    {"date": "20 Oct 2026", "description": "New backpack",          "category": "Shopping",      "amount": 45.30},
    {"date": "18 Oct 2026", "description": "Pharmacy purchase",     "category": "Health",        "amount": 25.40},
    {"date": "16 Oct 2026", "description": "Lunch at the campus cafe", "category": "Food",       "amount": 12.50},
    {"date": "14 Oct 2026", "description": "Streaming subscription", "category": "Entertainment", "amount": 15.99},
    {"date": "11 Oct 2026", "description": "Misc. stationery",      "category": "Other",         "amount": 8.00},
    {"date": "07 Oct 2026", "description": "Coffee and snacks",     "category": "Food",          "amount": 9.25},
    {"date": "03 Oct 2026", "description": "Bus fare",              "category": "Transport",     "amount": 3.75},
]

PROFILE_CATEGORY_TOTALS = [
    ("Bills", 60.00),
    ("Shopping", 45.30),
    ("Health", 25.40),
    ("Food", 21.75),
    ("Entertainment", 15.99),
    ("Other", 8.00),
    ("Transport", 3.75),
]
```

Both lists already sorted descending; names come from `CATEGORIES`.

### 5.2 `app.py` — the view

```python
@app.route("/profile")
def profile():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    total_spent = round(sum(t["amount"] for t in PROFILE_TRANSACTIONS), 2)
    summary = {
        "total_spent": total_spent,
        "transaction_count": len(PROFILE_TRANSACTIONS),
        "top_category": max(PROFILE_CATEGORY_TOTALS, key=lambda item: item[1])[0],
    }
    categories = [
        {
            "name": name,
            "total": amount,
            "percent": round(amount / total_spent * 100, 1),
        }
        for name, amount in PROFILE_CATEGORY_TOTALS
    ]

    return render_template(
        "profile.html",
        summary=summary,                    # ₹180.19 / 8 / Bills
        transactions=PROFILE_TRANSACTIONS,
        categories=categories,
        member_since="March 2024",
    )
```

No new imports (`session`, `redirect`, `url_for`, `render_template` are present);
no DB call; no `POST`.

### 5.3 `templates/base.html` — link the user name

```html
{% if current_user %}
<a href="{{ url_for('profile') }}" class="nav-user">Hi, {{ current_user.name }}</a>
<a href="{{ url_for('logout') }}" class="nav-signout">Sign out</a>
{% else %}
...
```

`<span>` → `<a class="nav-user">`: `.nav-links a` already supplies the muted
colour, `.nav-user` the weight/size, and `.nav-links a:hover` the hover state, so
**no new navbar CSS** is needed.

### 5.4 `templates/profile.html` (new)

```html
{% extends "base.html" %}

{% block title %}Your profile — Spendly{% endblock %}

{% block content %}
<section class="profile-section-block">
    <div class="profile-container">

        <header class="profile-header">
            <h1 class="profile-title">Your profile</h1>
            <p class="profile-subtitle">A snapshot of where your money went this month.</p>
        </header>

        <div class="profile-user-card">
            {% set name_parts = current_user.name.split() %}
            <div class="profile-avatar" aria-hidden="true">{{ name_parts[0][0] }}{{ name_parts[-1][0] if name_parts|length > 1 else '' }}</div>
            <div>
                <p class="profile-name">{{ current_user.name }}</p>
                <p class="profile-email">{{ current_user.email }}</p>
                <p class="profile-since">Member since {{ member_since }}</p>
            </div>
        </div>

        <div class="profile-stats">
            <div class="stat-card">
                <span class="stat-label">Total spent</span>
                <span class="stat-value">₹{{ "%.2f"|format(summary.total_spent) }}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Transactions</span>
                <span class="stat-value">{{ summary.transaction_count }}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Top category</span>
                <span class="stat-value">{{ summary.top_category }}</span>
            </div>
        </div>

        <div class="profile-columns">
            <section class="profile-card">
                <h2 class="profile-card-title">Recent transactions</h2>
                <div class="table-wrap">
                    <table class="tx-table">
                        <thead>
                            <tr>
                                <th scope="col">Date</th>
                                <th scope="col">Description</th>
                                <th scope="col">Category</th>
                                <th scope="col" class="tx-amount">Amount</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for t in transactions %}
                            <tr>
                                <td class="tx-date">{{ t.date }}</td>
                                <td>{{ t.description }}</td>
                                <td><span class="badge">{{ t.category }}</span></td>
                                <td class="tx-amount">₹{{ "%.2f"|format(t.amount) }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </section>

            <section class="profile-card">
                <h2 class="profile-card-title">Category breakdown</h2>
                <div class="breakdown">
                    {% for c in categories %}
                    <div class="breakdown-row">
                        <span class="breakdown-label">{{ c.name }}</span>
                        <span class="bar-track"><span class="bar-fill bar-fill--{{ c.name|lower }}" style="width: {{ c.percent }}%"></span></span>
                        <span class="breakdown-amount">₹{{ "%.2f"|format(c.total) }}</span>
                    </div>
                    {% endfor %}
                </div>
            </section>
        </div>

    </div>
</section>
{% endblock %}
```

No `<style>`, no scripts, no hex values. The single `style=` attribute is the
data-driven bar width (F5).

### 5.5 `static/css/style.css`

**A. Add seven tokens at the end of `:root`:**

```css
    --cat-food: #e8a33c;
    --cat-transport: #3f8ee8;
    --cat-bills: #8a7cf0;
    --cat-health: #d95d7a;
    --cat-entertainment: #c17f24;
    --cat-shopping: #1a472a;
    --cat-other: #6b6b6b;
```

**B. New "Profile page" block before the "Responsive" section** (variables only
outside `:root`):

```css
/* Profile page                                                        */
/* ------------------------------------------------------------------ */

.profile-section-block { padding: 3.5rem 2rem 4rem; }

.profile-container { max-width: 1000px; margin: 0 auto; }

.profile-header { margin-bottom: 2rem; }

.profile-title {
    font-family: var(--font-display);
    font-size: 2rem;
    color: var(--ink);
    margin-bottom: 0.25rem;
}

.profile-subtitle { font-size: 0.9rem; color: var(--ink-muted); }

.profile-user-card {
    display: flex;
    align-items: center;
    gap: 1.25rem;
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 1.75rem 2rem;
    margin-bottom: 1.5rem;
}

.profile-avatar {
    width: 56px;
    height: 56px;
    flex-shrink: 0;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: var(--accent-light);
    color: var(--accent);
    font-weight: 600;
    font-size: 1.1rem;
}

.profile-name { font-size: 1.15rem; font-weight: 600; color: var(--ink); }
.profile-email { font-size: 0.9rem; color: var(--ink-muted); }
.profile-since { font-size: 0.8rem; color: var(--ink-faint); margin-top: 0.25rem; }

.profile-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
}

.profile-columns {
    display: grid;
    grid-template-columns: 1.6fr 1fr;
    gap: 1.5rem;
    align-items: start;
}

.profile-card {
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 1.75rem;
}

.profile-card-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 1.25rem;
}

.table-wrap { overflow-x: auto; }

.tx-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }

.tx-table th {
    text-align: left;
    font-weight: 500;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--ink-faint);
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
}

.tx-table td {
    padding: 0.85rem 0.5rem 0.85rem 0;
    border-bottom: 1px solid var(--border-soft);
    color: var(--ink-soft);
}

.tx-table tbody tr:hover { background: var(--paper-warm); }
.tx-table tbody tr:last-child td { border-bottom: none; }
.tx-date { white-space: nowrap; color: var(--ink-muted); }

.tx-table th.tx-amount,
.tx-table td.tx-amount {
    text-align: right;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.badge {
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    background: var(--paper-warm);
    color: var(--ink-soft);
    font-size: 0.75rem;
    font-weight: 500;
    white-space: nowrap;
}

.breakdown { display: flex; flex-direction: column; gap: 1rem; }

.breakdown-row {
    display: grid;
    grid-template-columns: 6.5rem 1fr auto;
    align-items: center;
    gap: 0.85rem;
}

.breakdown-label { font-size: 0.85rem; color: var(--ink-soft); }

.breakdown-amount {
    font-size: 0.85rem;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.bar-fill--food { background: var(--cat-food); }
.bar-fill--transport { background: var(--cat-transport); }
.bar-fill--bills { background: var(--cat-bills); }
.bar-fill--health { background: var(--cat-health); }
.bar-fill--entertainment { background: var(--cat-entertainment); }
.bar-fill--shopping { background: var(--cat-shopping); }
.bar-fill--other { background: var(--cat-other); }
```

**C. Inside the existing `@media (max-width: 900px)` block:**

```css
    .profile-stats { grid-template-columns: 1fr; }
    .profile-columns { grid-template-columns: 1fr; }
```

**D. Inside the existing `@media (max-width: 600px)` block** — replace the
`.nav-links` hide rule (F7) and add page spacing:

```css
    .nav-links a:not(.nav-cta):not(.nav-signout):not(.nav-user) { display: none; }

    .profile-section-block { padding: 2.5rem 1.25rem 3rem; }
    .profile-user-card { padding: 1.25rem; }
    .profile-card { padding: 1.25rem; }
    .breakdown-row { grid-template-columns: 5rem 1fr auto; gap: 0.5rem; }
```

Reuse notes: `.stat-card` / `.stat-label` / `.stat-value` are reused as-is from
the landing block (they are generic and token-based; their hardcoded
`#e8e6e0` border is pre-existing and untouched). `.bar-track` is reused as the
14px rail; only the fill colours are new classes.

---

## 6. Verification plan

No test suite. Start the server once (`uv run python app.py`, port 5001); check
first that nothing is already listening.

### 6.1 Guard and happy path

```bash
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://localhost:5001/profile
# → 302 http://localhost:5001/login

rm -f /tmp/spendly4.jar
curl -s -o /dev/null -c /tmp/spendly4.jar -X POST http://localhost:5001/login \
  -d 'email=demo@spendly.com&password=demo123'          # 302, cookie set
curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/spendly4.jar http://localhost:5001/profile   # 200
```

### 6.2 Content assertions

```bash
PAGE=$(curl -s -b /tmp/spendly4.jar http://localhost:5001/profile)
echo "$PAGE" | grep -c 'Demo User\|demo@spendly.com\|Member since March 2024'   # 3
echo "$PAGE" | grep -o 'Profile page — coming' | wc -l                          # 0
for s in '180.19' '>8<' 'Bills' 'Recent transactions' 'Category breakdown'; do
  echo "$PAGE" | grep -q "$s" && echo "ok: $s"; done
echo "$PAGE" | grep -o '<tr>' | wc -l            # 9 (1 head row + 8 data rows)
echo "$PAGE" | grep -o 'badge' | wc -l           # 8
echo "$PAGE" | grep -o 'bar-fill bar-fill--' | wc -l   # 7
```

Stats cross-check: `₹180.19` = sum of the 8 rows; `Bills` = max category. Both
are derived in the view (F2), so the only way to break it is editing one literal.

### 6.3 Navbar link

```bash
echo "$PAGE" | grep -o 'href="/profile" class="nav-user"\|>Hi, Demo User</a>'
curl -s http://localhost:5001/ | grep -c 'href="/profile"'      # 0 when signed out
```

### 6.4 Spec rules (grep gates)

```bash
grep -nE '#[0-9a-fA-F]{3,6}' templates/profile.html       # empty
grep -c '<style' templates/profile.html                    # 0
grep -n 'style=' templates/profile.html                    # only the bar width line(s)
grep -nE 'get_db|sqlite3|SELECT' app.py | sed -n '1,20p'   # no new query in /profile
```

### 6.5 Scope guard

```bash
git diff --stat
# app.py, templates/base.html, static/css/style.css, AGENTS.md + new profile.html
git diff -- database/db.py                                 # empty
curl -s http://localhost:5001/expenses/add | head -1        # "Add expense — coming in Step 7"
curl -s -b /tmp/spendly4.jar http://localhost:5001/expenses/1/edit | head -1
git diff -- templates/landing.html templates/login.html templates/register.html \
            templates/terms.html templates/privacy.html    # empty
```

### 6.6 Browser / UI pass (ui-verify)

- 1280 px: two-column lower row, stats row of three, no overflow; table row
  hover works; amounts right-aligned and aligned on the decimal.
- 900 px: lower row and stats stack; bars stay readable.
- 375 px: **no horizontal page scroll**; the table scrolls inside
  `.table-wrap`; navbar shows "Hi, …" (links to `/profile`) and "Sign out";
  guest navbar unchanged (Sign in hidden, Get started visible).
- Keyboard: Tab reaches the profile link and Sign out; table headers are
  announced via `scope="col"`.
- Console: no errors; no extra network requests (no icon CDN).
- Fresh account (e.g. register a temp user) → card shows that user's name/e-mail,
  proving identity comes from `current_user`, not the literals.

### 6.7 Cleanup

```bash
kill %1; rm -f /tmp/spendly4.jar
```

---

## 7. DoD mapping

| DoD item | How it is proven |
|---|---|
| Anonymous `/profile` → `/login` | §6.1 |
| Signed-in `/profile` → 200 | §6.1 |
| User card name + e-mail + member-since, matching navbar | §6.2, §6.6 (fresh account) |
| ≥3 summary stats | §6.2 |
| ≥3 hardcoded transactions | §6.2 (8 rows) |
| ≥3 categories, all from `CATEGORIES` | §6.2 (7 bars) |
| Navbar signed-in state + name links to `/profile` | §6.3, §6.6 |
| No hex / no `<style>` / only bar-width `style=` | §6.4 |
| No overflow at 375 px; navbar links visible | §6.6 |
| `git diff` limited; `db.py`, stubs, auth untouched | §6.5 |

---

## 8. Execution order

1. `app.py` — add `PROFILE_TRANSACTIONS` / `PROFILE_CATEGORY_TOTALS` constants.
2. `app.py` — replace the `/profile` stub with the real view; move it out of the
   placeholder block.
3. `templates/profile.html` — new template (§5.4).
4. `templates/base.html` — `<span>` → `<a href="{{ url_for('profile') }}">`.
5. `static/css/style.css` — tokens, profile block, two media-query additions
   (including the navbar `:not()` fix).
6. Run §6.1–§6.5.
7. `AGENTS.md` — flip the `/profile` row to "Implemented — Step 4".
8. Browser pass §6.6, clean up §6.7.
9. Commit on `feature/profile-page-design` with the spec + this plan; note the
   deferred `created_at` member-since and the Step 5 data swap.

---

## 9. Out of scope

- Real `expenses` queries, per-user filtering, and the `/expenses/...` stubs —
  Steps 5 and 7–9.
- Editing/deleting transactions from the profile page (no buttons, no JS).
- Exposing `created_at` through `current_user` (F4, deferred).
- Lucide or any icon/CDN dependency (F10).
- Pagination, filters, charts, empty states — the hardcoded data is never empty.
- Auth/session changes, CSRF, `@login_required` refactors.

---

## 10. Risks / watch-outs

| Risk | Mitigation |
|---|---|
| Stats disagree with the table | Derived from the same literals in the view (F2). |
| Page contradicts navbar identity | Card reads `current_user`, never literals (F3). |
| Inline-style rule argued either way | Spec updated to allow the computed bar width only (F5); grep gate in §6.4. |
| New CSS leaks into landing | All rules prefixed `.profile-*` / `.tx-*` / `.breakdown-*`; only additive. |
| Mobile navbar regression ships | `:not()` fix in §5.5-D plus a 375 px check (§6.6). |
| Two dev servers on 5001 | Check the port before `python app.py`; reuse a running server. |
| Amount formatting depends on locale | Python `format` is locale-independent here; fixed `₹` prefix, dot decimal. |
| Stub drift while editing `app.py` | §6.5 asserts the three expense stubs still return their placeholder text. |
