import os
import re
import sqlite3

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.security import generate_password_hash

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
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
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


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


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
