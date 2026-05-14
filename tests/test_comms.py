"""Unit tests for the Communications MCP server.

Calls the underlying tool functions directly (not through the MCP protocol).
Skips when the ``mcp`` SDK isn't installed, since the server module imports
it at module load time. Run via ``just test-comms`` (which uses
``mcp_servers/.venv``) or any venv with ``mcp`` available.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

import pytest

pytest.importorskip("mcp")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import mcp_servers.comms as srv  # noqa: E402


def _unwrap(tool):
    return tool.fn if hasattr(tool, "fn") else tool


@pytest.fixture(autouse=True)
def _clear_staging():
    """Each test starts with an empty staging table."""
    with srv._STAGED_LOCK:
        srv._STAGED.clear()
    yield


def _parse_mailto(url):
    """Pull recipients + headers out of a mailto: URL."""
    assert url.startswith("mailto:")
    parsed = urlparse(url)
    path = parsed.path
    to = [unquote(a) for a in path.split(",") if a]
    qs = parse_qs(parsed.query, keep_blank_values=True)
    return to, qs


def test_stage_email_basic_to():
    out = _unwrap(srv.stage_email)(
        subject="hi",
        body="hello there",
        to=["a@example.com"],
    )
    assert "staging_id" in out and out["staging_id"]
    assert out["preview"]["recipients"]["total"] == 1
    to, qs = _parse_mailto(out["mailto_url"])
    assert to == ["a@example.com"]
    assert qs["subject"] == ["hi"]
    assert qs["body"] == ["hello there"]


def test_stage_email_bcc_group_send():
    out = _unwrap(srv.stage_email)(
        subject="Meet Thursday",
        body="Hi all, come to the meetup",
        bcc=["a@example.com", "b@example.com", "c@example.com"],
    )
    to, qs = _parse_mailto(out["mailto_url"])
    assert to == []
    assert qs["bcc"][0] == "a@example.com,b@example.com,c@example.com"
    assert out["preview"]["recipients"]["bcc"] == ["a@example.com", "b@example.com", "c@example.com"]
    assert out["preview"]["recipients"]["total"] == 3
    # No "multiple recipients in to:" warning since none are in to.
    assert not any("Multiple recipients in `to`" in w for w in out["warnings"])


def test_stage_email_dedupes_case_insensitive():
    out = _unwrap(srv.stage_email)(
        subject="x", body="y",
        bcc=["A@Example.com", "a@example.com", "  ", "B@example.com", "b@EXAMPLE.com"],
    )
    bcc = out["preview"]["recipients"]["bcc"]
    # Originals preserved, dedupe by lowercase.
    assert bcc == ["A@Example.com", "B@example.com"]


def test_stage_email_warns_on_no_recipients():
    out = _unwrap(srv.stage_email)(subject="oops", body="b")
    assert out["preview"]["recipients"]["total"] == 0
    assert any("No recipients" in w for w in out["warnings"])


def test_stage_email_warns_on_multiple_to():
    out = _unwrap(srv.stage_email)(
        subject="x", body="y",
        to=["a@example.com", "b@example.com"],
    )
    assert any("Multiple recipients in `to`" in w for w in out["warnings"])


def test_stage_email_warns_on_long_url():
    big_body = "x" * (srv.MAILTO_URL_WARN_BYTES + 500)
    out = _unwrap(srv.stage_email)(
        subject="x", body=big_body, to=["a@example.com"]
    )
    assert out["preview"]["url_byte_length"] > srv.MAILTO_URL_WARN_BYTES
    assert any("URL is" in w and "bytes" in w for w in out["warnings"])


def test_stage_email_url_encodes_special_chars():
    out = _unwrap(srv.stage_email)(
        subject="Re: hi & bye",
        body="line one\nline two",
        to=["a@example.com"],
    )
    # The URL must round-trip cleanly via standard parsing.
    to, qs = _parse_mailto(out["mailto_url"])
    assert to == ["a@example.com"]
    assert qs["subject"] == ["Re: hi & bye"]
    assert qs["body"] == ["line one\nline two"]


def test_get_staged_round_trips():
    out = _unwrap(srv.stage_email)(
        subject="x", body="y", to=["a@example.com"]
    )
    sid = out["staging_id"]
    fetched = _unwrap(srv.get_staged)(sid)
    assert fetched is not None
    assert fetched["staging_id"] == sid
    assert fetched["mailto_url"] == out["mailto_url"]
    assert fetched["preview"] == out["preview"]


def test_get_staged_unknown_returns_none():
    assert _unwrap(srv.get_staged)("definitely-not-real") is None
    assert _unwrap(srv.get_staged)("") is None


def test_staging_eviction_at_cap():
    """Past _STAGED_MAX inserts, the oldest record is evicted."""
    saved = srv._STAGED_MAX
    try:
        srv._STAGED_MAX = 3
        a = _unwrap(srv.stage_email)(subject="1", body="b", to=["a@e.com"])["staging_id"]
        _unwrap(srv.stage_email)(subject="2", body="b", to=["a@e.com"])
        _unwrap(srv.stage_email)(subject="3", body="b", to=["a@e.com"])
        _unwrap(srv.stage_email)(subject="4", body="b", to=["a@e.com"])
        # `a` should be gone (oldest evicted when the 4th was inserted).
        assert _unwrap(srv.get_staged)(a) is None
        assert len(srv._STAGED) == 3
    finally:
        srv._STAGED_MAX = saved
