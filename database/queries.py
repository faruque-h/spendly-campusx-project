"""Read-only query helpers for Spendly. No Flask imports.

Every function opens its own connection via get_db() and closes it before
returning, so callers never manage connections. Optional date_from/date_to
(ISO YYYY-MM-DD, inclusive) narrow every helper to that range.
"""

from datetime import datetime

from database.db import get_db


def _format_month(value):
    """'2026-03-18 10:22:31' -> 'March 2026'; degrade to '2026-03'."""
    try:
        return datetime.fromisoformat(value).strftime("%B %Y")
    except (TypeError, ValueError):
        return (value or "")[:7]


def _date_filter(date_from=None, date_to=None):
    """Inclusive `date` bounds as a ``" AND ..."`` fragment plus params.

    Returns ``("", ())`` when neither bound is set. The fragment only composes
    onto a query that already has a WHERE clause.
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


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": _format_month(row["created_at"]),
    }


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

    return {
        "total_spent": round(row["total"], 2),
        "transaction_count": row["count"],
        "top_category": top["category"] if top else "—",
    }


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

    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


def get_category_breakdown(user_id, date_from=None, date_to=None):
    clause, date_params = _date_filter(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ?" + clause + " GROUP BY category "
            "ORDER BY total DESC, category ASC",
            (user_id, *date_params),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    total = sum(row["total"] for row in rows)
    if total <= 0:
        return []

    breakdown = [
        {
            "name": row["category"],
            "amount": round(row["total"], 2),
            "pct": round(row["total"] / total * 100),
        }
        for row in rows
    ]
    # Integer rounding rarely lands on 100: give the remainder to the largest.
    breakdown[0]["pct"] += 100 - sum(item["pct"] for item in breakdown)
    return breakdown
