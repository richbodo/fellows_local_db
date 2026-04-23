"""Unit tests for scripts/prod_stats.py.

The script is stdlib-only and lives under scripts/ (not a package), so we
load it by path. Tests exercise the pure functions (tally, disk_usage,
print_human) against fixture MESSAGE strings — no real journalctl or SSH.
"""
import importlib.util
import io
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "prod_stats.py")

_spec = importlib.util.spec_from_file_location("prod_stats", SCRIPT_PATH)
prod_stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prod_stats)


# ---- fixture: representative journald MESSAGE strings --------------------

FIXTURE_MESSAGES = [
    # App-shell loads
    '127.0.0.1 - - [23/Apr/2026 10:15:32] "GET / HTTP/1.1" 200 -',
    '127.0.0.1 - - [23/Apr/2026 10:15:33] "GET /index.html HTTP/1.1" 200 -',
    '127.0.0.1 - - [23/Apr/2026 10:16:01] "GET / HTTP/1.1" 304 -',
    # Directory API (count both list and detail)
    '127.0.0.1 - - [23/Apr/2026 10:15:34] "GET /api/fellows HTTP/1.1" 200 -',
    '127.0.0.1 - - [23/Apr/2026 10:15:35] "GET /api/fellows?full=1 HTTP/1.1" 200 -',
    '127.0.0.1 - - [23/Apr/2026 10:16:00] "GET /api/fellows/jane-doe HTTP/1.1" 200 -',
    # DB downloads
    '127.0.0.1 - - [23/Apr/2026 10:15:36] "GET /fellows.db HTTP/1.1" 200 -',
    # Magic-link verify: one success, one 401
    '127.0.0.1 - - [23/Apr/2026 10:17:00] "POST /api/verify-token HTTP/1.1" 200 -',
    '127.0.0.1 - - [23/Apr/2026 10:17:05] "POST /api/verify-token HTTP/1.1" 401 -',
    # 5xx error (should bucket under errors_5xx)
    '127.0.0.1 - - [23/Apr/2026 10:18:00] "GET /api/stats HTTP/1.1" 500 -',
    # Send-unlock structured events: two sent, one http_error
    json.dumps({"event": "send_unlock_email", "result": "sent",
                "email_hash_prefix": "deadbeef1234", "token_prefix": "aaaaaaaaaaaa",
                "postmark": {"MessageID": "m1"}}),
    json.dumps({"event": "send_unlock_email", "result": "sent",
                "email_hash_prefix": "cafebabe5678", "token_prefix": "bbbbbbbbbbbb",
                "postmark": {"MessageID": "m2"}}),
    json.dumps({"event": "send_unlock_email", "result": "http_error",
                "email_hash_prefix": "feedface9abc", "token_prefix": "cccccccccccc",
                "status": 422}),
    # Noise that must not bump any counter
    "Rate limit: send-unlock for hash prefix deadbeef1234",
    '{"event": "build_meta", "build": {"built_at": "2026-04-23T09:00Z"}}',
    "",
    "not-a-log-line at all",
]


# ---- tally() -------------------------------------------------------------

def test_tally_counts_shell_loads():
    stats = prod_stats.tally(FIXTURE_MESSAGES)
    assert stats["shell_loads"] == 3


def test_tally_counts_directory_api():
    stats = prod_stats.tally(FIXTURE_MESSAGES)
    # list + ?full=1 + detail
    assert stats["api_fellows"] == 3


def test_tally_counts_db_downloads():
    stats = prod_stats.tally(FIXTURE_MESSAGES)
    assert stats["db_downloads"] == 1


def test_tally_counts_magic_link_verifications():
    stats = prod_stats.tally(FIXTURE_MESSAGES)
    assert stats["magic_links_verified"] == 1
    assert stats["magic_links_verify_failed"] == 1


def test_tally_counts_magic_links_sent_and_failures():
    stats = prod_stats.tally(FIXTURE_MESSAGES)
    assert stats["magic_links_sent"] == 2
    assert stats["magic_links_send_failed"] == {"http_error": 1}


def test_tally_bucket_5xx_by_route():
    stats = prod_stats.tally(FIXTURE_MESSAGES)
    assert stats["errors_5xx"] == {"500 GET /api/stats": 1}


def test_tally_ignores_build_meta_and_rate_limit_lines():
    # Inputs that look structured but aren't send_unlock_email must not count.
    msgs = [
        '{"event": "build_meta", "build": {"built_at": "x"}}',
        "Rate limit: send-unlock for hash prefix deadbeef1234",
    ]
    stats = prod_stats.tally(msgs)
    assert stats["magic_links_sent"] == 0
    assert stats["shell_loads"] == 0


def test_tally_empty_input_returns_zeros():
    stats = prod_stats.tally([])
    assert stats["shell_loads"] == 0
    assert stats["magic_links_sent"] == 0
    assert stats["errors_5xx"] == {}
    assert stats["magic_links_send_failed"] == {}


def test_tally_distinguishes_api_fellows_from_api_stats():
    # /api/stats must not be counted as /api/fellows.
    msgs = [
        '127.0.0.1 - - [x] "GET /api/stats HTTP/1.1" 200 -',
        '127.0.0.1 - - [x] "GET /api/fellows HTTP/1.1" 200 -',
    ]
    stats = prod_stats.tally(msgs)
    assert stats["api_fellows"] == 1


# ---- disk_usage() --------------------------------------------------------

def test_disk_usage_shape():
    disk = prod_stats.disk_usage("/")
    assert set(disk.keys()) == {"path", "total_gib", "used_gib", "free_gib", "pct_used"}
    assert disk["path"] == "/"
    assert disk["total_gib"] > 0
    assert 0.0 <= disk["pct_used"] <= 100.0


# ---- print_human() -------------------------------------------------------

def test_print_human_includes_expected_sections(capsys):
    stats = prod_stats.tally(FIXTURE_MESSAGES)
    disk = {"path": "/", "total_gib": 25.0, "used_gib": 10.0,
            "free_gib": 15.0, "pct_used": 40.0}
    prod_stats.print_human(stats, disk, "24 hours ago", "fellows-pwa")
    out = capsys.readouterr().out
    assert "fellows-pwa" in out
    assert "App-shell loads:" in out
    assert "Magic links sent:" in out
    assert "Disk (/)" in out
    assert "40.0%" in out


# ---- main() + --json -----------------------------------------------------

def test_main_json_output_parses(monkeypatch, capsys):
    # Short-circuit journal_messages so the test doesn't shell out to journalctl.
    monkeypatch.setattr(prod_stats, "journal_messages", lambda unit, since: FIXTURE_MESSAGES)
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
