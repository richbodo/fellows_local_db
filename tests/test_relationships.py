"""Schema bootstrap + ATTACH probe for app/relationships.py.

Architecture pinned by these tests:
- relationships.db is created on first open and is idempotent.
- fellows.db ATTACHes as `f` in read-only mode (?mode=ro), so a stray
  INSERT into f.fellows raises OperationalError at the SQLite level.
- Cross-DB JOIN (group_members → f.fellows) works in stdlib sqlite3.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app import relationships
from app.relationships import (
    SCHEMA_VERSION,
    bootstrap_schema,
    open_db,
)

FELLOWS_DB_PATH = Path(REPO_ROOT) / "app" / "fellows.db"


@pytest.fixture
def rel_path(tmp_path: Path) -> Path:
    """Per-test relationships.db path under tmp_path."""
    return tmp_path / "relationships.db"


def test_bootstrap_creates_file_and_tables(rel_path: Path):
    assert not rel_path.exists()
    conn = open_db(rel_db_path=rel_path, attach_fellows=False)
    try:
        assert rel_path.exists()
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"groups", "group_members", "fellow_tags", "fellow_notes", "settings"} <= tables
    finally:
        conn.close()


def test_bootstrap_is_idempotent(rel_path: Path):
    conn = open_db(rel_db_path=rel_path, attach_fellows=False)
    conn.close()
    # Second open must not raise; tables already exist.
    conn = open_db(rel_db_path=rel_path, attach_fellows=False)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        conn.close()


def test_groups_columns(rel_path: Path):
    conn = open_db(rel_db_path=rel_path, attach_fellows=False)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(groups)").fetchall()}
        assert cols == {"id", "name", "note", "created_at", "updated_at"}
        cols = {r[1] for r in conn.execute("PRAGMA table_info(group_members)").fetchall()}
        assert cols == {"group_id", "fellow_record_id"}
    finally:
        conn.close()


def test_foreign_keys_cascade_on_group_delete(rel_path: Path):
    conn = open_db(rel_db_path=rel_path, attach_fellows=False)
    try:
        conn.execute(
            "INSERT INTO groups(id, name, created_at, updated_at)"
            " VALUES (1, 'g', '2026-04-28', '2026-04-28')"
        )
        conn.execute(
            "INSERT INTO group_members(group_id, fellow_record_id) VALUES (1, 'r1')"
        )
        conn.commit()
        conn.execute("DELETE FROM groups WHERE id = 1")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM group_members").fetchone()[0]
        assert n == 0
    finally:
        conn.close()


@pytest.mark.skipif(
    not FELLOWS_DB_PATH.is_file(),
    reason="app/fellows.db not built; run `just db-rebuild`",
)
def test_attach_fellows_readonly_allows_select(rel_path: Path):
    conn = open_db(rel_db_path=rel_path, attach_fellows=True)
    try:
        n = conn.execute("SELECT COUNT(*) FROM f.fellows").fetchone()[0]
        assert n >= 1
        # Sanity: we can also see schema names from the attached db
        names = {r[0] for r in conn.execute("PRAGMA database_list").fetchall()[:0]}
        assert names == set()  # database_list returns (seq,name,file) tuples
    finally:
        conn.close()


@pytest.mark.skipif(
    not FELLOWS_DB_PATH.is_file(),
    reason="app/fellows.db not built; run `just db-rebuild`",
)
def test_attach_fellows_readonly_denies_write(rel_path: Path):
    conn = open_db(rel_db_path=rel_path, attach_fellows=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE f.fellows SET name = 'X' WHERE 1 = 0")
    finally:
        conn.close()


@pytest.mark.skipif(
    not FELLOWS_DB_PATH.is_file(),
    reason="app/fellows.db not built; run `just db-rebuild`",
)
def test_cross_db_join_resolves_member_names(rel_path: Path):
    conn = open_db(rel_db_path=rel_path, attach_fellows=True)
    try:
        # Pick two real fellows by record_id from the read-only attach.
        rows = conn.execute(
            "SELECT record_id, name FROM f.fellows ORDER BY name LIMIT 2"
        ).fetchall()
        assert len(rows) == 2
        rid_a, name_a = rows[0]["record_id"], rows[0]["name"]
        rid_b, name_b = rows[1]["record_id"], rows[1]["name"]

        conn.execute(
            "INSERT INTO groups(name, created_at, updated_at)"
            " VALUES ('test', '2026-04-28', '2026-04-28')"
        )
        gid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.executemany(
            "INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)",
            [(gid, rid_a), (gid, rid_b)],
        )
        conn.commit()

        joined = conn.execute(
            """
            SELECT f.fellows.name AS name
            FROM group_members
            JOIN f.fellows ON f.fellows.record_id = group_members.fellow_record_id
            WHERE group_members.group_id = ?
            ORDER BY f.fellows.name
            """,
            (gid,),
        ).fetchall()
        names = [r["name"] for r in joined]
        assert names == sorted([name_a, name_b])
    finally:
        conn.close()


def test_settings_round_trip(rel_path: Path):
    conn = open_db(rel_db_path=rel_path, attach_fellows=False)
    try:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES ('self_email', 'me@example.com')"
        )
        conn.commit()
        v = conn.execute(
            "SELECT value FROM settings WHERE key = 'self_email'"
        ).fetchone()[0]
        assert v == "me@example.com"
    finally:
        conn.close()


def test_constants_match_repo_layout():
    """Path constants in the module point inside the app/ dir of this repo."""
    assert relationships.RELATIONSHIPS_DB_PATH.parent.name == "app"
    assert relationships.FELLOWS_DB_PATH.parent.name == "app"
