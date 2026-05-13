"""Unit tests for scripts/installed_versions.py.

Mirrors tests/test_prod_stats.py: synthetic journald entries + a tiny
synthetic fellows.db, exercising the pure functions (``collect``,
``build_email_hash_index``, ``attribute``, ``print_human``) without
touching real journalctl or SSH.
"""
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "installed_versions.py")

_spec = importlib.util.spec_from_file_location("installed_versions", SCRIPT_PATH)
iv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(iv)


# ---- helpers -------------------------------------------------------------

def _entry(message: str, ts: str = "2026-05-12T10:00:00Z") -> dict:
    """Synthesize a journald entry dict matching `journalctl -o json` output."""
    epoch_us = int(
        datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1_000_000
    )
    return {"MESSAGE": message, "__REALTIME_TIMESTAMP": str(epoch_us)}


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _send_evt(email_hash_prefix: str, token_prefix: str, ts: str) -> dict:
    return _entry(
        json.dumps({
            "event": "send_unlock_email",
            "result": "sent",
            "email_hash_prefix": email_hash_prefix,
            "token_prefix": token_prefix,
            "postmark": {"MessageID": "x"},
        }),
        ts=ts,
    )


def _verify_evt(token_prefix: str, build_label: str, ua: str, ts: str,
                result: str = "ok") -> dict:
    return _entry(
        json.dumps({
            "event": "verify_token",
            "result": result,
            "token_prefix": token_prefix,
            "user_agent": ua,
            "build_label": build_label,
        }),
        ts=ts,
    )


def _boot_evt(last_submit_hash_prefix, build: str, ua: str, ts: str,
              extra: str = "displayMode=standalone provider=worker") -> dict:
    payload: dict = {
        "event": "client_error",
        "client_ip_prefix": "",
        "events": [{"kind": "boot", "msg": "cold_start", "extra": extra}],
        "ua": ua,
        "build": build,
        "route": "#/",
        "displayMode": "standalone",
        "online": True,
    }
    if last_submit_hash_prefix is not None:
        payload["lastSubmitHashPrefix"] = last_submit_hash_prefix
    return _entry(json.dumps(payload), ts=ts)


# ---- _parse_struct_event --------------------------------------------------

def test_parse_struct_event_matches_expected_event_kind():
    msg = json.dumps({"event": "verify_token", "result": "ok"})
    assert iv._parse_struct_event(msg, "verify_token") is not None
    # Wrong expected kind → None.
    assert iv._parse_struct_event(msg, "send_unlock_email") is None


def test_parse_struct_event_returns_none_for_access_log_lines():
    """Access log lines start with '127.0.0.1' — pre-filter must skip
    them cheaply before json.loads runs."""
    assert iv._parse_struct_event(
        '127.0.0.1 - - [12/May/2026 10:00:00] "GET / HTTP/1.1" 200 -',
        "verify_token",
    ) is None


def test_parse_struct_event_returns_none_for_malformed_json():
    assert iv._parse_struct_event('{"event": "verify_token"', "verify_token") is None


# ---- collect -------------------------------------------------------------

def test_collect_groups_three_event_kinds():
    """The bucketizer handles the three event kinds + the
    token_prefix → email_hash_prefix translation hop."""
    h = _sha256_hex("jane@example.com")
    prefix = h[:12]
    entries = [
        _send_evt(prefix, "tok123456789a", "2026-05-01T10:00:00Z"),
        _verify_evt("tok123456789a", "2026-05-01-aaaa", "Mozilla iPhone",
                    "2026-05-01T10:00:30Z"),
        _boot_evt(prefix, "2026-05-08-bbbb", "Mozilla iPhone",
                  "2026-05-08T08:00:00Z"),
    ]
    c = iv.collect(entries)
    assert c["send_token_to_email_prefix"]["tok123456789a"]["email_prefix"] == prefix
    assert c["verify_by_token_prefix"]["tok123456789a"]["build_label"] == "2026-05-01-aaaa"
    assert c["boot_by_email_prefix"][prefix]["build"] == "2026-05-08-bbbb"
    assert c["anonymous_boots"] == []


def test_collect_keeps_most_recent_per_key():
    """Two verify_token events on the same token_prefix (shouldn't happen
    in practice — random 12-hex — but if it does, freshest wins so the
    report reflects the latest known build)."""
    entries = [
        _verify_evt("tok_dup______", "2026-05-01-old", "ua1",
                    "2026-05-01T10:00:00Z"),
        _verify_evt("tok_dup______", "2026-05-08-new", "ua2",
                    "2026-05-08T10:00:00Z"),
    ]
    c = iv.collect(entries)
    rec = c["verify_by_token_prefix"]["tok_dup______"]
    assert rec["build_label"] == "2026-05-08-new"
    assert rec["ua"] == "ua2"


def test_collect_drops_failed_verify_attempts():
    """Only result=ok counts — expired/invalid attempts don't reveal a
    successful install. They still emit events (Phase A logs every
    consume_token outcome), but the attribution table should ignore
    them."""
    entries = [
        _verify_evt("tok_expired__", "2026-05-08-bld", "ua",
                    "2026-05-08T10:00:00Z", result="expired"),
        _verify_evt("tok_invalid__", "2026-05-08-bld", "ua",
                    "2026-05-08T10:00:00Z", result="invalid"),
    ]
    c = iv.collect(entries)
    assert c["verify_by_token_prefix"] == {}


def test_collect_separates_anonymous_boots():
    """Boots without lastSubmitHashPrefix land in anonymous_boots —
    can't be joined to email but still tell us a build is running."""
    entries = [
        _boot_evt(None, "2026-05-08-aaa", "Chrome", "2026-05-08T10:00:00Z"),
        _boot_evt(None, "2026-05-08-aaa", "Chrome", "2026-05-08T11:00:00Z"),
        _boot_evt(None, "2026-05-09-bbb", "Safari", "2026-05-09T10:00:00Z"),
    ]
    c = iv.collect(entries)
    assert c["boot_by_email_prefix"] == {}
    assert len(c["anonymous_boots"]) == 3


def test_collect_ignores_non_boot_client_errors():
    """`kind=install` and `kind=worker` client_error events also live in
    journald (they share the sink) — they must NOT bucket into the boot
    map. Only the first event's kind matters."""
    entries = [
        _entry(json.dumps({
            "event": "client_error",
            "events": [{"kind": "install", "msg": "landing_shown"}],
            "ua": "ua", "build": "2026-05-08-x", "displayMode": "browser-tab",
            "lastSubmitHashPrefix": "abcdef012345",
        }), ts="2026-05-08T10:00:00Z"),
        _entry(json.dumps({
            "event": "client_error",
            "events": [{"kind": "worker", "msg": "spawn_ok"}],
            "ua": "ua", "build": "2026-05-08-x", "displayMode": "standalone",
            "lastSubmitHashPrefix": "abcdef012345",
        }), ts="2026-05-08T10:01:00Z"),
    ]
    c = iv.collect(entries)
    assert c["boot_by_email_prefix"] == {}
    assert c["anonymous_boots"] == []


# ---- attribute -----------------------------------------------------------

def _make_db(tmp_path, emails):
    """Build a tiny fellows.db with the given (email, name) tuples."""
    db = tmp_path / "fellows.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE fellows (record_id TEXT PRIMARY KEY, slug TEXT, "
        "name TEXT, contact_email TEXT)"
    )
    for i, (email, name) in enumerate(emails):
        conn.execute(
            "INSERT INTO fellows (record_id, slug, name, contact_email) "
            "VALUES (?, ?, ?, ?)",
            (f"r{i}", f"s{i}", name, email),
        )
    conn.commit()
    conn.close()
    return db


def test_attribute_joins_verify_and_boot_for_same_email(tmp_path):
    """Happy path: a fellow with both verify_token AND kind=boot in
    window gets a single row carrying both columns + the plaintext
    email."""
    email = "jane@example.com"
    h = _sha256_hex(email)
    prefix = h[:12]
    db = _make_db(tmp_path, [(email, "Jane Example")])
    hash_index = iv.build_email_hash_index(str(db))

    entries = [
        _send_evt(prefix, "tok_aaaaaaaa", "2026-05-01T10:00:00Z"),
        _verify_evt("tok_aaaaaaaa", "2026-05-01-install", "iPhone OS 16_3",
                    "2026-05-01T10:00:30Z"),
        _boot_evt(prefix, "2026-05-08-seen", "iPhone OS 16_3",
                  "2026-05-08T08:00:00Z"),
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    assert len(attribution["rows"]) == 1
    row = attribution["rows"][0]
    assert row["email"] == "jane@example.com"
    assert row["installed_build"] == "2026-05-01-install"
    assert row["seen_build"] == "2026-05-08-seen"
    assert row["last_activity"] == "2026-05-08T08:00:00Z"
    assert row["stuck"] is True  # install != seen


def test_attribute_marks_healthy_when_install_matches_seen(tmp_path):
    """Equal build labels means no stale-shell drift — stuck=False."""
    email = "ok@example.com"
    h = _sha256_hex(email)
    prefix = h[:12]
    db = _make_db(tmp_path, [(email, "OK")])
    hash_index = iv.build_email_hash_index(str(db))
    entries = [
        _send_evt(prefix, "tok_okokokok", "2026-05-08T10:00:00Z"),
        _verify_evt("tok_okokokok", "2026-05-08-x", "ua",
                    "2026-05-08T10:00:30Z"),
        _boot_evt(prefix, "2026-05-08-x", "ua", "2026-05-08T12:00:00Z"),
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    assert attribution["rows"][0]["stuck"] is False


def test_attribute_handles_install_only_row(tmp_path):
    """A user who clicked the magic link but never booted after Phase B
    deployed shows installed_build only — seen_build is '—'."""
    email = "verify-only@example.com"
    h = _sha256_hex(email)
    prefix = h[:12]
    db = _make_db(tmp_path, [(email, "Verify Only")])
    hash_index = iv.build_email_hash_index(str(db))
    entries = [
        _send_evt(prefix, "tok_vvvvvvvv", "2026-05-08T10:00:00Z"),
        _verify_evt("tok_vvvvvvvv", "2026-05-08-install", "ua",
                    "2026-05-08T10:00:30Z"),
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    row = attribution["rows"][0]
    assert row["installed_build"] == "2026-05-08-install"
    assert row["seen_build"] == ""
    # stuck only triggers when BOTH builds present and they differ.
    assert row["stuck"] is False


def test_attribute_handles_boot_only_row(tmp_path):
    """A user whose last verify_token was pre-Phase-A but who boots
    after Phase B shows seen_build only — installed_build is '—'.
    This is the dominant case for existing installs the first time
    they open the app after telemetry ships."""
    email = "boot-only@example.com"
    h = _sha256_hex(email)
    prefix = h[:12]
    db = _make_db(tmp_path, [(email, "Boot Only")])
    hash_index = iv.build_email_hash_index(str(db))
    entries = [
        _boot_evt(prefix, "2026-05-08-current", "Safari",
                  "2026-05-08T08:00:00Z"),
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    row = attribution["rows"][0]
    assert row["installed_build"] == ""
    assert row["seen_build"] == "2026-05-08-current"
    assert row["last_activity"] == "2026-05-08T08:00:00Z"


def test_attribute_drops_verify_without_matching_send(tmp_path):
    """A verify_token whose matching send_unlock_email aged out of the
    window can't be attributed — drop rather than guess. The user can
    widen --since '@0' to recover."""
    db = _make_db(tmp_path, [("orphan@example.com", "Orphan")])
    hash_index = iv.build_email_hash_index(str(db))
    entries = [
        _verify_evt("tok_orphaned_", "2026-05-08-x", "ua",
                    "2026-05-08T10:00:30Z"),
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    assert attribution["rows"] == []


def test_attribute_keeps_most_recent_verify_per_email(tmp_path):
    """Two verify_token events for the same email (different magic-link
    clicks) collapse to one row showing the most recent build."""
    email = "frequent@example.com"
    h = _sha256_hex(email)
    prefix = h[:12]
    db = _make_db(tmp_path, [(email, "Frequent")])
    hash_index = iv.build_email_hash_index(str(db))
    entries = [
        # Old click — different token.
        _send_evt(prefix, "tok_old111111", "2026-05-01T10:00:00Z"),
        _verify_evt("tok_old111111", "2026-05-01-old", "ua-old",
                    "2026-05-01T10:00:30Z"),
        # Recent click — different token, same email.
        _send_evt(prefix, "tok_new222222", "2026-05-08T10:00:00Z"),
        _verify_evt("tok_new222222", "2026-05-08-new", "ua-new",
                    "2026-05-08T10:00:30Z"),
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    assert len(attribution["rows"]) == 1
    row = attribution["rows"][0]
    assert row["installed_build"] == "2026-05-08-new"


def test_attribute_handles_unknown_prefix(tmp_path):
    """A boot event whose lastSubmitHashPrefix doesn't match any fellow
    in fellows.db still surfaces — email is None, name is None, prefix
    is shown in place. This catches an off-allowlist user (rare but
    real) or a stale DB."""
    db = _make_db(tmp_path, [("known@example.com", "Known")])
    hash_index = iv.build_email_hash_index(str(db))
    entries = [
        _boot_evt("999999999999", "2026-05-08-x", "ua",
                  "2026-05-08T10:00:00Z"),
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    assert len(attribution["rows"]) == 1
    row = attribution["rows"][0]
    assert row["email"] is None
    assert row["email_prefix"] == "999999999999"


def test_attribute_aggregates_anonymous_boots_by_build(tmp_path):
    """Boots without lastSubmitHashPrefix get histogrammed by build —
    'N anonymous users on build X' is still operationally useful even
    without identity."""
    db = _make_db(tmp_path, [])
    hash_index = iv.build_email_hash_index(str(db))
    entries = [
        _boot_evt(None, "2026-05-08-a", "ua", "2026-05-08T10:00:00Z"),
        _boot_evt(None, "2026-05-08-a", "ua", "2026-05-08T11:00:00Z"),
        _boot_evt(None, "2026-05-09-b", "ua", "2026-05-09T10:00:00Z"),
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    assert attribution["anonymous_count"] == 3
    assert attribution["anonymous_builds"] == {
        "2026-05-08-a": 2,
        "2026-05-09-b": 1,
    }


def test_attribute_sorts_by_most_recent_activity(tmp_path):
    """Rows must come out most-recent-first so the maintainer's eye
    lands on the freshest signal."""
    db = _make_db(tmp_path, [
        ("old@example.com", "Old"),
        ("new@example.com", "New"),
    ])
    hash_index = iv.build_email_hash_index(str(db))
    old_h = _sha256_hex("old@example.com")
    new_h = _sha256_hex("new@example.com")
    entries = [
        _boot_evt(old_h[:12], "build-1", "ua", "2026-04-01T10:00:00Z"),
        _boot_evt(new_h[:12], "build-2", "ua", "2026-05-08T10:00:00Z"),
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    assert [r["email"] for r in attribution["rows"]] == [
        "new@example.com", "old@example.com",
    ]


# ---- build_email_hash_index ----------------------------------------------

def test_build_email_hash_index_normalises_email(tmp_path):
    """Mirrors the server's lower(trim(contact_email)) — must match so
    the prefix join lands."""
    db = _make_db(tmp_path, [("  Jane@Example.COM  ", "Jane")])
    idx = iv.build_email_hash_index(str(db))
    expected = _sha256_hex("jane@example.com")
    assert expected in idx
    assert idx[expected] == {"email": "jane@example.com", "name": "Jane"}


def test_build_email_hash_index_handles_missing_db(tmp_path):
    """Missing DB → empty dict, not raise. CLI keeps emitting the table
    with '<unknown prefix=…>' placeholders."""
    assert iv.build_email_hash_index(str(tmp_path / "nope.db")) == {}


# ---- print_human ---------------------------------------------------------

def test_print_human_handles_empty_window():
    """Smoke: empty input still produces readable output, no crash."""
    attribution = {"rows": [], "anonymous_count": 0, "anonymous_builds": {}}
    buf = io.StringIO()
    with redirect_stdout(buf):
        iv.print_human(attribution, "30 days ago", "fellows-pwa")
    out = buf.getvalue()
    assert "installed-versions" in out
    assert "no attributed" in out


def test_print_human_flags_stuck_users(tmp_path):
    """The STUCK marker is the load-bearing call-out — make sure it
    actually appears for an install/seen mismatch."""
    email = "stuck@example.com"
    h = _sha256_hex(email)
    prefix = h[:12]
    db = _make_db(tmp_path, [(email, "Stuck")])
    hash_index = iv.build_email_hash_index(str(db))
    entries = [
        _send_evt(prefix, "tok_s_s_s_s_", "2026-04-23T10:00:00Z"),
        _verify_evt("tok_s_s_s_s_", "2026-04-23-af63655", "iPhone",
                    "2026-04-23T10:00:30Z"),
        _boot_evt(prefix, "2026-04-23-af63655", "iPhone",
                  "2026-05-09T08:00:00Z"),  # same build — NOT stuck
    ]
    attribution = iv.attribute(iv.collect(entries), hash_index)
    buf = io.StringIO()
    with redirect_stdout(buf):
        iv.print_human(attribution, "30 days ago", "fellows-pwa")
    assert "STUCK" not in buf.getvalue()

    # Now flip seen to a newer build → should be marked stuck.
    entries[-1] = _boot_evt(prefix, "2026-05-12-newer", "iPhone",
                            "2026-05-12T08:00:00Z")
    attribution = iv.attribute(iv.collect(entries), hash_index)
    buf = io.StringIO()
    with redirect_stdout(buf):
        iv.print_human(attribution, "30 days ago", "fellows-pwa")
    assert "STUCK" in buf.getvalue()


def test_print_human_surfaces_anonymous_boots():
    attribution = {
        "rows": [],
        "anonymous_count": 5,
        "anonymous_builds": {"2026-05-12-abc": 4, "2026-05-08-xyz": 1},
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        iv.print_human(attribution, "30 days ago", "fellows-pwa")
    out = buf.getvalue()
    assert "5 events" in out or "Anonymous boots" in out
    assert "2026-05-12-abc" in out
    assert "2026-05-08-xyz" in out


# ---- end-to-end through main(--json) -------------------------------------

def test_main_json_emits_stable_schema(tmp_path, monkeypatch, capsys):
    """End-to-end smoke: --json output carries the documented top-level
    keys. We stub journal_entries and build_email_hash_index so the
    test doesn't depend on the droplet."""
    email = "jane@example.com"
    h = _sha256_hex(email)
    prefix = h[:12]

    entries = [
        _send_evt(prefix, "tok_e2e_aaaa", "2026-05-01T10:00:00Z"),
        _verify_evt("tok_e2e_aaaa", "2026-05-01-x", "ua",
                    "2026-05-01T10:00:30Z"),
        _boot_evt(prefix, "2026-05-08-y", "ua", "2026-05-08T08:00:00Z"),
    ]
    monkeypatch.setattr(iv, "journal_entries", lambda unit, since: entries)
    db = _make_db(tmp_path, [(email, "Jane")])
    monkeypatch.setattr(
        iv, "build_email_hash_index",
        lambda path=iv.FELLOWS_DB_PATH: iv.build_email_hash_index.__wrapped__(str(db))
        if hasattr(iv.build_email_hash_index, "__wrapped__")
        else _real_index(db),
    )
    # The above monkeypatch trick is fragile; simpler: just override
    # FELLOWS_DB_PATH to point at our tmp DB.
    monkeypatch.setattr(iv, "FELLOWS_DB_PATH", str(db))
    monkeypatch.setattr(
        iv, "build_email_hash_index", lambda path=str(db): _real_index(db)
    )

    rc = iv.main(["--json", "--since", "30 days ago"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["unit"] == "fellows-pwa"
    assert payload["since"] == "30 days ago"
    assert isinstance(payload["rows"], list)
    assert payload["rows"][0]["email"] == "jane@example.com"


def _real_index(db_path):
    """Helper for the monkeypatch above — calls the real builder against
    a known-good DB path without recursing through the monkeypatched
    binding."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT name, lower(trim(contact_email)) AS email "
            "FROM fellows WHERE contact_email IS NOT NULL "
            "AND trim(contact_email) != ''"
        )
        out = {}
        for row in cur.fetchall():
            email = row["email"]
            if email:
                out[hashlib.sha256(email.encode("utf-8")).hexdigest()] = {
                    "email": email, "name": row["name"] or ""
                }
        return out
    finally:
        conn.close()
