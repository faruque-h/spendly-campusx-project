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
        return redirect(url_for("landing"))

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
        return redirect(url_for("landing"))

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


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
