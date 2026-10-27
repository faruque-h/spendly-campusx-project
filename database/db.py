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

DEMO_USER = {
    "name": "Demo User",
    "email": "demo@spendly.com",
    "password": "demo123",
}

SEED_EXPENSES = [
    ("Food", 12.50, "Lunch at the campus cafe"),
    ("Transport", 3.75, "Bus fare"),
    ("Bills", 60.00, "Electricity bill"),
    ("Health", 25.40, "Pharmacy purchase"),
    ("Entertainment", 15.99, "Streaming subscription"),
    ("Shopping", 45.30, "New backpack"),
    ("Other", 8.00, "Misc. stationery"),
    ("Food", 9.25, "Coffee and snacks"),
]


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        with conn:
            conn.executescript(SCHEMA)
    finally:
        conn.close()


def _current_month_dates(count):
    today = date.today()
    if today.day == 1:
        days = [1] * count
    else:
        days = [1 + round(i * (today.day - 1) / (count - 1))
                for i in range(count)]
    return [date(today.year, today.month, day).isoformat() for day in days]


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
                (
                    DEMO_USER["name"],
                    DEMO_USER["email"],
                    generate_password_hash(DEMO_USER["password"]),
                ),
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
