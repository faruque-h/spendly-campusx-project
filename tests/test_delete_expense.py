"""Tests for the Step 9 delete-expense flow (app.py + database/queries.py).

Contract: .pi/specs/09-delete-expense.md

Importing `app` seeds the database, so it only happens through the `temp_db`
fixture. Delete is a single owned statement: `rowcount == 0` means missing or
foreign, and the route turns that into a 404.
"""

from urllib.parse import urlsplit

import database.db as db_module
from database.queries import insert_expense, remove_expense

SUCCESS_FLASH = "Expense deleted."
MISSING_ID = 999999

_COLUMNS = "id, user_id, amount, category, date, description"


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


def _row(expense_id):
    """A single expense as a plain dict, or None when it is gone."""
    conn = db_module.get_db()
    try:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


def _expenses_for(user_id):
    conn = db_module.get_db()
    try:
        return conn.execute(
            f"SELECT {_COLUMNS} FROM expenses WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


def _user_exists(user_id):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT 1 FROM users WHERE id = ?", (user_id,)
        ).fetchone() is not None
    finally:
        conn.close()


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


def _other_user_expense():
    """Second user owning one expense; returns (user_id, expense_id)."""
    conn = db_module.get_db()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Other User", "other@spendly.com", "x"),
            )
            user_id = cursor.lastrowid
            cursor = conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, 7.0, "Other", "2026-03-01", "Someone else's"),
            )
        return user_id, cursor.lastrowid
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Query helper                                                        #
# ------------------------------------------------------------------ #

def test_remove_expense_deletes_owned_row(demo_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]

    assert remove_expense(expense_id, demo_user_id) == 1
    assert _row(expense_id) is None


def test_remove_expense_wrong_user_deletes_nothing(demo_user_id, blank_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]
    before = _row(expense_id)

    assert remove_expense(expense_id, blank_user_id) == 0
    assert _row(expense_id) == before, "a foreign delete must not change the row"


def test_remove_expense_missing_id_returns_zero(blank_user_id):
    assert remove_expense(MISSING_ID, blank_user_id) == 0


def test_remove_expense_leaves_siblings_and_user_intact(blank_user_id):
    kept_id = _seeded_expense(blank_user_id, description="Keep me")
    deleted_id = _seeded_expense(blank_user_id, description="Delete me")

    assert remove_expense(deleted_id, blank_user_id) == 1
    assert _row(deleted_id) is None
    assert _row(kept_id) is not None, "other rows must survive"
    assert _user_exists(blank_user_id), "the user must survive"


# ------------------------------------------------------------------ #
# POST /expenses/<id>/delete                                           #
# ------------------------------------------------------------------ #

def test_delete_expense_post_unauthenticated_redirects(client, demo_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]

    response = client.post(f"/expenses/{expense_id}/delete")

    assert response.status_code == 302
    assert _redirect_path(response) == "/login"
    assert _row(expense_id) is not None, "nothing may be deleted while signed out"


def test_delete_expense_post_stale_session_redirects(client, demo_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]
    _sign_in(client, MISSING_ID)

    response = client.post(f"/expenses/{expense_id}/delete")

    assert response.status_code == 302
    assert _redirect_path(response) == "/login"
    assert _row(expense_id) is not None


def test_delete_expense_post_own_row_redirects_to_profile(client,
                                                          blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/delete")

    assert response.status_code == 302
    assert _redirect_path(response) == "/profile"
    assert _row(expense_id) is None


def test_delete_expense_post_own_row_leaves_other_users_alone(client,
                                                              demo_user_id,
                                                              blank_user_id):
    expense_id = _seeded_expense(blank_user_id)
    demo_before = [dict(row) for row in _expenses_for(demo_user_id)]
    _sign_in(client, blank_user_id)

    client.post(f"/expenses/{expense_id}/delete")

    assert [dict(row) for row in _expenses_for(demo_user_id)] == demo_before


def test_delete_expense_post_flashes_success(client, blank_user_id):
    expense_id = _seeded_expense(blank_user_id, amount=432.10,
                                 description="Delete me")
    _sign_in(client, blank_user_id)

    body = client.post(f"/expenses/{expense_id}/delete",
                       follow_redirects=True).get_data(as_text=True)

    assert SUCCESS_FLASH in body
    assert "Delete me" not in body, "the deleted row must not be listed"
    assert "₹432.10" not in body, "the deleted amount must not be listed"


def test_delete_expense_post_other_users_row_is_404(client, demo_user_id,
                                                    blank_user_id):
    expense_id = _other_user_expense()[1]
    before = _row(expense_id)
    _sign_in(client, blank_user_id)

    response = client.post(f"/expenses/{expense_id}/delete")

    assert response.status_code == 404
    assert _row(expense_id) == before


def test_delete_expense_post_missing_id_is_404(client, demo_user_id):
    _sign_in(client, demo_user_id)

    assert client.post(f"/expenses/{MISSING_ID}/delete").status_code == 404


def test_delete_expense_post_non_integer_id_is_404(client, demo_user_id):
    _sign_in(client, demo_user_id)

    assert client.post("/expenses/abc/delete").status_code == 404


# ------------------------------------------------------------------ #
# GET must be rejected                                                #
# ------------------------------------------------------------------ #

def test_delete_expense_get_unauthenticated_is_405(client, demo_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]

    response = client.get(f"/expenses/{expense_id}/delete")

    assert response.status_code == 405
    assert _row(expense_id) is not None


def test_delete_expense_get_authenticated_is_405(client, demo_user_id):
    expense_id = _expenses_for(demo_user_id)[0]["id"]
    _sign_in(client, demo_user_id)

    response = client.get(f"/expenses/{expense_id}/delete")

    assert response.status_code == 405
    assert "POST" in response.headers["Allow"]
    assert _row(expense_id) is not None


# ------------------------------------------------------------------ #
# /profile markup                                                     #
# ------------------------------------------------------------------ #

def test_profile_rows_render_delete_form(client, demo_user_id):
    _sign_in(client, demo_user_id)

    body = client.get("/profile").get_data(as_text=True)

    for row in _expenses_for(demo_user_id):
        assert f'action="/expenses/{row["id"]}/delete"' in body
    assert 'method="POST"' in body


def test_profile_rows_show_edit_and_delete(client, demo_user_id):
    _sign_in(client, demo_user_id)

    body = client.get("/profile").get_data(as_text=True)

    for row in _expenses_for(demo_user_id):
        assert f'/expenses/{row["id"]}/edit' in body, \
            "every listed transaction needs an Edit link"
        assert f'/expenses/{row["id"]}/delete' in body, \
            "every listed transaction needs a Delete form"


def test_profile_delete_button_has_unique_label(client, demo_user_id):
    _sign_in(client, demo_user_id)

    body = client.get("/profile").get_data(as_text=True)

    for row in _expenses_for(demo_user_id):
        assert (f'aria-label="Delete {row["category"]} expense of '
                f'₹{row["amount"]:.2f}') in body


def test_profile_empty_state_spans_five_columns(client, blank_user_id):
    _sign_in(client, blank_user_id)

    body = client.get("/profile").get_data(as_text=True)

    assert 'colspan="5"' in body


def test_profile_after_delete_no_longer_lists_expense(client, blank_user_id):
    deleted_id = _seeded_expense(blank_user_id, description="Gone")
    kept_id = _seeded_expense(blank_user_id, description="Kept")
    _sign_in(client, blank_user_id)

    client.post(f"/expenses/{deleted_id}/delete")
    body = client.get("/profile").get_data(as_text=True)

    assert f"/expenses/{deleted_id}/delete" not in body
    assert "Gone" not in body
    assert f"/expenses/{kept_id}/delete" in body
    assert "Kept" in body
