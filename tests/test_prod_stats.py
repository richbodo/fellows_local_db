"""Unit tests for scripts/prod_stats.py.

The script is stdlib-only and lives under scripts/ (not a package), so we
load it by path. Tests exercise the pure functions (``tally``,
``disk_usage``, ``print_human``, ``build_email_hash_index``,
``resolve_recipients``, plus the small ``_entry_*`` helpers) against
synthetic journald entries — no real journalctl or SSH.

Fixtures match what ``journalctl -u fellows-pwa --since … -o json --no-pager``
emits: each entry is a dict with at least ``MESSAGE`` and
``__REALTIME_TIMESTAMP`` (microseconds since the epoch, as a string).
"""
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "prod_stats.py")

_spec = importlib.util.spec_from_file_location("prod_stats", SCRIPT_PATH)
prod_stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prod_stats)


# ---- helpers -------------------------------------------------------------

def _entry(message: str, ts: str = "2026-04-23T10:17:00Z") -> dict:
    """Synthesize a journald entry dict matching `journalctl -o json` output.

    ``ts`` is an ISO-8601 Zulu string for readability; converted to
    microseconds-since-epoch (string) the way real journald serializes
    ``__REALTIME_TIMESTAMP``.
    """
    epoch_us = int(
        datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1_000_000
    )
    return {"MESSAGE": message, "__REALTIME_TIMESTAMP": str(epoch_us)}


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---- fixture: representative journald entries ----------------------------

FIXTURE_ENTRIES = [
    # App-shell loads
    _entry('127.0.0.1 - - [23/Apr/2026 10:15:32] "GET / HTTP/1.1" 200 -'),
    _entry('127.0.0.1 - - [23/Apr/2026 10:15:33] "GET /index.html HTTP/1.1" 200 -'),
    _entry('127.0.0.1 - - [23/Apr/2026 10:16:01] "GET / HTTP/1.1" 304 -'),
    # Directory API (count both list and detail)
    _entry('127.0.0.1 - - [23/Apr/2026 10:15:34] "GET /api/fellows HTTP/1.1" 200 -'),
    _entry('127.0.0.1 - - [23/Apr/2026 10:15:35] "GET /api/fellows?full=1 HTTP/1.1" 200 -'),
    _entry('127.0.0.1 - - [23/Apr/2026 10:16:00] "GET /api/fellows/jane-doe HTTP/1.1" 200 -'),
    # DB downloads
    _entry('127.0.0.1 - - [23/Apr/2026 10:15:36] "GET /fellows.db HTTP/1.1" 200 -'),
    # Magic-link verify: one success, one 401
    _entry('127.0.0.1 - - [23/Apr/2026 10:17:00] "POST /api/verify-token HTTP/1.1" 200 -'),
    _entry('127.0.0.1 - - [23/Apr/2026 10:17:05] "POST /api/verify-token HTTP/1.1" 401 -'),
    # 5xx error (should bucket under errors_5xx)
    _entry('127.0.0.1 - - [23/Apr/2026 10:18:00] "GET /api/stats HTTP/1.1" 500 -'),
    # Send-unlock structured events: two sent (distinct prefixes), one http_error.
    # Distinct timestamps so first/last ordering is testable downstream.
    _entry(
        json.dumps({"event": "send_unlock_email", "result": "sent",
                    "email_hash_prefix": "deadbeef1234", "token_prefix": "aaaaaaaaaaaa",
                    "postmark": {"MessageID": "m1"}}),
        ts="2026-04-23T10:17:00Z",
    ),
    _entry(
        json.dumps({"event": "send_unlock_email", "result": "sent",
                    "email_hash_prefix": "cafebabe5678", "token_prefix": "bbbbbbbbbbbb",
                    "postmark": {"MessageID": "m2"}}),
        ts="2026-04-23T10:17:02Z",
    ),
    _entry(
        json.dumps({"event": "send_unlock_email", "result": "http_error",
                    "email_hash_prefix": "feedface9abc", "token_prefix": "cccccccccccc",
                    "status": 422}),
        ts="2026-04-23T10:17:30Z",
    ),
    # Noise that must not bump any counter
    _entry("Rate limit: send-unlock for hash prefix deadbeef1234"),
    _entry('{"event": "build_meta", "build": {"built_at": "2026-04-23T09:00Z"}}'),
    _entry(""),
    _entry("not-a-log-line at all"),
]


# ---- tally() -------------------------------------------------------------

def test_tally_counts_shell_loads():
    stats = prod_stats.tally(FIXTURE_ENTRIES)
    assert stats["shell_loads"] == 3


def test_tally_counts_directory_api():
    stats = prod_stats.tally(FIXTURE_ENTRIES)
    # list + ?full=1 + detail
    assert stats["api_fellows"] == 3


def test_tally_counts_db_downloads():
    stats = prod_stats.tally(FIXTURE_ENTRIES)
    assert stats["db_downloads"] == 1


def test_tally_counts_magic_link_verifications():
    stats = prod_stats.tally(FIXTURE_ENTRIES)
    assert stats["magic_links_verified"] == 1
    assert stats["magic_links_verify_failed"] == 1


def test_tally_counts_magic_links_sent_and_failures():
    stats = prod_stats.tally(FIXTURE_ENTRIES)
    assert stats["magic_links_sent"] == 2
    assert stats["magic_links_send_failed"] == {"http_error": 1}


def test_tally_bucket_5xx_by_route():
    stats = prod_stats.tally(FIXTURE_ENTRIES)
    assert stats["errors_5xx"] == {"500 GET /api/stats": 1}


def test_tally_buckets_4xx_by_route_and_excludes_5xx():
    """4xx access lines bucket separately from 5xx; verify-token 401 already
    has its own counter (verify_fail) but should still also appear here so
    the operator sees full per-status breakdown."""
    entries = [
        _entry('127.0.0.1 - - [x] "GET /api/fellows/missing HTTP/1.1" 404 -'),
        _entry('127.0.0.1 - - [x] "GET /fellows.db HTTP/1.1" 403 -'),
        _entry('127.0.0.1 - - [x] "GET /api/fellows/missing HTTP/1.1" 404 -'),
        _entry('127.0.0.1 - - [x] "GET /api/stats HTTP/1.1" 500 -'),
    ]
    stats = prod_stats.tally(entries)
    assert stats["errors_4xx"] == {
        "404 GET /api/fellows/missing": 2,
        "403 GET /fellows.db": 1,
    }
    # 5xx still bucketed independently.
    assert stats["errors_5xx"] == {"500 GET /api/stats": 1}


def test_tally_recent_errors_caps_and_orders_newest_first():
    """recent_errors carries the verbatim access line for each 4xx/5xx,
    sorted newest-first and capped at RECENT_ERRORS_CAP. This is what
    `--errors-only` prints to support 'user reported a 404 at 3pm —
    what was it?' triage."""
    msgs = []
    expected_total = prod_stats.RECENT_ERRORS_CAP + 3
    for i in range(expected_total):
        # Increment timestamp so sort order is well-defined.
        ts = f"2026-04-23T10:{i:02d}:00Z"
        msgs.append(_entry(f'127.0.0.1 - - [x] "GET /thing/{i} HTTP/1.1" 404 -', ts=ts))
    # Sprinkle 200s — must NOT show up in recent_errors.
    msgs.append(_entry('127.0.0.1 - - [x] "GET / HTTP/1.1" 200 -',
                       ts="2026-04-23T11:00:00Z"))
    stats = prod_stats.tally(msgs)
    recent = stats["recent_errors"]
    assert len(recent) == prod_stats.RECENT_ERRORS_CAP
    # Newest first: i = expected_total-1 down to expected_total - CAP
    assert "GET /thing/" + str(expected_total - 1) in recent[0]["message"]
    assert recent[0]["status"] == 404
    # All entries must be 4xx/5xx; no 200s
    for r in recent:
        assert r["status"] >= 400
    # Strictly descending ts.
    timestamps = [r["ts"] for r in recent]
    assert timestamps == sorted(timestamps, reverse=True)


def test_tally_recent_errors_empty_when_no_errors():
    entries = [
        _entry('127.0.0.1 - - [x] "GET / HTTP/1.1" 200 -'),
        _entry('127.0.0.1 - - [x] "GET /api/fellows HTTP/1.1" 200 -'),
    ]
    stats = prod_stats.tally(entries)
    assert stats["recent_errors"] == []
    assert stats["errors_4xx"] == {}


def test_tally_ignores_build_meta_and_rate_limit_lines():
    # Inputs that look structured but aren't send_unlock_email must not count.
    entries = [
        _entry('{"event": "build_meta", "build": {"built_at": "x"}}'),
        _entry("Rate limit: send-unlock for hash prefix deadbeef1234"),
    ]
    stats = prod_stats.tally(entries)
    assert stats["magic_links_sent"] == 0
    assert stats["shell_loads"] == 0


def test_tally_empty_input_returns_zeros():
    stats = prod_stats.tally([])
    assert stats["shell_loads"] == 0
    assert stats["magic_links_sent"] == 0
    assert stats["errors_5xx"] == {}
    assert stats["magic_links_send_failed"] == {}
    assert stats["email_events_by_prefix"] == {}


def test_tally_distinguishes_api_fellows_from_api_stats():
    # /api/stats must not be counted as /api/fellows.
    entries = [
        _entry('127.0.0.1 - - [x] "GET /api/stats HTTP/1.1" 200 -'),
        _entry('127.0.0.1 - - [x] "GET /api/fellows HTTP/1.1" 200 -'),
    ]
    stats = prod_stats.tally(entries)
    assert stats["api_fellows"] == 1


# ---- _entry_message + _entry_ts (load-bearing helpers) -------------------

def test_entry_message_returns_string_payload():
    assert prod_stats._entry_message({"MESSAGE": "hello"}) == "hello"


def test_entry_message_skips_byte_array_messages():
    # journalctl emits MESSAGE as a list[int] for non-UTF8 payloads. The
    # fellows-pwa server never emits those, so the helper deliberately
    # skips them rather than trying to decode.
    assert prod_stats._entry_message({"MESSAGE": [104, 105]}) is None


def test_entry_message_handles_missing_key():
    assert prod_stats._entry_message({}) is None


def test_entry_ts_converts_microseconds_to_iso_z():
    # 2026-04-23T10:17:00Z → epoch us
    ts_iso = "2026-04-23T10:17:00Z"
    epoch_us = int(
        datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp() * 1_000_000
    )
    out = prod_stats._entry_ts({"__REALTIME_TIMESTAMP": str(epoch_us)})
    assert out == ts_iso


def test_entry_ts_returns_none_on_missing_or_garbage():
    assert prod_stats._entry_ts({}) is None
    assert prod_stats._entry_ts({"__REALTIME_TIMESTAMP": "not-a-number"}) is None


# ---- tally(): per-prefix send buckets with timestamps -------------------

def test_tally_buckets_send_events_per_prefix_with_timestamps():
    """Two events with the same hash prefix produce a single bucket
    containing both events, each carrying its own timestamp. This is the
    foundation prod-stats-long uses to compute first_ts/last_ts per
    recipient — a regression here would silently break the recipient
    list."""
    entries = [
        _entry(
            json.dumps({"event": "send_unlock_email", "result": "sent",
                        "email_hash_prefix": "abcdef012345"}),
            ts="2026-04-23T10:00:00Z",
        ),
        _entry(
            json.dumps({"event": "send_unlock_email", "result": "sent",
                        "email_hash_prefix": "abcdef012345"}),
            ts="2026-04-23T10:30:00Z",
        ),
        _entry(
            json.dumps({"event": "send_unlock_email", "result": "http_error",
                        "email_hash_prefix": "999999999999"}),
            ts="2026-04-23T11:00:00Z",
        ),
    ]
    stats = prod_stats.tally(entries)
    by_prefix = stats["email_events_by_prefix"]
    assert set(by_prefix.keys()) == {"abcdef012345", "999999999999"}
    same_prefix = by_prefix["abcdef012345"]["events"]
    assert len(same_prefix) == 2
    assert {e["result"] for e in same_prefix} == {"sent"}
    assert {e["ts"] for e in same_prefix} == {
        "2026-04-23T10:00:00Z", "2026-04-23T10:30:00Z",
    }
    other = by_prefix["999999999999"]["events"]
    assert len(other) == 1 and other[0]["result"] == "http_error"


def test_tally_does_not_bucket_http_lines_under_email_events():
    entries = [
        _entry('127.0.0.1 - - [x] "GET /api/fellows HTTP/1.1" 200 -'),
    ]
    stats = prod_stats.tally(entries)
    assert stats["email_events_by_prefix"] == {}


# ---- disk_usage() --------------------------------------------------------

def test_disk_usage_shape():
    disk = prod_stats.disk_usage("/")
    assert set(disk.keys()) == {"path", "total_gib", "used_gib", "free_gib", "pct_used"}
    assert disk["path"] == "/"
    assert disk["total_gib"] > 0
    assert 0.0 <= disk["pct_used"] <= 100.0


# ---- build_email_hash_index() -------------------------------------------

def _make_fellows_db(path, rows):
    """Create a minimal fellows.db at `path` with the columns build_email_hash_index reads."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE fellows ("
            "  record_id TEXT PRIMARY KEY,"
            "  name TEXT,"
            "  contact_email TEXT"
            ")"
        )
        conn.executemany(
            "INSERT INTO fellows (record_id, name, contact_email) VALUES (?,?,?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_build_email_hash_index_joins_emails_to_fellows(tmp_path):
    """Happy path: builds sha256-keyed dict with lowercased+trimmed emails.
    Empty/null emails skipped. Always pass an explicit db_path so a stray
    test never falls back to the production default
    (/opt/fellows/deploy/dist/fellows.db)."""
    db_path = tmp_path / "fellows.db"
    _make_fellows_db(db_path, [
        ("rec_1", "Alice Aardvark", "Alice@Example.com  "),  # mixed case + trailing ws
        ("rec_2", "Bob Brown", "bob@example.com"),
        ("rec_3", "Carol No-Email", ""),                      # skipped (empty)
        ("rec_4", "Dana NULL", None),                          # skipped (NULL)
    ])
    idx = prod_stats.build_email_hash_index(db_path=str(db_path))
    assert len(idx) == 2
    expected_alice_key = _sha256_hex("alice@example.com")
    expected_bob_key = _sha256_hex("bob@example.com")
    assert idx[expected_alice_key] == {"email": "alice@example.com", "name": "Alice Aardvark"}
    assert idx[expected_bob_key] == {"email": "bob@example.com", "name": "Bob Brown"}


def test_build_email_hash_index_returns_empty_on_unopenable_db(tmp_path, capsys):
    """Path under a nonexistent directory: sqlite3.connect raises
    OperationalError; the function catches it and returns {}, plus a
    note on stderr. Don't pass a path that points at a missing file in
    an *existing* directory — sqlite3 silently creates an empty DB
    there, which then crashes on the SELECT (a different code path)."""
    bad_path = tmp_path / "nope" / "fellows.db"  # parent dir doesn't exist
    out = prod_stats.build_email_hash_index(db_path=str(bad_path))
    assert out == {}
    err = capsys.readouterr().err
    assert "Cannot open fellows DB" in err


# ---- resolve_recipients() -----------------------------------------------

def test_resolve_recipients_matches_prefix_and_sorts_newest_first():
    """Recipient row resolution: prefix-prefix match against the hash
    index, accumulated send count + timestamps, sorted newest last_ts
    first. Unmatched prefixes still produce a row with email=None."""
    alice_full = _sha256_hex("alice@example.com")  # 64 hex chars
    bob_full = _sha256_hex("bob@example.com")
    hash_index = {
        alice_full: {"email": "alice@example.com", "name": "Alice"},
        bob_full: {"email": "bob@example.com", "name": "Bob"},
    }
    email_events = {
        alice_full[:12]: {"events": [
            {"ts": "2026-04-23T10:00:00Z", "result": "sent"},
            {"ts": "2026-04-23T10:30:00Z", "result": "sent"},
        ]},
        bob_full[:12]: {"events": [
            {"ts": "2026-04-23T12:00:00Z", "result": "sent"},
        ]},
        "ffffffffffff": {"events": [  # no match
            {"ts": "2026-04-23T11:00:00Z", "result": "http_error"},
        ]},
    }
    rows = prod_stats.resolve_recipients(email_events, hash_index)
    assert len(rows) == 3
    # Sorted by last_ts desc → Bob (12:00), unknown (11:00), Alice (10:30).
    assert rows[0]["email"] == "bob@example.com"
    assert rows[0]["sent"] == 1
    assert rows[0]["last_ts"] == "2026-04-23T12:00:00Z"
    assert rows[1]["email"] is None and rows[1]["prefix"] == "ffffffffffff"
    assert rows[2]["email"] == "alice@example.com"
    assert rows[2]["sent"] == 2
    assert rows[2]["first_ts"] == "2026-04-23T10:00:00Z"
    assert rows[2]["last_ts"] == "2026-04-23T10:30:00Z"


# ---- print_human() -------------------------------------------------------

def test_print_human_includes_expected_sections(capsys):
    stats = prod_stats.tally(FIXTURE_ENTRIES)
    disk = {"path": "/", "total_gib": 25.0, "used_gib": 10.0,
            "free_gib": 15.0, "pct_used": 40.0}
    prod_stats.print_human(stats, disk, "24 hours ago", "fellows-pwa")
    out = capsys.readouterr().out
    assert "fellows-pwa" in out
    assert "App-shell loads:" in out
    assert "Magic links sent:" in out
    assert "Disk (/)" in out
    assert "40.0%" in out
    # Without recipients, the confidential block must NOT appear.
    assert "Magic-link recipients" not in out


def test_print_human_with_recipients_prints_confidential_block(capsys):
    """When recipients are passed, print_human appends the recipient list
    (header + each row). Header text is the contract; address presence
    is the regression guard. Only synthetic emails here."""
    disk = {"path": "/", "total_gib": 25.0, "used_gib": 10.0,
            "free_gib": 15.0, "pct_used": 40.0}
    recipients = [
        {"prefix": "abcdef012345", "email": "alice@example.com", "name": "Alice",
         "sent": 2, "results": {"sent": 2}, "first_ts": "2026-04-23T10:00:00Z",
         "last_ts": "2026-04-23T10:30:00Z", "collisions": 0},
    ]
    prod_stats.print_human({
        "shell_loads": 0, "api_fellows": 0, "db_downloads": 0,
        "magic_links_sent": 2, "magic_links_send_failed": {},
        "magic_links_verified": 0, "magic_links_verify_failed": 0,
        "errors_4xx": {}, "errors_5xx": {},
    }, disk, "@0", "fellows-pwa", recipients=recipients)
    out = capsys.readouterr().out
    assert "Magic-link recipients" in out
    assert "alice@example.com" in out


def test_print_human_errors_only_skips_unrelated_sections(capsys):
    """In --errors-only mode, print_human prints just the 4xx/5xx counts
    plus the most recent error access lines. The shell-loads / disk /
    magic-link sections must NOT appear — that's the whole point of
    "what just broke?" triage view."""
    disk = {"path": "/", "total_gib": 25.0, "used_gib": 10.0,
            "free_gib": 15.0, "pct_used": 40.0}
    stats = {
        "shell_loads": 99, "api_fellows": 99, "db_downloads": 99,
        "magic_links_sent": 7, "magic_links_send_failed": {},
        "magic_links_verified": 7, "magic_links_verify_failed": 0,
        "errors_4xx": {"404 GET /thing": 3},
        "errors_5xx": {"500 GET /api/stats": 1},
        "recent_errors": [
            {"ts": "2026-04-23T15:00:00Z", "status": 404,
             "message": '127.0.0.1 - - [x] "GET /thing HTTP/1.1" 404 -'},
        ],
    }
    prod_stats.print_human(stats, disk, "24 hours ago", "fellows-pwa",
                           errors_only=True)
    out = capsys.readouterr().out
    assert "fellows-pwa" in out
    assert "4xx errors:" in out and "404 GET /thing: 3" in out
    assert "5xx errors:" in out and "500 GET /api/stats: 1" in out
    # The verbatim recent line is the high-value signal.
    assert "most recent error access line" in out
    assert "/thing" in out and "2026-04-23T15:00:00Z" in out
    # Sections that don't belong in errors-only must be absent.
    assert "App-shell loads:" not in out
    assert "Magic links sent:" not in out
    assert "Disk (" not in out


def test_print_human_errors_only_with_no_errors_says_so(capsys):
    """Empty 4xx/5xx + recent_errors should still produce a clean report
    (no crash, no blank section)."""
    disk = {"path": "/", "total_gib": 25.0, "used_gib": 10.0,
            "free_gib": 15.0, "pct_used": 40.0}
    stats = {
        "shell_loads": 0, "api_fellows": 0, "db_downloads": 0,
        "magic_links_sent": 0, "magic_links_send_failed": {},
        "magic_links_verified": 0, "magic_links_verify_failed": 0,
        "errors_4xx": {}, "errors_5xx": {}, "recent_errors": [],
    }
    prod_stats.print_human(stats, disk, "24 hours ago", "fellows-pwa",
                           errors_only=True)
    out = capsys.readouterr().out
    assert "4xx errors:              0" in out
    assert "5xx errors:              0" in out
    assert "(none in window)" in out


# ---- main() + --json -----------------------------------------------------

def test_main_json_output_parses(monkeypatch, capsys):
    # Short-circuit journal_entries so the test doesn't shell out to journalctl.
    monkeypatch.setattr(prod_stats, "journal_entries",
                        lambda unit, since: FIXTURE_ENTRIES)
    rc = prod_stats.main(["--json", "--since", "1 hour ago"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unit"] == "fellows-pwa"
    assert payload["since"] == "1 hour ago"
    assert payload["requests"]["shell_loads"] == 3
    assert payload["requests"]["magic_links_sent"] == 2
    assert set(payload["disk"].keys()) == {
        "path", "total_gib", "used_gib", "free_gib", "pct_used",
    }
    # 4xx + 5xx counters and recent-error list must be in the public JSON
    # so an automated consumer (e.g. an oncall dashboard) can read them.
    assert "errors_4xx" in payload["requests"]
    assert "errors_5xx" in payload["requests"]
    assert "recent_errors" in payload["requests"]
    # Internal per-prefix bucket must not leak into the public JSON.
    assert "email_events_by_prefix" not in payload["requests"]


def test_main_errors_only_flag_routes_to_focused_view(monkeypatch, capsys):
    """`--errors-only` switches the human output to the focused triage
    view; it must NOT change the JSON path. Verifies the wiring from
    argparse → print_human, not the body of print_human itself (which
    has its own tests above)."""
    error_entries = [
        _entry('127.0.0.1 - - [x] "GET /missing HTTP/1.1" 404 -',
               ts="2026-04-23T15:00:00Z"),
        _entry('127.0.0.1 - - [x] "GET / HTTP/1.1" 200 -',
               ts="2026-04-23T15:01:00Z"),
    ]
    monkeypatch.setattr(prod_stats, "journal_entries",
                        lambda unit, since: error_entries)
    rc = prod_stats.main(["--errors-only", "--since", "1 hour ago"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "4xx errors:" in out
    assert "404 GET /missing: 1" in out
    assert "most recent error access line" in out
    # Non-error sections suppressed.
    assert "App-shell loads:" not in out
    assert "Disk (" not in out
