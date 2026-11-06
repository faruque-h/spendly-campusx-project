"""Tests for the Step 7 add-expense form (app.py + database/queries.py).

Contract: .pi/specs/07-add-expense.md

Importing `app` seeds the database, so it is only imported inside tests that
pass through the `temp_db` fixture. Every expectation here is taken from the
spec — status codes (400 on validation failure, 302 only after a write), the
four error strings, sticky re-render values, canonical ISO date storage, 2-dp
amount rounding, and rows attributed to the session user.
"""

import re
from datetime import date as date_cls
from urllib.parse import urlsplit

import pytest

import database.db as db_module
from database.db import CATEGORIES
from database.queries import insert_expense

# Error strings pinned by the spec's validation table.
AMOUNT_ERROR = "Please enter an amount greater than 0."
CATEGORY_ERROR = "Please choose a valid category."
DATE_ERROR = "Please enter a valid date (YYYY-MM-DD)."
DESCRIPTION_ERROR = "Description must be 200 characters or fewer."
SUCCESS_FLASH = "Expense added."

_OPTION_RE = re.compile(r'<option value="([^"]*)"([^>]*)>')
_INPUT_RE = re.compile(r'<input\b[^>]*name="([^"]+)"[^>]*>', re.S)


# ------------------------------------------------------------------ #
# Local helpers                                                       #
# ------------------------------------------------------------------ #

def _sign_in(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _redirect_path(response):
    """Path (no query string) of a redirect's Location header."""
    return urlsplit(response.headers["Location"]).path


def _expenses_for(user_id):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


def _expense_count(user_id):
    return len(_expenses_for(user_id))


def _total_expense_count():
    conn = db_module.get_db()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()["n"]
    finally:
        conn.close()


def _options(body):
    """{option value: whether the option carries `selected`}."""
    return {value: "selected" in attrs
            for value, attrs in _OPTION_RE.findall(body)}


def _inputs(body):
    """{input name: full <input ...> tag text}."""
    return {match.group(1): match.group(0)
            for match in _INPUT_RE.finditer(body)}


def _valid_form(**overrides):
    form = {
        "amount": "50.00",
        "category": "Food",
        "date": "2026-03-20",
        "description": "Lunch",
    }
    form.update(overrides)
    return form


# ------------------------------------------------------------------ #
# Query helper: insert_expense                                        #
# ------------------------------------------------------------------ #

def test_insert_expense_returns_row_id_and_persists_values(temp_db,
                                                           blank_user_id):
    new_id = insert_expense(blank_user_id, 50.0, "Food", "2026-03-20", "Lunch")

    assert new_id, "insert_expense must return the new row id"

    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE id = ?", (new_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "returned id must address the inserted row"
    assert row["user_id"] == blank_user_id
    assert row["amount"] == pytest.approx(50.0)
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"
    assert row["description"] == "Lunch"


def test_insert_expense_stores_null_description(temp_db, blank_user_id):
    new_id = insert_expense(blank_user_id, 12.5, "Bills", "2026-03-21", None)

    conn = db_module.get_db()
    try:
        value = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (new_id,),
        ).fetchone()["description"]
    finally:
        conn.close()

    assert value is None, "description=None must be stored as SQL NULL"


def test_insert_expense_stores_description_verbatim(temp_db, blank_user_id):
    new_id = insert_expense(blank_user_id, 1.0, "Other", "2026-03-22",
                            "  padded text  ")

    conn = db_module.get_db()
    try:
        value = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (new_id,),
        ).fetchone()["description"]
    finally:
        conn.close()

    assert value == "  padded text  ", "helper must not rewrite the description"


# ------------------------------------------------------------------ #
# GET /expenses/add                                                   #
# ------------------------------------------------------------------ #

def test_add_expense_get_requires_login(client):
    response = client.get("/expenses/add")

    assert response.status_code == 302
    assert _redirect_path(response) == "/login", "expected the login page"
    assert not urlsplit(response.headers["Location"]).query, \
        "spec forbids a next/return-to parameter"


def test_add_expense_get_renders_empty_form(client, blank_user_id):
    _sign_in(client, blank_user_id)

    response = client.get("/expenses/add")
    body = response.get_data(as_text=True)
    inputs = _inputs(body)

    assert response.status_code == 200
    assert "Add expense — Spendly" in body, "expected the spec's page title"
    assert 'method="POST"' in body
    assert 'action="/expenses/add"' in body
    assert set(inputs) >= {"amount", "date", "description"}

    # Amount: numeric, 2 dp, positive, required.
    assert 'type="number"' in inputs["amount"]
    assert 'step="0.01"' in inputs["amount"]
    assert 'min="0.01"' in inputs["amount"]
    assert "required" in inputs["amount"]
    assert 'value=""' in inputs["amount"], "GET must leave amount blank"

    # Date: pre-filled with today's ISO date.
    assert 'type="date"' in inputs["date"]
    assert "required" in inputs["date"]
    assert f'value="{date_cls.today().isoformat()}"' in inputs["date"]

    # Description: optional, capped at 200 characters.
    assert 'maxlength="200"' in inputs["description"]
    assert "required" not in inputs["description"]
    assert 'value=""' in inputs["description"]

    assert "Save Expense" in body, "expected the submit button label"


def test_add_expense_get_lists_every_category_option(client, blank_user_id):
    _sign_in(client, blank_user_id)

    body = client.get("/expenses/add").get_data(as_text=True)
    options = _options(body)

    assert set(options) == set(CATEGORIES), \
        "dropdown must be driven by CATEGORIES, with no placeholder option"
    assert len(options) == len(CATEGORIES) == 7
    assert options[CATEGORIES[0]] is True, \
        "GET must preselect the first category"


# ------------------------------------------------------------------ #
# POST /expenses/add — auth guard                                     #
# ------------------------------------------------------------------ #

def test_add_expense_get_with_stale_session_redirects_to_login(client,
                                                              temp_db):
    # A session pointing at a deleted user must not render the form, matching
    # /profile's stale-session handling.
    _sign_in(client, 999999)

    response = client.get("/expenses/add")

    assert response.status_code == 302
    assert _redirect_path(response) == "/login"
    with client.session_transaction() as sess:
        assert "user_id" not in sess, "the stale session must be cleared"


def test_add_expense_post_requires_login(client, blank_user_id):
    before = _total_expense_count()

    response = client.post("/expenses/add", data=_valid_form())

    assert response.status_code == 302
    assert _redirect_path(response) == "/login"
    assert _total_expense_count() == before, \
        "an unauthenticated POST must not write a row"


# ------------------------------------------------------------------ #
# POST /expenses/add — success                                        #
# ------------------------------------------------------------------ #

def test_add_expense_post_valid_redirects_and_saves_row(client, blank_user_id,
                                                        demo_user_id):
    _sign_in(client, blank_user_id)
    demo_before = _expense_count(demo_user_id)

    response = client.post("/expenses/add", data=_valid_form())

    assert response.status_code == 302
    assert _redirect_path(response) == "/profile", \
        "success must redirect to the bare profile page"

    rows = _expenses_for(blank_user_id)
    assert len(rows) == 1, "exactly one row must be inserted"
    assert rows[0]["user_id"] == blank_user_id, \
        "row must belong to the session user"
    assert rows[0]["amount"] == pytest.approx(50.0)
    assert rows[0]["category"] == "Food"
    assert rows[0]["date"] == "2026-03-20"
    assert rows[0]["description"] == "Lunch"
    assert _expense_count(demo_user_id) == demo_before, \
        "another user's ledger must be untouched"


def test_add_expense_post_valid_flashes_success_and_shows_on_profile(
        client, blank_user_id):
    _sign_in(client, blank_user_id)

    response = client.post("/expenses/add", data=_valid_form(),
                           follow_redirects=True)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert SUCCESS_FLASH in body, "spec requires the 'Expense added.' flash"
    assert "Lunch" in body, "new expense must appear in the transaction list"
    assert "₹50.00" in body, "amount must render as ₹ with 2 dp"
    assert "20 Mar 2026" in body, "date must render through display_date"


def test_add_expense_post_without_description_stores_null(client,
                                                          blank_user_id):
    _sign_in(client, blank_user_id)

    response = client.post("/expenses/add",
                           data=_valid_form(description=""))

    assert response.status_code == 302
    assert _redirect_path(response) == "/profile"

    rows = _expenses_for(blank_user_id)
    assert len(rows) == 1
    assert rows[0]["description"] is None, \
        "an empty description must be stored as NULL"


@pytest.mark.parametrize("submitted, stored", [
    ("2026-3-5", "2026-03-05"),
    ("2026-03-20", "2026-03-20"),
])
def test_add_expense_post_stores_canonical_iso_date(client, blank_user_id,
                                                    submitted, stored):
    _sign_in(client, blank_user_id)

    client.post("/expenses/add", data=_valid_form(date=submitted))

    rows = _expenses_for(blank_user_id)
    assert len(rows) == 1
    assert rows[0]["date"] == stored, \
        "dates must be zero-padded ISO so TEXT comparison stays correct"


@pytest.mark.parametrize("submitted, expected", [
    ("12.3456", 12.35),
    ("50.5", 50.5),
    ("0.005", 0.01),
])
def test_add_expense_post_rounds_amount_to_two_dp(client, blank_user_id,
                                                  submitted, expected):
    _sign_in(client, blank_user_id)

    client.post("/expenses/add", data=_valid_form(amount=submitted))

    rows = _expenses_for(blank_user_id)
    assert len(rows) == 1
    assert rows[0]["amount"] == pytest.approx(expected), \
        "stored amount must match the input's step=\"0.01\""


def test_add_expense_post_accepts_200_char_description(client, blank_user_id):
    _sign_in(client, blank_user_id)
    description = "x" * 200

    response = client.post("/expenses/add",
                           data=_valid_form(description=description))

    assert response.status_code == 302
    assert _redirect_path(response) == "/profile"
    assert _expenses_for(blank_user_id)[0]["description"] == description


def test_add_expense_post_stores_sql_like_description_literally(
        client, blank_user_id):
    _sign_in(client, blank_user_id)
    payload = "Robert'); DROP TABLE expenses;--"

    response = client.post("/expenses/add",
                           data=_valid_form(description=payload))

    assert response.status_code == 302
    rows = _expenses_for(blank_user_id)
    assert len(rows) == 1, "values must be bound as placeholders, not SQL"
    assert rows[0]["description"] == payload


# ------------------------------------------------------------------ #
# POST /expenses/add — validation failures (400, sticky, no write)     #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("amount", ["", "   ", "0", "-5", "abc", "nan", "inf",
                                    "-inf", "1e999",
                                    # rounds to 0.00: validation must run on
                                    # the normalised value, not the raw one
                                    "0.004", "0.001"])
def test_add_expense_post_invalid_amount_returns_400(client, blank_user_id,
                                                     amount):
    _sign_in(client, blank_user_id)
    before = _total_expense_count()

    response = client.post("/expenses/add", data=_valid_form(amount=amount))
    body = response.get_data(as_text=True)

    assert response.status_code == 400, "validation failures use 400"
    assert AMOUNT_ERROR in body
    assert _total_expense_count() == before, "no row may be written"

    expected = amount.strip()
    if expected:
        assert f'value="{expected}"' in _inputs(body)["amount"], \
            "the rejected amount must be retained in the field"


def test_add_expense_post_missing_amount_keeps_other_fields(client,
                                                            blank_user_id):
    _sign_in(client, blank_user_id)
    form = _valid_form(amount="", category="Bills")
    del form["amount"]  # field absent entirely

    response = client.post("/expenses/add", data=form)
    body = response.get_data(as_text=True)
    inputs = _inputs(body)

    assert response.status_code == 400
    assert AMOUNT_ERROR in body
    assert _options(body)["Bills"] is True, "submitted category stays selected"
    assert 'value="2026-03-20"' in inputs["date"], "submitted date is sticky"
    assert 'value="Lunch"' in inputs["description"], \
        "submitted description is sticky"
    assert "Lunch" in body


def test_add_expense_post_invalid_category_returns_400(client, blank_user_id):
    _sign_in(client, blank_user_id)
    before = _total_expense_count()

    response = client.post("/expenses/add", data=_valid_form(category="Pets"))
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert CATEGORY_ERROR in body
    assert _total_expense_count() == before

    # The valid submitted amount/date are still sticky on the re-render.
    assert 'value="50.00"' in _inputs(body)["amount"]
    assert 'value="2026-03-20"' in _inputs(body)["date"]


@pytest.mark.parametrize("value", ["", "20-03-2026", "2026-13-01",
                                   "2026-03-32", "not-a-date"])
def test_add_expense_post_invalid_date_returns_400(client, blank_user_id,
                                                   value):
    _sign_in(client, blank_user_id)
    before = _total_expense_count()

    response = client.post("/expenses/add", data=_valid_form(date=value))
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert DATE_ERROR in body
    assert _total_expense_count() == before


def test_add_expense_post_over_long_description_returns_400(client,
                                                            blank_user_id):
    _sign_in(client, blank_user_id)
    before = _total_expense_count()
    description = "x" * 201

    response = client.post("/expenses/add",
                           data=_valid_form(description=description))
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert DESCRIPTION_ERROR in body
    assert _total_expense_count() == before
    assert f'value="{description}"' in _inputs(body)["description"], \
        "the rejected description must be retained"


def test_add_expense_post_rejects_first_failing_rule_only(client,
                                                          blank_user_id):
    _sign_in(client, blank_user_id)

    # Amount fails first, so neither the category nor the date error appears.
    response = client.post("/expenses/add",
                           data=_valid_form(amount="abc", category="Pets",
                                            date="20-03-2026"))
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert AMOUNT_ERROR in body
    assert CATEGORY_ERROR not in body
    assert DATE_ERROR not in body


# ------------------------------------------------------------------ #
# POST /expenses/add — stale session (FK IntegrityError)              #
# ------------------------------------------------------------------ #

def test_add_expense_post_with_stale_session_redirects_to_login(
        client, temp_db):
    missing_user_id = 999999
    _sign_in(client, missing_user_id)
    before = _total_expense_count()

    response = client.post("/expenses/add", data=_valid_form())

    assert response.status_code == 302, "a stale session must not 500"
    assert _redirect_path(response) == "/login"
    assert _total_expense_count() == before, "the FK must block the insert"

    with client.session_transaction() as sess:
        assert "user_id" not in sess, "the stale session must be cleared"


# ------------------------------------------------------------------ #
# Entry point from /profile                                           #
# ------------------------------------------------------------------ #

def test_profile_links_to_add_expense_form(client, blank_user_id):
    _sign_in(client, blank_user_id)

    body = client.get("/profile").get_data(as_text=True)

    assert 'href="/expenses/add"' in body, \
        "spec requires an Add Expense link on /profile"
    assert "Add Expense" in body
