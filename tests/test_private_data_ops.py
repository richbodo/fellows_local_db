"""Unit tests for the Private Data Ops MCP server.

These call the underlying tool functions directly (not through the MCP
protocol) against a temp relationships.db plus the live ``app/fellows.db``.

Skips when the ``mcp`` SDK isn't installed, since the server module imports
it at module load time. Run via ``just test-private-data-ops`` (which uses
``mcp_servers/.venv``) or any venv with ``mcp`` available.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("mcp")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FELLOWS_DB = REPO_ROOT / "app" / "fellows.db"

if not FELLOWS_DB.is_file():
    pytest.skip(
        f"fellows.db not found at {FELLOWS_DB}. Run: just db-rebuild",
        allow_module_level=True,
    )

from app.relationships import bootstrap_schema  # noqa: E402
import mcp_servers.private_data_ops as srv  # noqa: E402


def _unwrap(tool):
    """Get the plain callable behind a FastMCP-decorated tool object."""
    return tool.fn if hasattr(tool, "fn") else tool


@pytest.fixture
def fixture_db(tmp_path):
    """Build a temp relationships.db with two groups and a few members.

    Members are drawn from the live fellows.db so the cross-DB join in
    get_group_members has something real to match. We pick the first three
    fellows by name — they'll be the same on every run for a given DB build.
    """
    rel = tmp_path / "relationships.db"
    conn = sqlite3.connect(rel)
    conn.row_factory = sqlite3.Row
    bootstrap_schema(conn)

    fconn = sqlite3.connect(FELLOWS_DB)
    fconn.row_factory = sqlite3.Row
    fellow_ids = [
        r["record_id"]
        for r in fconn.execute(
            "SELECT record_id FROM fellows ORDER BY name ASC LIMIT 3"
        ).fetchall()
    ]
    fconn.close()
    assert len(fellow_ids) == 3, "fellows.db must have at least 3 rows for tests"

    now = "2026-05-14T10:00:00Z"
    conn.execute(
        "INSERT INTO groups(id, name, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (1, "Climate Action Group", "Test group for climate", now, now),
    )
    conn.execute(
        "INSERT INTO groups(id, name, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (2, "Auckland Meetup", "", now, "2026-05-13T10:00:00Z"),
    )
    # Climate group: 2 members; Auckland: 1 member; plus 1 orphan to test the
    # left-join branch (record_id not in fellows.db).
    conn.executemany(
        "INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)",
        [
            (1, fellow_ids[0]),
            (1, fellow_ids[1]),
            (1, "orphan-record-id-does-not-exist"),
            (2, fellow_ids[2]),
        ],
    )
    conn.commit()
    conn.close()
    return rel


@pytest.fixture(autouse=True)
def _set_db_paths(fixture_db):
    prev_rel = srv._REL_DB_PATH
    prev_fel = srv._FELLOWS_DB_PATH
    srv._REL_DB_PATH = fixture_db
    srv._FELLOWS_DB_PATH = FELLOWS_DB
    yield
    srv._REL_DB_PATH = prev_rel
    srv._FELLOWS_DB_PATH = prev_fel


def test_list_groups_returns_both_newest_first():
    out = _unwrap(srv.list_groups)()
    assert out["total"] == 2
    assert [g["name"] for g in out["results"]] == ["Climate Action Group", "Auckland Meetup"]
    climate = out["results"][0]
    assert climate["group_id"] == 1
    assert climate["member_count"] == 3
    assert climate["note"] == "Test group for climate"


def test_list_groups_respects_limit():
    out = _unwrap(srv.list_groups)(limit=1)
    assert out["total"] == 2          # pre-limit total
    assert len(out["results"]) == 1
    assert out["results"][0]["name"] == "Climate Action Group"


def test_find_group_case_insensitive_substring():
    out = _unwrap(srv.find_group)("climate")
    assert out["query"] == "climate"
    assert out["total"] == 1
    assert out["results"][0]["name"] == "Climate Action Group"

    out2 = _unwrap(srv.find_group)("CLIMATE")
    assert out2["total"] == 1


def test_find_group_empty_query_short_circuits():
    assert _unwrap(srv.find_group)("") == {"query": "", "total": 0, "results": []}
    assert _unwrap(srv.find_group)("   ")["results"] == []


def test_find_group_no_match():
    out = _unwrap(srv.find_group)("nonexistent")
    assert out["total"] == 0
    assert out["results"] == []


def test_get_group_members_joins_fellows():
    out = _unwrap(srv.get_group_members)(1)
    assert out is not None
    assert out["group"]["name"] == "Climate Action Group"
    assert out["group"]["member_count"] == 3
    members = out["members"]
    assert len(members) == 3
    # Two members resolve from fellows.db, one is orphan.
    resolved = [m for m in members if m["name"] is not None]
    orphans = [m for m in members if m["name"] is None]
    assert len(resolved) == 2
    assert len(orphans) == 1
    assert orphans[0]["record_id"] == "orphan-record-id-does-not-exist"
    assert orphans[0]["contact_email"] is None
    # Resolved members carry the joined fields.
    for m in resolved:
        assert set(m.keys()) == {
            "record_id", "slug", "name",
            "contact_email", "fellow_type", "currently_based_in",
        }


def test_get_group_members_unknown_returns_none():
    assert _unwrap(srv.get_group_members)(99999) is None


def test_read_only_enforcement():
    """A write against either DB must raise OperationalError."""
    conn = srv._open_ro()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO groups(id, name, note, created_at, updated_at) VALUES (3, 'x', '', 'now', 'now')")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM f.fellows WHERE 1=1")
    finally:
        conn.close()
