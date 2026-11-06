"""Tests for the Step 6 date filter on /profile (app.py + database/queries.py).

Contract: .pi/specs/06-date-filter-profile.md

Fixture rows are placed on calendar-month boundaries relative to `date.today()`
so every preset window boundary is exercised deterministically, and every
expected total is derived from the fixture rows themselves instead of being
hardcoded. Importing `app` seeds the database, so it is only imported inside
tests that pass through the `temp_db` fixture.
"""

import html
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

import pytest

import database.db as db_module
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

INVERTED_FLASH = "Start date must be before end date."

# Labels and month offsets pinned by the spec's preset table.
PRESET_WINDOWS = (
    ("This Month", 0),
    ("Last 3 Months", 2),
    ("Last 6 Months", 5),
)
ALL_TIME_LABEL = "All Time"


# ------------------------------------------------------------------ #
# Local helpers                                                       #
# ------------------------------------------------------------------ #

def _month_start(day, months_back=0):
    """First day of the month `months_back` before `day`'s month (ISO text).

    Deliberately an independent mirror of the spec's integer month maths, so a
    wrong implementation cannot define its own expected value.
    """
    total = day.year * 12 + day.month - 1 - months_back
    year, month = divmod(total, 12)
    return date(year, month + 1, 1).isoformat()


def _unpadded(iso_date):
    """'2026-03-01' -> '2026-3-1' (strptime accepts it, SQLite ordering does not)."""
    year, month, day = iso_date.split("-")
    return f"{year}-{int(month)}-{int(day)}"


def _in_range(row, date_from, date_to):
    return ((date_from is None or row["date"] >= date_from)
            and (date_to is None or row["date"] <= date_to))


def _top_category(rows):
    """Top category of a row set: SUM(amount) DESC, category ASC, '—' if empty."""
    totals = {}
    for row in rows:
        totals[row["category"]] = totals.get(row["category"], 0) + row["amount"]
    if not totals:
        return "—"
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _expected(rows, date_from=None, date_to=None):
    """(total, count, top_category) for the fixture rows inside an ISO range."""
    picked = [row for row in rows if _in_range(row, date_from, date_to)]
    return round(sum(row["amount"] for row in picked), 2), len(picked), _top_category(picked)


def _stats(body):
    """The three rendered stat-card values: (total, transactions, top category)."""
    values = re.findall(r'<span class="stat-value">([^<]*)</span>', body)
    assert len(values) == 3, f"expected 3 stat cards, got {values!r}"
    return values[0], values[1], values[2]


def _transaction_dates(body):
    """ISO dates are rendered via `display_date`, so match the rendered rows."""
    return re.findall(r'<td class="tx-date">([^<]+)</td>', body)


def _breakdown_labels(body):
    return re.findall(r'<span class="breakdown-label">([^<]+)</span>', body)


def _preset_links(body):
    """[(label, href, class_attr)] for every `.filter-preset` anchor."""
    anchors = re.findall(r"<a\b[^>]*class=\"[^\"]*filter-preset[^\"]*\"[^>]*>[^<]+</a>", body)
    links = []
    for anchor in anchors:
        classes = re.search(r'class="([^"]+)"', anchor).group(1)
        href = re.search(r'href="([^"]+)"', anchor).group(1)
        label = re.search(r">([^<]+)</a>", anchor).group(1)
        # Jinja escapes `&` in attribute values as `&amp;`.
        links.append((label.strip(), html.unescape(href), classes))
    return links


def _rendered_date(iso_date):
    """Mirror of the `display_date` filter for assertions on rendered rows."""
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d %b %Y")


def _sign_in(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


# ------------------------------------------------------------------ #
# Fixtures: users with fixed-date expenses                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def dated_rows():
    """Rows pinned to month boundaries around today (plus one future row).

    today 10.00 Food | this-month start 20.00 Food | -2mo 30.00 Transport |
    -5mo 40.00 Bills | -7mo 50.00 Bills | today+15d 60.00 Bills (future)

    Unfiltered top category is Bills; "This Month" top category is Food, which
    is what makes a filtered top-category aggregate observable.
    """
    today = date.today()
    return [
        {"date": today.isoformat(), "amount": 10.00, "category": "Food",
         "description": "Coffee today"},
        {"date": _month_start(today, 0), "amount": 20.00, "category": "Food",
         "description": "Groceries"},
        {"date": _month_start(today, 2), "amount": 30.00, "category": "Transport",
         "description": "Monthly pass"},
        {"date": _month_start(today, 5), "amount": 40.00, "category": "Bills",
         "description": "Electricity"},
        {"date": _month_start(today, 7), "amount": 50.00, "category": "Bills",
         "description": "Old bill"},
        {"date": (today + timedelta(days=15)).isoformat(), "amount": 60.00,
         "category": "Bills", "description": "Future rent"},
    ]


def _insert_user(email, name="Dated User"):
    conn = db_module.get_db()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, "x"),
            )
        return cursor.lastrowid
    finally:
        conn.close()


def _insert_expenses(user_id, rows):
    conn = db_module.get_db()
    try:
        with conn:
            conn.executemany(
                "INSERT INTO expenses "
                "(user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                [(user_id, row["amount"], row["category"], row["date"],
                  row["description"]) for row in rows],
            )
    finally:
        conn.close()


@pytest.fixture
def dated_user(temp_db, dated_rows):
    """(user_id, rows) for a fresh user owning the dated fixture rows."""
    user_id = _insert_user("dated@spendly.com")
    _insert_expenses(user_id, dated_rows)
    return user_id, dated_rows


@pytest.fixture
def other_dated_user(temp_db):
    """A second user whose rows overlap every window, with a loud category."""
    rows = [
        {"date": date.today().isoformat(), "amount": 999.00,
         "category": "Shopping", "description": "Other user today"},
        {"date": _month_start(date.today(), 2), "amount": 888.00,
         "category": "Shopping", "description": "Other user -2mo"},
    ]
    user_id = _insert_user("other@spendly.com", name="Other User")
    _insert_expenses(user_id, rows)
    return user_id, rows


@pytest.fixture
def dated_client(client, dated_user):
    user_id, _ = dated_user
    return _sign_in(client, user_id)


# ------------------------------------------------------------------ #
# Module helpers named by the spec                                    #
# ------------------------------------------------------------------ #

def test_build_presets_windows_and_shape(temp_db):
    import app as app_module

    today = date.today()
    presets = app_module._build_presets(today, None, None)

    assert [(p["key"], p["label"]) for p in presets[:3]] == [
        ("this_month", "This Month"),
        ("last_3_months", "Last 3 Months"),
        ("last_6_months", "Last 6 Months"),
    ]
    assert presets[-1]["key"] == "all_time"
    assert presets[-1]["label"] == ALL_TIME_LABEL
    for preset in presets:
        assert set(preset) == {"key", "label", "date_from", "date_to", "active"}, (
            "unexpected preset keys"
        )

    for preset, (_, months_back) in zip(presets[:3], PRESET_WINDOWS):
        assert preset["date_from"] == _month_start(today, months_back)
        assert preset["date_to"] == today.isoformat()

    # No parameters: only "All Time" is active.
    assert [p["label"] for p in presets if p["active"]] == [ALL_TIME_LABEL]

    # A request range equal to a preset window activates exactly that preset.
    this_month = (presets[0]["date_from"], presets[0]["date_to"])
    active = [p["label"] for p in app_module._build_presets(today, *this_month)
              if p["active"]]
    assert active == ["This Month"]


@pytest.mark.parametrize("raw,expected_iso", [
    ("2026-11-05", "2026-11-05"),
    ("2026-1-5", "2026-01-05"),
    (" 2026-03-01 ", "2026-03-01"),
    ("", None),
    (None, None),
    ("not-a-date", None),
    ("2026-02-30", None),
    ("2026-01-01' OR '1'='1", None),
])
def test_parse_iso_date_normalises_or_rejects(temp_db, raw, expected_iso):
    import app as app_module

    assert app_module._parse_iso_date(raw) == expected_iso


@pytest.mark.parametrize("day,months_back,first", [
    (date(2026, 11, 5), 0, "2026-11-01"),
    (date(2026, 1, 15), 2, "2025-11-01"),   # year rollover going back
    (date(2026, 3, 31), 6, "2025-09-01"),
    (date(2026, 2, 1), 5, "2025-09-01"),
    (date(2024, 2, 29), 1, "2024-01-01"),
])
def test_month_start_uses_calendar_month_maths(temp_db, day, months_back, first):
    import app as app_module

    assert app_module._month_start(day, months_back) == first


# ------------------------------------------------------------------ #
# Query helpers (database/queries.py)                                 #
# ------------------------------------------------------------------ #

def test_summary_without_bounds_equals_explicit_none_bounds(dated_user):
    user_id, rows = dated_user

    assert get_summary_stats(user_id) == get_summary_stats(
        user_id, date_from=None, date_to=None
    )
    total, count, top = _expected(rows)
    assert get_summary_stats(user_id) == {
        "total_spent": pytest.approx(total),
        "transaction_count": count,
        "top_category": top,
    }


def test_summary_top_category_comes_from_filtered_rows(dated_user):
    user_id, rows = dated_user
    today = date.today()
    date_from, date_to = _month_start(today, 0), today.isoformat()

    summary = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    total, count, top = _expected(rows, date_from, date_to)

    assert top == "Food", "fixture sanity: this-month top category differs from all-time"
    assert _expected(rows)[2] == "Bills", "fixture sanity: all-time top category"
    assert summary["top_category"] == "Food"
    assert summary["total_spent"] == pytest.approx(total)
    assert summary["transaction_count"] == count


@pytest.mark.parametrize("one_sided", ["from", "to"])
def test_summary_one_sided_bounds_apply_only_that_bound(dated_user, one_sided):
    user_id, rows = dated_user
    today = date.today()

    if one_sided == "from":
        bounds = {"date_from": _month_start(today, 5)}
    else:
        bounds = {"date_to": _month_start(today, 2)}

    total, count, top = _expected(rows, **bounds)
    summary = get_summary_stats(user_id, **bounds)

    assert summary["total_spent"] == pytest.approx(total)
    assert summary["transaction_count"] == count
    assert summary["top_category"] == top


def test_recent_transactions_range_is_newest_first_and_limited(dated_user):
    user_id, rows = dated_user
    today = date.today()
    date_from = _month_start(today, 5)

    transactions = get_recent_transactions(
        user_id, date_from=date_from, date_to=today.isoformat()
    )
    picked = [row for row in rows
              if _in_range(row, date_from, today.isoformat())]

    assert len(transactions) == len(picked)
    assert all(item["date"] >= date_from for item in transactions)
    assert all(item["date"] <= today.isoformat() for item in transactions)
    assert [item["date"] for item in transactions] == sorted(
        (item["date"] for item in transactions), reverse=True
    )
    assert sum(item["amount"] for item in transactions) == pytest.approx(
        sum(row["amount"] for row in picked)
    )

    # `limit` still truncates a filtered view (to the newest in-range rows).
    newest = max((row["date"] for row in picked))
    limited = get_recent_transactions(
        user_id, 1, date_from=date_from, date_to=today.isoformat()
    )
    assert len(limited) == 1
    assert limited[0]["date"] == newest


def test_recent_transactions_keeps_default_and_positional_limit(dated_user):
    user_id, rows = dated_user

    assert get_recent_transactions(user_id) == get_recent_transactions(
        user_id, limit=10, date_from=None, date_to=None
    )
    assert len(get_recent_transactions(user_id)) == min(len(rows), 10)
    # Trailing date params: the second positional argument is still `limit`.
    assert len(get_recent_transactions(user_id, 2)) == 2


def test_category_breakdown_range_percentages(dated_user):
    user_id, rows = dated_user
    today = date.today()
    date_from = _month_start(today, 5)

    breakdown = get_category_breakdown(
        user_id, date_from=date_from, date_to=today.isoformat()
    )
    picked = [row for row in rows
              if _in_range(row, date_from, today.isoformat())]

    assert {item["name"] for item in breakdown} == {row["category"] for row in picked}
    assert sum(item["amount"] for item in breakdown) == pytest.approx(
        sum(row["amount"] for row in picked)
    )
    amounts = [item["amount"] for item in breakdown]
    assert amounts == sorted(amounts, reverse=True)
    assert all(isinstance(item["pct"], int) for item in breakdown)
    assert sum(item["pct"] for item in breakdown) == 100


def test_query_helpers_empty_range_return_zero_values(dated_user):
    user_id, _ = dated_user
    empty = {"date_from": "2000-01-01", "date_to": "2000-12-31"}

    assert get_summary_stats(user_id, **empty) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }
    assert get_recent_transactions(user_id, **empty) == []
    assert get_category_breakdown(user_id, **empty) == []


def test_query_helpers_never_leak_another_users_rows(dated_user, other_dated_user):
    user_id, rows = dated_user
    other_id, other_rows = other_dated_user
    today = date.today()
    date_from, date_to = _month_start(today, 5), today.isoformat()

    summary = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    total, count, top = _expected(rows, date_from, date_to)
    assert summary["total_spent"] == pytest.approx(total)
    assert summary["transaction_count"] == count
    assert summary["top_category"] == top

    transactions = get_recent_transactions(
        user_id, date_from=date_from, date_to=date_to
    )
    assert all(item["amount"] < 100 for item in transactions), \
        "another user's large expenses leaked into the transaction list"

    breakdown = get_category_breakdown(
        user_id, date_from=date_from, date_to=date_to
    )
    assert "Shopping" not in {item["name"] for item in breakdown}

    # And the mirror image: the other user only sees their own rows.
    other_summary = get_summary_stats(
        other_id, date_from=date_from, date_to=date_to
    )
    other_total, other_count, other_top = _expected(other_rows, date_from, date_to)
    assert other_summary["total_spent"] == pytest.approx(other_total)
    assert other_summary["transaction_count"] == other_count
    assert other_summary["top_category"] == "Shopping"
    assert other_top == "Shopping"


# ------------------------------------------------------------------ #
# /profile route: unfiltered parity with Step 5                       #
# ------------------------------------------------------------------ #

def test_profile_without_params_matches_unfiltered_helper(client, demo_user_id):
    """No query params must behave exactly like Step 5's unfiltered profile."""
    _sign_in(client, demo_user_id)

    response = client.get("/profile")
    body = response.get_data(as_text=True)
    summary = get_summary_stats(demo_user_id)
    transactions = get_recent_transactions(demo_user_id)

    assert response.status_code == 200
    total, count, top = _stats(body)
    assert total == f"₹{summary['total_spent']:.2f}"
    assert count == str(summary["transaction_count"])
    assert top == summary["top_category"]
    assert len(_transaction_dates(body)) == len(transactions)
    assert _breakdown_labels(body), "unfiltered view must render a breakdown"


def test_profile_unfiltered_includes_future_dated_rows(dated_client, dated_user):
    _, rows = dated_user

    body = dated_client.get("/profile").get_data(as_text=True)
    total, count, top = _expected(rows)

    assert _stats(body) == (f"₹{total:.2f}", str(count), top)
    assert _rendered_date((date.today() + timedelta(days=15)).isoformat()) in _transaction_dates(body)


# ------------------------------------------------------------------ #
# /profile route: query-string parsing                                #
# ------------------------------------------------------------------ #

def test_profile_blank_params_are_treated_as_absent(dated_client, dated_user):
    _, rows = dated_user
    total, count, top = _expected(rows)

    response = dated_client.get("/profile?date_from=&date_to=")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert _stats(body) == (f"₹{total:.2f}", str(count), top)
    links = dict((label, (href, classes)) for label, href, classes in _preset_links(body))
    assert "filter-preset--active" in links[ALL_TIME_LABEL][1]
    assert body.count('aria-current="page"') == 1


def test_profile_whitespace_params_are_treated_as_absent(dated_client, dated_user):
    _, rows = dated_user
    total, _, _ = _expected(rows)

    body = dated_client.get("/profile?date_from=%20&date_to=%20%20").get_data(as_text=True)

    assert _stats(body)[0] == f"₹{total:.2f}"
    assert "filter-preset--active" in dict(
        (label, classes) for label, _, classes in _preset_links(body)
    )[ALL_TIME_LABEL]


@pytest.mark.parametrize("label,months_back", PRESET_WINDOWS)
def test_profile_preset_window_filters_all_sections(
    dated_client, dated_user, label, months_back
):
    _, rows = dated_user
    today = date.today()
    date_from = _month_start(today, months_back)
    date_to = today.isoformat()
    total, count, top = _expected(rows, date_from, date_to)

    response = dated_client.get(f"/profile?date_from={date_from}&date_to={date_to}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert _stats(body) == (f"₹{total:.2f}", str(count), top)
    # Future-dated rows stay hidden because every preset ends today.
    assert _rendered_date((today + timedelta(days=15)).isoformat()) not in _transaction_dates(body)

    active = [name for name, _, classes in _preset_links(body)
              if "filter-preset--active" in classes]
    assert active == [label]
    assert body.count('aria-current="page"') == 1


def test_preset_links_have_resolvable_hrefs_and_clean_all_time_url(app, dated_client):
    from flask import url_for

    body = dated_client.get("/profile").get_data(as_text=True)
    links = _preset_links(body)

    assert [label for label, _, _ in links] == [
        "This Month", "Last 3 Months", "Last 6 Months", ALL_TIME_LABEL
    ]

    today = date.today()
    with app.test_request_context():
        expected = {
            label: url_for("profile",
                           date_from=_month_start(today, months_back),
                           date_to=today.isoformat())
            for label, months_back in PRESET_WINDOWS
        }
        expected[ALL_TIME_LABEL] = url_for("profile")

    assert expected[ALL_TIME_LABEL] == "/profile"
    for label, href, _ in links:
        assert href == expected[label], f"wrong href for {label}"

    # No live "?date_from=None" style leftovers from url_for(None, None).
    for label, href, _ in links:
        assert "None" not in href, f"{label} href leaked a None value"


def test_profile_active_preset_is_single_for_preset_and_all_time(dated_client):
    today = date.today()
    urls = ["/profile"] + [
        f"/profile?date_from={_month_start(today, months_back)}"
        f"&date_to={today.isoformat()}"
        for _, months_back in PRESET_WINDOWS
    ]

    for url in urls:
        body = dated_client.get(url).get_data(as_text=True)
        assert body.count("filter-preset--active") == 1, f"expected one active preset for {url}"
        assert body.count('aria-current="page"') == 1, f"expected one aria-current for {url}"


def test_profile_custom_range_filters_all_sections_and_prefills(dated_client, dated_user):
    _, rows = dated_user
    today = date.today()
    date_from = _month_start(today, 5)
    date_to = _month_start(today, 2)
    total, count, top = _expected(rows, date_from, date_to)

    response = dated_client.get(f"/profile?date_from={date_from}&date_to={date_to}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert _stats(body) == (f"₹{total:.2f}", str(count), top)
    assert top == "Bills"

    rendered = _transaction_dates(body)
    assert len(rendered) == count
    assert all(date_from <= row["date"] <= date_to
               for row in rows if _rendered_date(row["date"]) in rendered)

    # Breakdown is filtered too, and still uses ₹.
    labels = _breakdown_labels(body)
    assert set(labels) == {row["category"] for row in rows
                           if _in_range(row, date_from, date_to)}
    assert "Food" not in labels
    assert f"₹{total:.2f}" in body
    assert "₹888.00" not in body and "₹999.00" not in body

    # A custom range that matches no preset leaves every preset inactive...
    assert body.count("filter-preset--active") == 0
    assert body.count('aria-current="page"') == 0
    # ...but the inputs show the normalised applied bounds.
    assert f'value="{date_from}"' in body
    assert f'value="{date_to}"' in body


@pytest.mark.parametrize("bounds", ["from_only", "to_only"])
def test_profile_one_sided_range_filters_only_that_bound(dated_client, dated_user, bounds):
    _, rows = dated_user
    today = date.today()

    if bounds == "from_only":
        params = {"date_from": _month_start(today, 2)}
        url = f"/profile?date_from={params['date_from']}"
    else:
        params = {"date_to": _month_start(today, 0)}
        url = f"/profile?date_to={params['date_to']}"

    total, count, top = _expected(rows, **params)
    body = dated_client.get(url).get_data(as_text=True)

    assert _stats(body) == (f"₹{total:.2f}", str(count), top)

    if bounds == "from_only":
        # No upper bound: the future-dated row is reachable.
        assert _rendered_date((today + timedelta(days=15)).isoformat()) in _transaction_dates(body)
    else:
        assert _rendered_date(today.isoformat()) not in _transaction_dates(body)


def test_profile_inverted_range_flashes_and_falls_back(dated_client, dated_user):
    _, rows = dated_user
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    total, count, top = _expected(rows)

    response = dated_client.get(
        f"/profile?date_from={today.isoformat()}&date_to={yesterday}"
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert INVERTED_FLASH in body
    assert "flash--error" in body
    # Both bounds dropped -> unfiltered view, "All Time" active again.
    assert _stats(body) == (f"₹{total:.2f}", str(count), top)
    active = [label for label, _, classes in _preset_links(body)
              if "filter-preset--active" in classes]
    assert active == [ALL_TIME_LABEL]
    assert body.count('aria-current="page"') == 1


@pytest.mark.parametrize("bad_from,bad_to", [
    ("not-a-date", None),
    ("2026-13-01", None),
    ("2026-02-30", None),
    ("2026-01-01' OR '1'='1", None),
    (None, "not-a-date"),
])
def test_profile_malformed_date_is_ignored_but_other_bound_applies(
    dated_client, dated_user, bad_from, bad_to
):
    _, rows = dated_user
    today = date.today()
    good_from = _month_start(today, 2)
    good_to = today.isoformat()

    query_from = bad_from if bad_from is not None else good_from
    query_to = bad_to if bad_to is not None else good_to
    query = f"date_from={quote(query_from)}&date_to={quote(query_to)}"
    response = dated_client.get(f"/profile?{query}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert INVERTED_FLASH not in body

    params = {"date_from": None if bad_from else good_from,
              "date_to": None if bad_to else good_to}
    total, count, top = _expected(rows, **params)
    assert _stats(body) == (f"₹{total:.2f}", str(count), top)


def test_profile_single_day_range(dated_client, dated_user):
    _, rows = dated_user
    today = date.today().isoformat()
    total, count, top = _expected(rows, today, today)

    body = dated_client.get(f"/profile?date_from={today}&date_to={today}").get_data(
        as_text=True
    )

    assert _stats(body) == (f"₹{total:.2f}", str(count), top)
    dates = _transaction_dates(body)
    assert len(dates) == count
    assert set(dates) == {_rendered_date(today)}


@pytest.mark.parametrize("style", ["unpadded", "whitespace"])
def test_profile_date_params_are_normalised_before_use(dated_client, dated_user, style):
    _, rows = dated_user
    today = date.today()
    date_from = _month_start(today, 2)
    date_to = _month_start(today, 0)
    total, count, top = _expected(rows, date_from, date_to)

    if style == "unpadded":
        raw_from, raw_to = _unpadded(date_from), _unpadded(date_to)
    else:
        raw_from, raw_to = f"%20{date_from}%20", f"%20{date_to}%20"

    body = dated_client.get(
        f"/profile?date_from={raw_from}&date_to={raw_to}"
    ).get_data(as_text=True)

    assert _stats(body) == (f"₹{total:.2f}", str(count), top)
    # The template receives (and prefills) the zero-padded ISO values only.
    assert f'value="{date_from}"' in body
    assert f'value="{date_to}"' in body


# ------------------------------------------------------------------ #
# /profile route: empty ranges                                        #
# ------------------------------------------------------------------ #

def test_profile_empty_range_shows_zero_state_without_errors(dated_client):
    response = dated_client.get("/profile?date_from=2000-01-01&date_to=2000-12-31")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert _stats(body) == ("₹0.00", "0", "—")
    assert _transaction_dates(body) == []
    assert "bar-fill--" not in body
    assert _breakdown_labels(body) == []
    assert "No transactions in this range." in body
    assert "No spending in this range." in body
    assert body.count("empty-note") >= 2


def test_profile_user_without_expenses_sees_zero_state_for_any_filter(
    client, blank_user_id
):
    _sign_in(client, blank_user_id)
    today = date.today().isoformat()

    for url in (
        "/profile",
        f"/profile?date_from={_month_start(date.today(), 5)}&date_to={today}",
        f"/profile?date_to={today}",
    ):
        response = client.get(url)
        body = response.get_data(as_text=True)
        assert response.status_code == 200, url
        assert _stats(body) == ("₹0.00", "0", "—"), url
        assert "No transactions in this range." in body, url
        assert "No spending in this range." in body, url


# ------------------------------------------------------------------ #
# /profile route: auth guard and per-user isolation                   #
# ------------------------------------------------------------------ #

def test_profile_with_filter_params_requires_login(client):
    response = client.get("/profile?date_from=2026-01-01&date_to=2026-12-31")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_profile_filtered_view_isolates_users(client, app, dated_user, other_dated_user):
    user_id, rows = dated_user
    other_id, other_rows = other_dated_user
    today = date.today().isoformat()
    date_from = _month_start(date.today(), 5)

    first = _sign_in(app.test_client(), user_id)
    body = first.get(f"/profile?date_from={date_from}&date_to={today}").get_data(
        as_text=True
    )
    total, count, top = _expected(rows, date_from, today)
    assert _stats(body) == (f"₹{total:.2f}", str(count), top)
    assert "999.00" not in body and "888.00" not in body
    assert "Shopping" not in body

    second = _sign_in(app.test_client(), other_id)
    body = second.get(f"/profile?date_from={date_from}&date_to={today}").get_data(
        as_text=True
    )
    other_total, other_count, other_top = _expected(other_rows, date_from, today)
    assert _stats(body) == (f"₹{other_total:.2f}", str(other_count), other_top)
    assert other_top == "Shopping"
    assert "Food" not in body and "Bills" not in body


# ------------------------------------------------------------------ #
# /profile route: rendered contract details                           #
# ------------------------------------------------------------------ #

def test_profile_currency_symbol_survives_any_filter(dated_client, dated_user):
    today = date.today()
    urls = [
        "/profile",
        f"/profile?date_from={_month_start(today, 0)}&date_to={today.isoformat()}",
        f"/profile?date_from={_month_start(today, 5)}&date_to={_month_start(today, 2)}",
        "/profile?date_from=2000-01-01&date_to=2000-12-31",
    ]

    for url in urls:
        body = dated_client.get(url).get_data(as_text=True)
        total, _, _ = _stats(body)
        assert total.startswith("₹"), f"total spent must render ₹ for {url}"
        for amount in re.findall(r'<td class="tx-amount">([^<]+)</td>', body):
            assert amount.startswith("₹"), f"row amount without ₹ for {url}: {amount!r}"
        for amount in re.findall(r'<span class="breakdown-amount">([^<]+)</span>', body):
            assert amount.startswith("₹"), f"breakdown amount without ₹ for {url}"
        assert "$" not in body, f"non-₹ currency rendered for {url}"


def test_profile_subtitle_is_period_neutral(dated_client):
    body = dated_client.get("/profile").get_data(as_text=True)

    assert "A snapshot of where your money went." in body
    assert "A snapshot of where your money went this month." not in body
