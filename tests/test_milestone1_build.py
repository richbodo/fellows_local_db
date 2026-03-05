"""
Milestone 1 tests: Build script output (fellows.db).
Run after: python build/import_json_to_sqlite.py
"""
import os
import sqlite3
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO_ROOT, "app", "fellows.db")


@pytest.fixture(scope="module")
def db():
    if not os.path.exists(DB_PATH):
        pytest.skip(
            f"DB not found at {DB_PATH}. Run: python build/import_json_to_sqlite.py"
        )
    conn = sqlite3.connect(DB_PATH)
    yield conn
    conn.close()


def test_fellows_count(db):
    """Should have 442 fellows."""
    cur = db.execute("SELECT COUNT(*) FROM fellows")
    assert cur.fetchone()[0] == 442


def test_fellows_has_slug_and_name(db):
    """Should have name and slug columns with expected sample."""
    cur = db.execute(
        "SELECT name, slug FROM fellows WHERE name IS NOT NULL AND name != '' ORDER BY name LIMIT 3"
    )
    rows = cur.fetchall()
    assert len(rows) >= 3
    names = [r[0] for r in rows]
    slugs = [r[1] for r in rows]
    assert "Aaron Bird" in names
    assert "aaron_bird" in slugs


def test_fts5_exists_and_matches(db):
    """FTS5 table should exist and return rows for 'Aaron'."""
    cur = db.execute(
        "SELECT name FROM fellows_fts WHERE fellows_fts MATCH 'Aaron'"
    )
    rows = cur.fetchall()
    assert len(rows) >= 1
    names = [r[0] for r in rows]
    assert "Aaron Bird" in names or "Aaron McDonald" in names


def test_aaron_bird_by_slug(db):
    """Lookup by slug aaron_bird returns Aaron Bird."""
    cur = db.execute("SELECT name FROM fellows WHERE slug = 'aaron_bird'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "Aaron Bird"


def test_list_only_query_returns_minimal_columns(db):
    """List-only endpoint uses SELECT record_id, slug, name; 442 rows."""
    cur = db.execute("SELECT record_id, slug, name FROM fellows ORDER BY name")
    rows = cur.fetchall()
    assert len(rows) == 442
    assert len(rows[0]) == 3
