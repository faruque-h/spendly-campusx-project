import os
import re
import sqlite3
from datetime import date, datetime

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
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


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    # The Werkzeug debugger is an RCE console: opt in explicitly, never default on.
    app.run(debug=os.environ.get("SPENDLY_DEBUG") == "1", port=5001)
