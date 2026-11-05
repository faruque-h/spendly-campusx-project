import pytest

import database.db as db_module


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point every get_db() call at a throwaway database."""
    monkeypatch.setattr(db_module, "DATABASE", tmp_path / "test.db")
    db_module.init_db()
    db_module.seed_db()
    return db_module.DATABASE


@pytest.fixture
def app(temp_db):
    # Import lazily: app.py seeds at import time and must seed the temp DB.
    from app import app as flask_app

    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def demo_user_id(temp_db):
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()
    finally:
        conn.close()
    return row["id"]


@pytest.fixture
def blank_user_id(temp_db):
    """A real user row with no expenses."""
    conn = db_module.get_db()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Blank User", "blank@spendly.com", "x"),
            )
        return cursor.lastrowid
    finally:
        conn.close()
