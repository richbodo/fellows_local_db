"""Unit tests for the Shared Data Ops MCP server.

These call the underlying tool functions directly (not through the MCP
protocol) against the live ``app/fellows.db``. Protocol-level smoke
testing happens separately via an stdio client harness.

Skips when the ``mcp`` SDK isn't installed, since the server module
imports it at module load time. Run via ``just test-shared-data-ops``
(which uses ``mcp_servers/.venv``) or any venv with ``mcp`` available.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Skip the whole module if the MCP SDK isn't available in this venv.
pytest.importorskip("mcp")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DB_PATH = REPO_ROOT / "app" / "fellows.db"

if not DB_PATH.is_file():
    pytest.skip(
        f"fellows.db not found at {DB_PATH}. Run: python build/restore_from_knack_scrapefile.py",
        allow_module_level=True,
    )

import mcp_servers.shared_data_ops as srv  # noqa: E402


def _unwrap(tool):
    """Get the plain callable behind a FastMCP-decorated tool object."""
    return tool.fn if hasattr(tool, "fn") else tool


@pytest.fixture(autouse=True)
def _set_db_path():
    """Point the server at the real DB for every test."""
    prev = srv._DB_PATH
    srv._DB_PATH = DB_PATH
    yield
    srv._DB_PATH = prev


def test_get_directory_stats_matches_db_count():
    stats = _unwrap(srv.get_directory_stats)()
    assert isinstance(stats, dict)
    assert stats["total"] > 0
    import sqlite3
    with sqlite3.connect(DB_PATH) as conn:
        actual = conn.execute("SELECT COUNT(*) FROM fellows").fetchone()[0]
    assert stats["total"] == actual
    for key in ("by_fellow_type", "by_cohort", "by_region", "field_completeness"):
        assert isinstance(stats[key], list)
        assert all("label" in row and "count" in row for row in stats[key])


def test_search_fellows_returns_summary_shape():
    out = _unwrap(srv.search_fellows)("NZ", limit=5)
    assert out["query"] == "NZ"
    assert out["total"] >= 0
    assert len(out["results"]) <= 5
    if out["results"]:
        row = out["results"][0]
        assert set(row.keys()) == {
            "record_id", "slug", "name", "fellow_type", "cohort",
            "currently_based_in", "bio_tagline", "has_contact_email",
        }
        assert isinstance(row["has_contact_email"], bool)


def test_search_fellows_empty_query_short_circuits():
    out = _unwrap(srv.search_fellows)("", limit=10)
    assert out == {"query": "", "total": 0, "results": []}
    out = _unwrap(srv.search_fellows)("   ", limit=10)
    assert out["results"] == []


def test_search_fellows_caps_limit():
    out = _unwrap(srv.search_fellows)("a*", limit=10_000)
    assert len(out["results"]) <= srv.SEARCH_LIMIT_MAX


def test_get_fellow_returns_null_for_unknown():
    assert _unwrap(srv.get_fellow)("definitely-not-a-real-slug-xyz") is None
    assert _unwrap(srv.get_fellow)("") is None


def test_get_fellow_returns_full_record():
    # Pick a known fellow from the directory via list_fellows.
    listing = _unwrap(srv.list_fellows)(limit=1)
    assert listing["results"], "directory is empty; can't run get_fellow round-trip"
    slug = listing["results"][0]["slug"]
    fellow = _unwrap(srv.get_fellow)(slug)
    assert fellow is not None
    assert fellow["slug"] == slug
    # Full shape: should include columns that SummaryFellow strips.
    assert "primary_citizenship" in fellow
    assert "fellow_status" in fellow


def test_list_fellows_filter_matches_stats():
    """A filtered list's total should match the stats-page aggregate for that filter."""
    stats = _unwrap(srv.get_directory_stats)()
    if not stats["by_fellow_type"]:
        pytest.skip("no fellow_type values to test against")
    first = stats["by_fellow_type"][0]
    out = _unwrap(srv.list_fellows)(fellow_type=first["label"], limit=5)
    assert out["total"] == first["count"]
    assert out["filters_applied"] == {"fellow_type": first["label"]}
    assert len(out["results"]) <= 5


def test_list_fellows_has_contact_email_filter():
    """has_contact_email True/False/None should partition the directory."""
    total_all = _unwrap(srv.list_fellows)(limit=1)["total"]
    total_yes = _unwrap(srv.list_fellows)(has_contact_email=True, limit=1)["total"]
    total_no = _unwrap(srv.list_fellows)(has_contact_email=False, limit=1)["total"]
    assert total_yes + total_no == total_all


def test_list_fellows_pagination():
    page1 = _unwrap(srv.list_fellows)(limit=3, offset=0)
    page2 = _unwrap(srv.list_fellows)(limit=3, offset=3)
    assert page1["total"] == page2["total"]
    slugs1 = [r["slug"] for r in page1["results"]]
    slugs2 = [r["slug"] for r in page2["results"]]
    assert not set(slugs1) & set(slugs2)  # no overlap


def test_list_fellows_caps_limit():
    out = _unwrap(srv.list_fellows)(limit=10_000)
    assert out["limit"] == srv.LIST_LIMIT_MAX
    assert len(out["results"]) <= srv.LIST_LIMIT_MAX


def test_list_fellows_region_substring_match():
    """region filter is substring against the comma-separated column."""
    stats = _unwrap(srv.get_directory_stats)()
    if not stats["by_region"]:
        pytest.skip("no region values to test against")
    region = stats["by_region"][0]["label"]
    out = _unwrap(srv.list_fellows)(region=region, limit=1)
    assert out["total"] >= 1
    assert out["filters_applied"] == {"region": region}


def test_resolve_db_path_priority(monkeypatch, tmp_path):
    """--db beats env var; env beats default."""
    fake = tmp_path / "x.db"
    monkeypatch.setenv("FELLOWS_DB_PATH", str(fake))
    assert srv._resolve_db_path("/cli/path/y.db") == Path("/cli/path/y.db").resolve()
    assert srv._resolve_db_path(None) == fake.resolve()
    monkeypatch.delenv("FELLOWS_DB_PATH")
    assert srv._resolve_db_path(None) == (REPO_ROOT / "app" / "fellows.db").resolve()
