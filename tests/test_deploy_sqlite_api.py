"""Sanity checks for deploy/sqlite_api_support.py (same queries as app server)."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "deploy"))

import sqlite_api_support as sq  # noqa: E402

DB_PATH = REPO_ROOT / "app" / "fellows.db"


@pytest.mark.skipif(not DB_PATH.is_file(), reason="app/fellows.db not built")
def test_deploy_sqlite_helpers_match_app_db():
    conn = sq.connect(DB_PATH)
    assert conn is not None
    try:
        lst = sq.get_fellows_list(conn)
        assert len(lst) >= 1
        assert "slug" in lst[0]
        full = sq.get_all_fellows(conn)
        assert len(full) == len(lst)
        one = sq.get_fellow_by_slug_or_id(conn, lst[0]["slug"])
        assert one and one.get("slug") == lst[0]["slug"]
        stats = sq.get_stats(conn)
        assert stats["total"] >= 1
        hits = sq.search_fellows(conn, "a")
        assert isinstance(hits, list)
    finally:
        conn.close()
