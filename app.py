import math
import os
import re
import sqlite3
from datetime import date, datetime

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import CATEGORIES, get_db, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    insert_expense,
    update_expense,
)

app = Flask(__name__)

# Flash/session signing key. Set SPENDLY_SECRET_KEY in production; the
# fallback is for local development only.
app.config["SECRET_KEY"] = os.environ.get("SPENDLY_SECRET_KEY", "dev-only-change-me")
# Secure cookies need HTTPS, so they stay opt-in for local development.
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("SPENDLY_SECURE_COOKIES") == "1":
    app.config["SESSION_COOKIE_SECURE"] = True

# Simple, deliberately permissive email shape: local@domain.tld
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ------------------------------------------------------------------ #
# Date filter helpers                                                 #
# ------------------------------------------------------------------ #

# Presets: key, label, and how many months back the window starts.
PROFILE_PRESETS = (
    ("this_month", "This Month", 0),
    ("last_3_months", "Last 3 Months", 2),
    ("last_6_months", "Last 6 Months", 5),
)


def _parse_iso_date(value):
    """Normalise 'YYYY-MM-DD' to canonical ISO; None when missing or invalid.

    strptime accepts unpadded input ('2026-1-5') but SQLite compares the TEXT
    `date` column lexicographically, so only zero-padded values may reach SQL.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _month_start(day, months_back=0):
    """First day of the month `months_back` months before `day`'s month."""
    total = day.year * 12 + day.month - 1 - months_back
    year, month = divmod(total, 12)
    return date(year, month + 1, 1).isoformat()


def _build_presets(today, date_from, date_to):
    """Preset windows for the filter bar, each annotated with `active`."""
    presets = [
        {
            "key": key,
            "label": label,
            "date_from": _month_start(today, months_back),
            "date_to": today.isoformat(),
        }
        for key, label, months_back in PROFILE_PRESETS
    ]
    presets.append({"key": "all_time", "label": "All Time",
                    "date_from": None, "date_to": None})
    for preset in presets:
        preset["active"] = (preset["date_from"] == date_from
                            and preset["date_to"] == date_to)
    return presets


# ------------------------------------------------------------------ #
# Expense form helpers                                                #
# ------------------------------------------------------------------ #

def _parse_expense_form(form_data):
    """Normalise + validate the add/edit expense form.

    Returns (sticky fields, error-or-None, amount, iso_date). `amount` and
    `iso_date` are only meaningful when `error` is None.
    """
    form = {
        "amount": (form_data.get("amount") or "").strip(),
        "category": form_data.get("category") or "",
        "date": (form_data.get("date") or "").strip(),
        "description": (form_data.get("description") or "").strip(),
    }

    # Normalise before validating: round(0.004, 2) is 0.0, so validating the
    # raw value would let a sub-cent amount through as zero. float() also
    # parses 'nan' and 'inf', so the checks below guard them.
    amount = None
    try:
        amount = round(float(form["amount"]), 2)
    except ValueError:
        pass  # unparsable; the None check below reports it

    iso_date = _parse_iso_date(form["date"])

    error = None
    if amount is None or not math.isfinite(amount) or amount <= 0:
        error = "Please enter an amount greater than 0."
    elif form["category"] not in CATEGORIES:
        error = "Please choose a valid category."
    elif iso_date is None:
        error = "Please enter a valid date (YYYY-MM-DD)."
    elif len(form["description"]) > 200:
        error = "Description must be 200 characters or fewer."

    if error is not None:
        return form, error, None, None
    return form, error, amount, iso_date


# Ensure the database and demo data exist before any route is used.
with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Template globals                                                    #
# ------------------------------------------------------------------ #

@app.context_processor
def inject_current_user():
    """Expose the signed-in user to every template as `current_user`."""
    user_id = session.get("user_id")
    if user_id is None:
        return {"current_user": None}

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        # Stale cookie for a user that no longer exists: treat as anonymous.
        session.clear()
        return {"current_user": None}

    return {"current_user": {"id": row["id"], "name": row["name"],
                             "email": row["email"]}}


@app.template_filter("display_date")
def display_date(value):
    """'2026-10-21' -> '21 Oct 2026'; pass anything unparseable through."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return value


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Signed-in users have no reason to see the sign-up form.
    if session.get("user_id") is not None:
        return redirect(url_for("landing"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""  # never strip passwords

        error = None
        if not name:
            error = "Please enter your name."
        elif not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."

        if error is None:
            conn = get_db()
            try:
                existing = conn.execute(
                    "SELECT 1 FROM users WHERE lower(email) = ?", (email,)
                ).fetchone()

                if existing is not None:
                    error = "An account with this email already exists."
                else:
                    try:
                        with conn:  # commits on success, rolls back on error
                            conn.execute(
                                "INSERT INTO users (name, email, password_hash) "
                                "VALUES (?, ?, ?)",
                                (name, email, generate_password_hash(password)),
                            )
                    except sqlite3.IntegrityError:
                        error = "An account with this email already exists."
                    else:
                        flash("Account created successfully. Please sign in.",
                              "success")
                        return redirect(url_for("login"))
            finally:
                conn.close()

        # Validation / duplicate failure: 400 with sticky fields.
        return render_template("register.html", error=error,
                               name=name, email=email), 400

    return render_template("register.html", name="", email="")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET" and session.get("user_id") is not None:
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""  # never strip passwords

        if not email or not password:
            return render_template(
                "login.html", email=email,
                error="Please enter your email and password.",
            ), 400

        conn = get_db()
        try:
            user = conn.execute(
                "SELECT id, name, password_hash FROM users "
                "WHERE lower(email) = ?",
                (email,),
            ).fetchone()
        finally:
            conn.close()

        verified = False
        if user is not None:
            try:
                verified = check_password_hash(user["password_hash"], password)
            except ValueError:
                # Malformed/unsupported stored hash — treat as a mismatch.
                verified = False

        if not verified:
            return render_template("login.html", email=email,
                                   error="Invalid email or password."), 401

        session.clear()
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user['name']}.", "success")
        return redirect(url_for("profile"))

    return render_template("login.html", email="")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    if user is None:
        # Stale session for a user that no longer exists.
        session.clear()
        flash("Please sign in again.", "error")
        return redirect(url_for("login"))

    date_from = _parse_iso_date(request.args.get("date_from"))
    date_to = _parse_iso_date(request.args.get("date_to"))

    # An inverted range is a user error: fall back to the unfiltered view.
    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.", "error")
        date_from = date_to = None

    today = date.today()
    return render_template(
        "profile.html",
        user=user,
        summary=get_summary_stats(user_id, date_from=date_from, date_to=date_to),
        transactions=get_recent_transactions(
            user_id, date_from=date_from, date_to=date_to
        ),
        categories=get_category_breakdown(
            user_id, date_from=date_from, date_to=date_to
        ),
        date_from=date_from,
        date_to=date_to,
        presets=_build_presets(today, date_from, date_to),
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    if get_user_by_id(session["user_id"]) is None:
        # Stale session for a user that no longer exists.
        session.clear()
        flash("Please sign in again.", "error")
        return redirect(url_for("login"))

    # Pre-filled values: blank on GET (date defaults to today), sticky on error.
    form = {
        "amount": "",
        "category": CATEGORIES[0],
        "date": date.today().isoformat(),
        "description": "",
    }

    if request.method == "POST":
        form, error, amount, iso_date = _parse_expense_form(request.form)

        if error is None:
            try:
                insert_expense(
                    session["user_id"],
                    amount,
                    form["category"],
                    iso_date,
                    form["description"] or None,
                )
            except sqlite3.IntegrityError:
                # Stale session for a user that no longer exists.
                session.clear()
                flash("Please sign in again.", "error")
                return redirect(url_for("login"))
            flash("Expense added.", "success")
            return redirect(url_for("profile"))

        return render_template("add_expense.html", categories=CATEGORIES,
                               error=error, **form), 400

    return render_template("add_expense.html", categories=CATEGORIES,
                           error=None, **form)


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    if get_user_by_id(user_id) is None:
        # Stale session for a user that no longer exists.
        session.clear()
        flash("Please sign in again.", "error")
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "POST":
        form, error, amount, iso_date = _parse_expense_form(request.form)
        if error is None:
            changed = update_expense(
                id, user_id, amount, form["category"], iso_date,
                form["description"] or None,
            )
            if changed == 0:
                # Row deleted between the GET and this POST.
                abort(404)
            flash("Expense updated.", "success")
            return redirect(url_for("profile"))

        return render_template("edit_expense.html", categories=CATEGORIES,
                               expense_id=id, error=error, **form), 400

    form = {
        "amount": f"{expense['amount']:.2f}",
        "category": expense["category"],
        "date": expense["date"],
        "description": expense["description"] or "",
    }
    return render_template("edit_expense.html", categories=CATEGORIES,
                           expense_id=id, error=None, **form)


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    # The Werkzeug debugger is an RCE console: opt in explicitly, never default on.
    app.run(debug=os.environ.get("SPENDLY_DEBUG") == "1", port=5001)
