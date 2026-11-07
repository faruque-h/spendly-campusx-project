"""Tests for the Step 8 edit-expense form (app.py + database/queries.py).

Contract: .pi/specs/08-edit-expense.md

Importing `app` seeds the database, so it is only imported inside tests that
pass through the `temp_db` fixture. Status codes are pinned by the spec:
404 for a missing/foreign id, 400 for validation failures, 302 only after a
successful write.
"""

import re
from urllib.parse import urlsplit

import pytest

import database.db as db_module
from database.db import CATEGORIES
from database.queries import (
    get_expense_by_id,
    get_recent_transactions,
    insert_expense,
    update_expense,
)

# Error strings pinned by the shared Step 7 validation rules.
AMOUNT_ERROR = "Please enter an amount greater than 0."
CATEGORY_ERROR = "Please choose a valid category."
DATE_ERROR = "Please enter a valid date (YYYY-MM-DD)."
DESCRIPTION_ERROR = "Description must be 200 characters or fewer."
SUCCESS_FLASH = "Expense updated."

_OPTION_RE = re.compile(r'<option value="([^"]*)"([^>]*)>')
_INPUT_RE = re.compile(r'<input\b[^>]*name="([^"]+)"[^>]*>', re.S)

MISSING_ID = 999999


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


def _row(expense_id):
    """A single expense as a plain dict, for before/after comparisons."""
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE id = ?", (expense_id,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


def _other_user_expense():
    """Second user owning one expense; returns (user_id, expense_id)."""
    conn = db_module.get_db()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash) "
                "VALUES (?, ?, ?)",
                ("Other User", "other@spendly.com", "x"),
            )
            user_id = cursor.lastrowid
            cursor = conn.execute(
                "INSERT INTO expenses "
                "(user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, 7.0, "Other", "2026-03-01", "Someone else's"),
            )
        return user_id, cursor.lastrowid
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
        "amount": "99.00",
        "category": "Health",
        "date": "2026-03-25",
        "description": "Edited",
    }
    form.update(overrides)
    return form


def _seeded_expense(user_id, **overrides):
    """Insert one expense for `user_id`; returns its id."""
    values = {
        "amount": 12.5,
        "category": "Bills",
        "date": "2026-03-21",
        "description": "Coffee",
    }
    values.update(overrides)
    return insert_expense(user_id, values["amount"], values["category"],
                          values["date"], values["description"])


# ------------------------------------------------------------------ #
# Query helpers                                                       #
# ------------------------------------------------------------------ #

def test_get_expense_by_id_returns_owned_row(demo_user_id):
    expected = dict(_expenses_for(demo_user_id)[0])

    expense = get_expense_by_id(expected["id"], demo_user_id)

    assert set(expense) == {"id", "amount", "category", "date", "description"}
    assert expense["id"] == expected["id"]
    assert expense["amount"] == pytest.approx(expected["amount"])
    assert expense["category"] == expected["category"]
    assert expense["date"] == expected["date"]
    assert expense["description"] == expected["description"]


def test_get_expense_by_id_hides_other_users_row(demo_user_id,
                                                 blank_user_id):
    demo_expense_id = _expenses_for(demo_user_id)[0]["id"]

    assert get_expense_by_id(demo_expense_id, blank_user_id) is None, \
        "a foreign expense must be indistinguishable from a missing one"


def test_get_expense_by_id_missing_returns_none(demo_user_id):
    assert get_expense_by_id(MISSING_ID, demo_user_id) is None


def test_update_expense_updates_owned_row(blank_user_id):
    expense_id = _seeded_expense(blank_user_id)

    changed = update_expense(expense_id, blank_user_id, 99.0, "Health",
                             "2026-03-25", "Edited")

    assert changed == 1
    row = _row(expense_id)
    assert row["id"] == expense_id
    assert row["user_id"] == blank_user_id, "ownership must not change"
    assert row["amount"] == pytest.approx(99.0)
    assert row["category"] == "Health"
    assert row["date"] == "2026-03-25"
    assert row["description"] == "Edited"


def test_update_expense_leaves_other_users_row_untouched(demo_user_id,
                                                         blank_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]
    before = _row(expense_id)

    changed = update_expense(expense_id, blank_user_id, 1.0, "Other",
                             "2026-01-01", "hijacked")

    assert changed == 0, "the user_id guard must match zero rows"
    assert _row(expense_id) == before, "foreign rows must be immutable"


def test_update_expense_stores_null_description(blank_user_id):
    expense_id = _seeded_expense(blank_user_id)

    assert update_expense(expense_id, blank_user_id, 5.0, "Other",
                          "2026-03-22", None) == 1
    assert _row(expense_id)["description"] is None


def test_get_recent_transactions_includes_row_ids(demo_user_id):
    transactions = get_recent_transactions(demo_user_id)
    expected = {row["id"] for row in _expenses_for(demo_user_id)}

    assert len(transactions) == len(expected)
    assert all(set(item) == {"id", "date", "description", "category",
                             "amount"} for item in transactions)
    assert {item["id"] for item in transactions} == expected


# ------------------------------------------------------------------ #
# GET /expenses/<id>/edit                                             #
# ------------------------------------------------------------------ #

def test_edit_expense_get_requires_login(client, demo_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]

    response = client.get(f"/expenses/{expense_id}/edit")

    assert response.status_code == 302
    assert _redirect_path(response) == "/login"
    assert not urlsplit(response.headers["Location"]).query, \
        "spec forbids a next/return-to parameter"


def test_edit_expense_get_prefills_form(client, blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    _sign_in(client, blank_user_id)

    response = client.get(f"/expenses/{expense_id}/edit")
    body = response.get_data(as_text=True)
    inputs = _inputs(body)
    options = _options(body)

    assert response.status_code == 200
    assert "Edit expense — Spendly" in body
    assert 'method="POST"' in body
    assert f'action="/expenses/{expense_id}/edit"' in body

    assert 'value="12.50"' in inputs["amount"], "amount renders at 2 dp"
    assert 'step="0.01"' in inputs["amount"]
    assert "required" in inputs["amount"]
    assert 'value="2026-03-21"' in inputs["date"]
    assert 'value="Coffee"' in inputs["description"]
    assert "Save Changes" in body

    assert set(options) == set(CATEGORIES)
    assert [value for value, selected in options.items() if selected] == \
        ["Bills"], "exactly the stored category must be pre-selected"


def test_edit_expense_get_other_users_row_is_404(client, demo_user_id,
                                                 blank_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]
    _sign_in(client, blank_user_id)

    assert client.get(f"/expenses/{expense_id}/edit").status_code == 404


def test_edit_expense_get_missing_id_is_404(client, demo_user_id):
    _sign_in(client, demo_user_id)

    assert client.get(f"/expenses/{MISSING_ID}/edit").status_code == 404


def test_edit_expense_get_non_integer_id_is_404(client, demo_user_id):
    _sign_in(client, demo_user_id)

    assert client.get("/expenses/abc/edit").status_code == 404


# ------------------------------------------------------------------ #
# POST /expenses/<id>/edit                                            #
# ------------------------------------------------------------------ #

def test_edit_expense_post_requires_login(client, blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    before = _row(expense_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form())

    assert response.status_code == 302
    assert _redirect_path(response) == "/login"
    assert _row(expense_id) == before, \
        "an unauthenticated POST must not write"


def test_edit_expense_post_updates_row_and_redirects(client, blank_user_id,
                                                     demo_user_id):
    expense_id = _seeded_expense(blank_user_id)
    demo_before = _expenses_for(demo_user_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form())

    assert response.status_code == 302
    assert _redirect_path(response) == "/profile", \
        "success must redirect to the bare profile page"

    row = _row(expense_id)
    assert row["user_id"] == blank_user_id
    assert row["amount"] == pytest.approx(99.0)
    assert row["category"] == "Health"
    assert row["date"] == "2026-03-25"
    assert row["description"] == "Edited"
    assert _expenses_for(demo_user_id) == demo_before, \
        "another user's ledger must be untouched"


def test_edit_expense_post_flashes_success(client, blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    _sign_in(client, blank_user_id)

    body = client.post(f"/expenses/{expense_id}/edit", data=_valid_form(),
                       follow_redirects=True).get_data(as_text=True)

    assert SUCCESS_FLASH in body
    assert "Edited" in body, "the new description must show on /profile"
    assert "₹99.00" in body, "amount must render as ₹ with 2 dp"


def test_edit_expense_post_other_users_row_is_404(client, demo_user_id,
                                                  blank_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]
    before = _row(expense_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form())

    assert response.status_code == 404
    assert _row(expense_id) == before


def test_edit_expense_post_missing_id_is_404(client, demo_user_id):
    _sign_in(client, demo_user_id)

    response = client.post(f"/expenses/{MISSING_ID}/edit",
                           data=_valid_form())

    assert response.status_code == 404


def test_edit_expense_post_missing_amount_keeps_submitted_values(
        client, blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    _sign_in(client, blank_user_id)
    form = _valid_form(amount="")
    del form["amount"]  # field absent entirely

    response = client.post(f"/expenses/{expense_id}/edit", data=form)
    body = response.get_data(as_text=True)

    assert response.status_code == 400, "validation failures use 400"
    assert AMOUNT_ERROR in body
    assert _inputs(body)["amount"].count('value=""') == 1, \
        "the submitted amount stays blank"

    # Sticky values must be the submitted ones, not the stored row's.
    assert _options(body)["Health"] is True
    assert 'value="2026-03-25"' in _inputs(body)["date"]
    assert 'value="Edited"' in _inputs(body)["description"]


@pytest.mark.parametrize("amount", ["", "0", "-5", "abc", "nan"])
def test_edit_expense_post_invalid_amount_returns_400(client, blank_user_id,
                                                      amount):
    expense_id = _seeded_expense(blank_user_id)
    before = _row(expense_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form(amount=amount))
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert AMOUNT_ERROR in body
    assert _row(expense_id) == before, "a rejected edit must not write"


def test_edit_expense_post_rounds_amount_to_two_dp(client, blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form(amount="12.344"))

    assert response.status_code == 302
    assert _row(expense_id)["amount"] == pytest.approx(12.34)


def test_edit_expense_post_invalid_category_returns_400(client, blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    before = _row(expense_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form(category="Pets"))
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert CATEGORY_ERROR in body
    assert _row(expense_id) == before
    assert 'value="99.00"' in _inputs(body)["amount"], \
        "the valid submitted amount is sticky"


@pytest.mark.parametrize("value", ["", "20-03-2026", "2026-13-01",
                                   "not-a-date"])
def test_edit_expense_post_invalid_date_returns_400(client, blank_user_id,
                                                    value):
    expense_id = _seeded_expense(blank_user_id)
    before = _row(expense_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form(date=value))
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert DATE_ERROR in body
    assert _row(expense_id) == before


def test_edit_expense_post_normalises_unpadded_date(client, blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form(date="2026-3-5"))

    assert response.status_code == 302
    assert _row(expense_id)["date"] == "2026-03-05", \
        "dates must be zero-padded ISO so TEXT comparison stays correct"


def test_edit_expense_post_blank_description_stores_null(client,
                                                         blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form(description="   "))

    assert response.status_code == 302
    assert _row(expense_id)["description"] is None


def test_edit_expense_post_long_description_returns_400(client,
                                                        blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    before = _row(expense_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/edit",
                           data=_valid_form(description="x" * 201))
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert DESCRIPTION_ERROR in body
    assert _row(expense_id) == before


# ------------------------------------------------------------------ #
# /profile — Actions column                                           #
# ------------------------------------------------------------------ #

def test_profile_rows_link_to_edit_page(client, demo_user_id):
    _sign_in(client, demo_user_id)

    body = client.get("/profile").get_data(as_text=True)

    assert '<th scope="col" class="tx-actions">Actions</th>' in body
    for row in _expenses_for(demo_user_id):
        assert f'/expenses/{row["id"]}/edit' in body, \
            "every listed transaction needs an Edit link"


def test_profile_empty_state_spans_five_columns(client, blank_user_id):
    _sign_in(client, blank_user_id)

    body = client.get("/profile").get_data(as_text=True)

    assert 'colspan="5"' in body, "the empty row must span the Actions column"
