---
description: Seed realistic dummy expenses for a specific user
argument-hint: "<user_id> <count> <months>"
---

Read `database/db.py` to understand the `expenses` table schema, the `get_db()`
connection pattern, and that the database file is resolved from `db.py` (never
hardcode `spendly.db`).

Arguments: `$ARGUMENTS`

## Step 1 — Parse arguments

Extract from `$ARGUMENTS`:

- `user_id` — positive integer
- `count` — positive integer, number of expenses to create
- `months` — positive integer, how many past months to spread them across

If any argument is missing, not an integer, or not greater than 0, stop and say:

```text
Usage: /seed-expense <user_id> <count> <months>
Example: /seed-expense 1 50 6
```

## Step 2 — Verify the user exists

Before generating anything, run a parameterised
`SELECT 1 FROM users WHERE id = ?`. If no row is found, stop and say:

```text
No user found with id <user_id>.
```

## Step 3 — Generate and insert expenses

Run a single Python script from the repo root using **uv** (do not use bare
`python3` — Werkzeug and the project environment are only available via uv):

```bash
uv run python - <<'PY'
...
PY
```

The script must:

1. Import `get_db` from `database.db`.
2. Spread `count` expenses over the past `months` months, using dates in
   `YYYY-MM-DD` format (the column is `TEXT`). Never generate a future date.
3. Pick categories from exactly the fixed list in `db.py`
   (`Food, Transport, Bills, Health, Entertainment, Shopping, Other`), weighted
   roughly: Food 30%, Transport 20%, Bills 12%, Shopping 12%, Other 10%,
   Health 8%, Entertainment 8%.
4. Use these realistic INR amount ranges (stored as `REAL` numbers, no currency
   symbol in the column):
   - Food: 50–800
   - Transport: 20–500
   - Bills: 200–3000
   - Health: 100–2000
   - Entertainment: 100–1500
   - Shopping: 200–5000
   - Other: 50–1000
5. Write a short realistic Indian-context description per expense
   (e.g. "Auto to office", "Airtel recharge", "Groceries at DMart").
6. Insert with parameterised SQL only — no f-strings or `%` formatting in SQL —
   using the `get_db()` pattern from `db.py`:

```python
conn = get_db()
try:
    with conn:
        conn.executemany(
            "INSERT INTO expenses "
            "(user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
finally:
    conn.close()
```

   All inserts happen in one transaction; any failure rolls back everything.
7. Not modify or delete existing rows or other users' expenses.

## Step 4 — Confirm

Print:

- the number of expenses inserted
- the min and max `date` of the inserted rows
- a sample of 5 inserted records (`id`, `date`, `category`, `amount`, `description`)
