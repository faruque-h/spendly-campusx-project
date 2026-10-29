import os
import re
import sqlite3

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

app = Flask(__name__)

# Flash/session signing key. Set SPENDLY_SECRET_KEY in production; the
# fallback is for local development only.
app.config["SECRET_KEY"] = os.environ.get("SPENDLY_SECRET_KEY", "dev-only-change-me")

# Simple, deliberately permissive email shape: local@domain.tld
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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


# Step 4 placeholder data — mirrors SEED_EXPENSES in database/db.py so the
# page matches the demo account. Replaced by per-user queries in Step 5.
PROFILE_TRANSACTIONS = [
    {"date": "21 Oct 2026", "description": "Electricity bill", "category": "Bills", "amount": 60.00},
    {"date": "20 Oct 2026", "description": "New backpack", "category": "Shopping", "amount": 45.30},
    {"date": "18 Oct 2026", "description": "Pharmacy purchase", "category": "Health", "amount": 25.40},
    {"date": "16 Oct 2026", "description": "Lunch at the campus cafe", "category": "Food", "amount": 12.50},
    {"date": "14 Oct 2026", "description": "Streaming subscription", "category": "Entertainment", "amount": 15.99},
    {"date": "11 Oct 2026", "description": "Misc. stationery", "category": "Other", "amount": 8.00},
    {"date": "07 Oct 2026", "description": "Coffee and snacks", "category": "Food", "amount": 9.25},
    {"date": "03 Oct 2026", "description": "Bus fare", "category": "Transport", "amount": 3.75},
]

PROFILE_CATEGORY_TOTALS = [
    ("Bills", 60.00),
    ("Shopping", 45.30),
    ("Health", 25.40),
    ("Food", 21.75),
    ("Entertainment", 15.99),
    ("Other", 8.00),
    ("Transport", 3.75),
]


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

    total_spent = round(sum(t["amount"] for t in PROFILE_TRANSACTIONS), 2)
    summary = {
        "total_spent": total_spent,
        "transaction_count": len(PROFILE_TRANSACTIONS),
        "top_category": max(PROFILE_CATEGORY_TOTALS, key=lambda item: item[1])[0],
    }
    categories = [
        {
            "name": name,
            "total": amount,
            "percent": round(amount / total_spent * 100, 1),
        }
        for name, amount in PROFILE_CATEGORY_TOTALS
    ]

    return render_template(
        "profile.html",
        summary=summary,
        transactions=PROFILE_TRANSACTIONS,
        categories=categories,
        member_since="March 2024",
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
    app.run(debug=True, port=5001)
