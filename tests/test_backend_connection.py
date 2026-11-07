"""Tests for the Step 5 backend connection (database/queries.py + /profile)."""

import re
from datetime import datetime

import pytest

from database.db import CATEGORIES
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

SEED_TOTAL = 180.19
SEED_COUNT = 8


# ------------------------------------------------------------------ #
# Query helpers                                                       #
# ------------------------------------------------------------------ #

def test_get_user_by_id(demo_user_id):
    user = get_user_by_id(demo_user_id)

    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    # created_at is datetime('now'), so assert the shape, not the month.
    assert re.fullmatch(r"[A-Z][a-z]+ \d{4}", user["member_since"])


def test_get_user_by_id_missing():
    assert get_user_by_id(999999) is None


def test_get_summary_stats(demo_user_id):
    summary = get_summary_stats(demo_user_id)

    assert summary["total_spent"] == pytest.approx(SEED_TOTAL)
    assert summary["transaction_count"] == SEED_COUNT
    assert summary["top_category"] == "Bills"


def test_get_summary_stats_blank(blank_user_id):
    assert get_summary_stats(blank_user_id) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


def test_get_recent_transactions(demo_user_id):
    transactions = get_recent_transactions(demo_user_id)

    assert len(transactions) == SEED_COUNT
    for item in transactions:
        assert set(item) == {"id", "date", "description", "category", "amount"}
    dates = [item["date"] for item in transactions]
    assert dates == sorted(dates, reverse=True)
    assert sum(item["amount"] for item in transactions) == pytest.approx(SEED_TOTAL)


def test_get_recent_transactions_limit(demo_user_id):
    assert len(get_recent_transactions(demo_user_id, limit=3)) == 3


def test_get_recent_transactions_blank(blank_user_id):
    assert get_recent_transactions(blank_user_id) == []


def test_get_category_breakdown(demo_user_id):
    breakdown = get_category_breakdown(demo_user_id)

    assert len(breakdown) == len(CATEGORIES)
    assert {item["name"] for item in breakdown} == set(CATEGORIES)
    amounts = [item["amount"] for item in breakdown]
    assert amounts == sorted(amounts, reverse=True)
    assert all(isinstance(item["pct"], int) for item in breakdown)
    assert sum(item["pct"] for item in breakdown) == 100
    assert breakdown[0]["name"] == "Bills"
    assert breakdown[0]["pct"] == 34

    food = next(item for item in breakdown if item["name"] == "Food")
    assert food["amount"] == pytest.approx(21.75)


def test_get_category_breakdown_blank(blank_user_id):
    assert get_category_breakdown(blank_user_id) == []


# ------------------------------------------------------------------ #
# /profile route                                                      #
# ------------------------------------------------------------------ #

def test_profile_requires_login(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_profile_seed_user(client, demo_user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = demo_user_id

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in ("Demo User", "demo@spendly.com", "Member since ",
                     "180.19", "Bills", "₹", "Recent transactions",
                     "Category breakdown"):
        assert expected in body
    assert "346.24" not in body


def test_profile_transaction_rows(client, demo_user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = demo_user_id

    body = client.get("/profile").get_data(as_text=True)

    assert body.count('<td class="tx-date">') == SEED_COUNT
    shown = re.findall(r'tx-date">(\d{2} [A-Z][a-z]{2} \d{4})</td>', body)
    assert len(shown) == SEED_COUNT
    parsed = [datetime.strptime(value, "%d %b %Y") for value in shown]
    assert parsed == sorted(parsed, reverse=True)


def test_profile_category_rows(client, demo_user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = demo_user_id

    body = client.get("/profile").get_data(as_text=True)

    assert body.count("bar-fill bar-fill--") == len(CATEGORIES)
    widths = [int(value) for value in re.findall(r"width: (\d+)%", body)]
    assert len(widths) == len(CATEGORIES)
    assert sum(widths) == 100


def test_profile_blank_user(client, blank_user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = blank_user_id

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹0.00" in body
    assert ">0<" in body
    assert "—" in body
    assert "bar-fill" not in body
    assert '<td class="tx-date">' not in body


def test_profile_stale_session(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 999999

    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
