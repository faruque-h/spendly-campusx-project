---
description: Create a single dummy user in the SQLite database
---

Read `database/db.py` to understand the `users` schema and the `get_db()` helper.

Then run a single Python script from the repo root using **uv** (do not use bare
`python3` — Werkzeug is only installed in the project environment):

```bash
uv run python - <<'PY'
...
PY
```

The script must:

1. Import `get_db` from `database.db` (which resolves `spendly.db` in the repo root).
2. Generate a realistic random Indian user using common first/last names across regions:
   - Name: first + last name
   - Email: derived from the name plus a random 2-3 digit suffix,
     lowercase, e.g. `rahul.sharma91@gmail.com`
   - Password: `password123`, hashed with
     `werkzeug.security.generate_password_hash`
   - `created_at`: current UTC datetime as `YYYY-MM-DD HH:MM:SS`
3. If the generated email already exists, regenerate it until it is unique
   (check with `SELECT 1 FROM users WHERE email = ?`).
4. Insert with parameterized SQL only, matching the `get_db()` pattern in
   `db.py`, and `conn.commit()` inside a `with conn:` block. Close the
   connection in a `finally`.
5. Not modify or delete the demo user (`demo@spendly.com`) or any existing rows.

Print a short confirmation on success:

```text
id:    <id>
name:  <name>
email: <email>
password: password123
```
