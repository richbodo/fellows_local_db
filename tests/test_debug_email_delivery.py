"""Unit tests for scripts/debug_email_delivery.py.

The SSH + Postmark paths are integration-only and not exercised here.
These tests cover pure logic: hashing, parsing journalctl JSON lines,
filtering, and report formatting.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import debug_email_delivery as ded  # noqa: E402


def _journal_envelope(message: str, ts_us: int = 1_743_000_000_000_000) -> str:
    """Build a journalctl -o json envelope for the given MESSAGE."""
    return json.dumps(
        {
            "_TRANSPORT": "stdout",
            "__REALTIME_TIMESTAMP": str(ts_us),
            "MESSAGE": message,
        }
    )


def _send_event_json(**overrides) -> str:
    payload = {
        "event": "send_unlock_email",
        "result": "sent",
        "email_hash_prefix": "aabbccddeeff",
        "token_prefix": "1122334455aa",
        "postmark": {
            "message_id": "msg-id-1",
            "error_code": 0,
            "message": "OK",
            "to": "to@example.com",
            "submitted_at": "2026-04-19T05:41:02.0Z",
        },
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_build_ssh_cmd_quotes_since_with_spaces():
    """--since '2 hours ago' must survive SSH-then-remote-shell re-parse.

    Regression: SSH concatenates argv with spaces on the wire, so unquoted
    remote args get re-split by the remote shell. journalctl rejects the
    resulting `--since 2` with "Failed to parse timestamp: 2".
    """
    cmd = ded.build_ssh_cmd("example.com", "52221", "rsb", "2 hours ago")
    assert cmd[0] == "ssh"
    assert cmd[-2] == "rsb@example.com"
    remote = cmd[-1]
    # Every remote token that journalctl would re-split must be shell-quoted.
    assert "'2 hours ago'" in remote
    assert "journalctl -u fellows-pwa --since '2 hours ago' -o json --no-pager" == remote


def test_build_ssh_cmd_quotes_unit_and_simple_since():
    """Simple args (no spaces) are safe to leave unquoted, but shlex.quote
    is idempotent so the command shape is still deterministic."""
    cmd = ded.build_ssh_cmd("h", "22", "u", "24h", unit="foo-pwa")
    remote = cmd[-1]
    assert "foo-pwa" in remote
    assert " 24h " in remote + " "  # 24h appears as its own token


def test_build_ssh_cmd_sudo_mode_uses_sudo_s_not_pty():
    """--sudo uses `sudo -S -p ''` + piped stdin password, not a pty.

    Regression: the old `-tt` pty approach swallowed sudo's prompt into the
    captured stdout stream so the user never saw "Password:" and the script
    hung waiting for input they didn't know to provide.
    """
    cmd = ded.build_ssh_cmd("example.com", "52221", "rsb", "2 hours ago", use_sudo=True)
    assert "-tt" not in cmd
    assert "BatchMode=yes" not in " ".join(cmd)
    remote = cmd[-1]
    # `sudo -S -p '' journalctl ...` — the empty -p silences the prompt text
    # so it doesn't contaminate the journalctl JSON output.
    assert remote.startswith("sudo -S -p '' journalctl ")
    assert "'2 hours ago'" in remote


def test_build_ssh_cmd_default_uses_batchmode_no_sudo():
    cmd = ded.build_ssh_cmd("h", "22", "u", "24h")
    assert "-tt" not in cmd
    assert "BatchMode=yes" in cmd
    assert not cmd[-1].startswith("sudo ")


def test_ssh_journal_sudo_pipes_password_to_stdin(monkeypatch):
    """--sudo path should pipe the password to subprocess stdin, not rely on a tty."""
    captured = {}

    class _FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        captured["capture_output"] = kwargs.get("capture_output")
        return _FakeResult()

    monkeypatch.setattr(ded.subprocess, "run", fake_run)
    ded.ssh_journal(
        "h", "22", "u", "24h", use_sudo=True, sudo_password="secret-pw"
    )
    assert captured["input"] == "secret-pw\n"
    assert captured["capture_output"] is True
    # Password never ends up in argv itself.
    assert "secret-pw" not in " ".join(captured["cmd"])


def test_ssh_journal_non_sudo_does_not_write_stdin(monkeypatch):
    captured = {}

    class _FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["input"] = kwargs.get("input")
        return _FakeResult()

    monkeypatch.setattr(ded.subprocess, "run", fake_run)
    ded.ssh_journal("h", "22", "u", "24h", use_sudo=False)
    assert captured["input"] is None


def test_hash_email_matches_server_contract():
    a = ded.hash_email("  Test@Example.COM  ")
    b = ded.hash_email("test@example.com")
    assert a == b
    assert len(a) == 64


def test_parse_events_extracts_send_event_and_timestamp():
    raw = _journal_envelope(_send_event_json(), ts_us=1_743_000_000_000_000)
    events = ded.parse_events(raw)
    assert len(events) == 1
    e = events[0]
    assert e["event"] == "send_unlock_email"
    assert e["result"] == "sent"
    assert e["email_hash_prefix"] == "aabbccddeeff"
    assert e["_ts"] == "2025-03-26T14:40:00Z"


def test_parse_events_extracts_rate_limit_line():
    raw = _journal_envelope("Rate limit: send-unlock for hash prefix deadbeef0123")
    events = ded.parse_events(raw)
    assert len(events) == 1
    assert events[0]["result"] == "rate_limit"
    assert events[0]["email_hash_prefix"] == "deadbeef0123"


def test_parse_events_skips_unrelated_journal_lines():
    # Auth-status events and build_meta lines should be ignored.
    raw = "\n".join(
        [
            _journal_envelope(
                json.dumps({"event": "auth_status", "authenticated": True})
            ),
            _journal_envelope(
                json.dumps({"event": "build_meta", "build": {"git_sha": "abc"}})
            ),
            _journal_envelope("Serving /opt/fellows/deploy/dist on 127.0.0.1:8765"),
        ]
    )
    assert ded.parse_events(raw) == []


def test_parse_events_tolerates_garbage_lines():
    raw = "\n".join(
        [
            "not json at all",
            "",
            _journal_envelope(_send_event_json()),
            "{\"MESSAGE\":\"truncated",  # malformed outer JSON
        ]
    )
    events = ded.parse_events(raw)
    assert len(events) == 1
    assert events[0]["result"] == "sent"


def test_parse_events_handles_http_error_shape():
    raw = _journal_envelope(
        json.dumps(
            {
                "event": "send_unlock_email",
                "result": "http_error",
                "email_hash_prefix": "deadbeef0123",
                "token_prefix": "aabb1122cc33",
                "status": 422,
                "reason": "HTTP Error 422",
                "body": '{"ErrorCode":406,"Message":"Sender signature not confirmed"}',
            }
        )
    )
    events = ded.parse_events(raw)
    assert len(events) == 1
    assert events[0]["result"] == "http_error"
    assert events[0]["status"] == 422
    assert "ErrorCode" in events[0]["body"]


def test_filter_events_by_email_hash_prefix_exact():
    events = [
        {"result": "sent", "email_hash_prefix": "aabbccddeeff"},
        {"result": "sent", "email_hash_prefix": "aabbccddeeff"},
        {"result": "sent", "email_hash_prefix": "000000000000"},
    ]
    got = ded.filter_events(events, email_hash_prefix="aabbccdd")
    assert len(got) == 2

    got = ded.filter_events(events, email_hash_prefix="zzzz")
    assert got == []


def test_filter_events_by_result():
    events = [
        {"result": "sent", "email_hash_prefix": "a"},
        {"result": "http_error", "email_hash_prefix": "a"},
        {"result": "rate_limit", "email_hash_prefix": "a"},
    ]
    assert len(ded.filter_events(events, result="sent")) == 1
    assert len(ded.filter_events(events, result="http_error")) == 1
    assert len(ded.filter_events(events, result="rate_limit")) == 1
    assert len(ded.filter_events(events, result="error")) == 0


def test_filter_events_combined_prefix_and_result():
    events = [
        {"result": "sent", "email_hash_prefix": "aabbcc"},
        {"result": "http_error", "email_hash_prefix": "aabbcc"},
        {"result": "sent", "email_hash_prefix": "000000"},
    ]
    got = ded.filter_events(events, email_hash_prefix="aabb", result="sent")
    assert len(got) == 1
    assert got[0]["result"] == "sent"
    assert got[0]["email_hash_prefix"] == "aabbcc"


def test_format_report_empty_window():
    out = ded.format_report(
        [], {}, {"host": "fellows.example", "since": "2h", "filter_desc": None}
    )
    assert "No events in window." in out
    assert "fellows.example" in out


def test_format_report_renders_sent_event_fields():
    events = [
        {
            "event": "send_unlock_email",
            "result": "sent",
            "email_hash_prefix": "aabbccddeeff",
            "token_prefix": "1122334455aa",
            "postmark": {
                "message_id": "msg-123",
                "error_code": 0,
                "message": "OK",
                "to": "to@example.com",
                "submitted_at": "2026-04-19T05:41:02Z",
            },
            "_ts": "2026-04-19T05:41:02Z",
        }
    ]
    out = ded.format_report(
        events,
        {},
        {"host": "fellows.example", "since": "2h", "filter_desc": "email hash aabbccdd…"},
    )
    assert "result=sent" in out
    assert "msg-123" in out
    assert "aabbccddeeff" in out
    assert "Summary:" in out
    assert "sent: 1" in out
    # The "Message: OK" line is noise — we suppress it.
    assert "Message:            OK" not in out


def test_format_report_renders_http_error_body():
    events = [
        {
            "event": "send_unlock_email",
            "result": "http_error",
            "email_hash_prefix": "deadbeef0123",
            "token_prefix": "11aa22bb33cc",
            "status": 422,
            "reason": "HTTP Error 422: Unprocessable Entity",
            "body": '{"ErrorCode":406,"Message":"Sender signature not confirmed"}',
            "_ts": "2026-04-19T05:42:18Z",
        }
    ]
    out = ded.format_report(events, {}, {"host": "h", "since": "s", "filter_desc": None})
    assert "http_error" in out
    assert "Sender signature not confirmed" in out
    assert "422" in out


def test_format_report_renders_postmark_lookup():
    events = [
        {
            "event": "send_unlock_email",
            "result": "sent",
            "email_hash_prefix": "aa",
            "token_prefix": "bb",
            "postmark": {"message_id": "msg-1"},
            "_ts": "2026-04-19T05:41:00Z",
        }
    ]
    postmark = {
        "msg-1": {
            "Status": "Sent",
            "Recipients": ["to@example.com"],
            "MessageEvents": [
                {"Type": "Delivered", "ReceivedAt": "2026-04-19T05:41:05Z", "Details": {}},
                {"Type": "Opened", "ReceivedAt": "2026-04-19T05:45:01Z", "Details": {"Summary": "opened"}},
            ],
        }
    }
    out = ded.format_report(events, postmark, {"host": "h", "since": "s", "filter_desc": None})
    assert "Postmark resolution" in out
    assert "Delivered" in out
    assert "Opened" in out


def test_format_report_renders_postmark_lookup_error():
    events = [
        {
            "event": "send_unlock_email",
            "result": "sent",
            "email_hash_prefix": "aa",
            "postmark": {"message_id": "msg-1"},
            "_ts": "t",
        }
    ]
    postmark = {"msg-1": {"_error": "HTTP 401", "_body": "invalid token"}}
    out = ded.format_report(events, postmark, {"host": "h", "since": "s", "filter_desc": None})
    assert "HTTP 401" in out
    assert "invalid token" in out


def test_main_refuses_both_email_and_hash_prefix(capsys, monkeypatch):
    # main() should exit via argparse.error when both are supplied.
    def _fail(*a, **kw):
        raise AssertionError("ssh_journal should not be reached on arg error")

    monkeypatch.setattr(ded, "ssh_journal", _fail)
    import pytest

    with pytest.raises(SystemExit) as exc:
        ded.main(
            ["--email", "a@b.com", "--email-hash-prefix", "deadbeef"]
        )
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "one of" in err


def test_main_json_output_round_trips(monkeypatch, capsys):
    """End-to-end JSON path: mock ssh_journal, verify JSON structure.

    --no-sudo so getpass doesn't prompt, --no-postmark so we don't try to
    fetch a token. No --email so the allowlist check isn't triggered.
    """
    monkeypatch.setattr(
        ded,
        "ssh_journal",
        lambda host, port, user, since, **kw: _journal_envelope(_send_event_json()),
    )
    rc = ded.main(["--json", "--no-sudo", "--no-postmark", "--since", "1 hour ago"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["host"] == ded.DEFAULT_HOST
    assert data["since"] == "1 hour ago"
    assert len(data["events"]) == 1
    assert data["events"][0]["result"] == "sent"
    assert data["postmark"] == {}


def test_postmark_default_is_on(monkeypatch):
    """No flag → args.postmark is True (default-on; --no-postmark opts out)."""
    ap = ded.build_arg_parser()
    args = ap.parse_args([])
    assert args.postmark is True


def test_postmark_no_postmark_flag_opts_out():
    ap = ded.build_arg_parser()
    args = ap.parse_args(["--no-postmark"])
    assert args.postmark is False


def test_resolve_postmark_token_prefers_cli_arg(monkeypatch):
    """Priority 1: --postmark-token beats env and auto-fetch."""
    monkeypatch.setenv("FELLOWS_POSTMARK_TOKEN", "env-token")
    ap = ded.build_arg_parser()
    args = ap.parse_args(["--postmark-token", "cli-token"])
    tok, source = ded.resolve_postmark_token(args, sudo_password="pw")
    assert tok == "cli-token"
    assert "--postmark-token" in source


def test_resolve_postmark_token_falls_back_to_env(monkeypatch):
    """Priority 2: env var when --postmark-token unset."""
    monkeypatch.setenv("FELLOWS_POSTMARK_TOKEN", "env-token")
    ap = ded.build_arg_parser()
    args = ap.parse_args([])
    tok, source = ded.resolve_postmark_token(args, sudo_password=None)
    assert tok == "env-token"
    assert "env" in source


def test_resolve_postmark_token_auto_fetches_with_sudo(monkeypatch):
    """Priority 3: auto-fetch from prod env file when sudo password available."""
    monkeypatch.delenv("FELLOWS_POSTMARK_TOKEN", raising=False)
    monkeypatch.setattr(
        ded, "fetch_postmark_token_from_prod",
        lambda host, port, user, pw: "fetched-token",
    )
    ap = ded.build_arg_parser()
    args = ap.parse_args([])
    tok, source = ded.resolve_postmark_token(args, sudo_password="pw")
    assert tok == "fetched-token"
    assert "auto-fetch" in source


def test_resolve_postmark_token_returns_none_without_sources(monkeypatch):
    """No --postmark-token, no env, no --sudo → no token, main errors cleanly."""
    monkeypatch.delenv("FELLOWS_POSTMARK_TOKEN", raising=False)
    ap = ded.build_arg_parser()
    args = ap.parse_args([])
    tok, source = ded.resolve_postmark_token(args, sudo_password=None)
    assert tok is None


def test_fetch_postmark_token_from_prod_parses_quoted_and_unquoted(monkeypatch):
    """Env-file parser handles both KEY=val and KEY='val' and KEY=\"val\"."""
    cases = [
        ('FELLOWS_POSTMARK_TOKEN=abc123\nFELLOWS_MAIL_FROM=admin@x\n', "abc123"),
        ('FELLOWS_POSTMARK_TOKEN="abc123"\n', "abc123"),
        ("FELLOWS_POSTMARK_TOKEN='abc123'\n", "abc123"),
        ("FELLOWS_SESSION_SECRET=ignore\nFELLOWS_POSTMARK_TOKEN=tkn\n", "tkn"),
    ]
    for stdout, expected in cases:
        class _R:
            returncode = 0
        _R.stdout = stdout
        _R.stderr = ""
        monkeypatch.setattr(ded.subprocess, "run", lambda *a, **kw: _R())
        assert ded.fetch_postmark_token_from_prod("h", "22", "u", "pw") == expected


def test_fetch_postmark_token_from_prod_raises_when_missing(monkeypatch):
    class _R:
        returncode = 0
        stdout = "FELLOWS_SESSION_SECRET=only-this\n"
        stderr = ""

    monkeypatch.setattr(ded.subprocess, "run", lambda *a, **kw: _R())
    import pytest
    with pytest.raises(RuntimeError, match="not found"):
        ded.fetch_postmark_token_from_prod("h", "22", "u", "pw")


def test_sudo_default_is_on():
    """No flag → args.sudo is True (default-on; --no-sudo opts out).

    Zero-flag happy path needs sudo: the operator isn't in systemd-journal
    on prod, so journalctl silently returns empty otherwise.
    """
    ap = ded.build_arg_parser()
    args = ap.parse_args([])
    assert args.sudo is True


def test_sudo_no_sudo_flag_opts_out():
    ap = ded.build_arg_parser()
    args = ap.parse_args(["--no-sudo"])
    assert args.sudo is False


def test_fetch_allowlist_from_prod_parses_and_normalises(monkeypatch):
    class _R:
        returncode = 0
        stdout = '{"hashes": ["AABBCC", "ddEEff", "1234"]}'
        stderr = ""

    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _R()

    monkeypatch.setattr(ded.subprocess, "run", fake_run)
    allow = ded.fetch_allowlist_from_prod("h", "22", "u")
    # lowercased for consistent comparison with sha256().hexdigest()
    assert allow == {"aabbcc", "ddeeff", "1234"}
    # No sudo involved — must use BatchMode=yes to fail fast on auth prompts.
    assert "BatchMode=yes" in " ".join(captured["cmd"])
    # And we didn't smuggle sudo into the remote command.
    assert "sudo" not in captured["cmd"][-1]


def test_fetch_allowlist_from_prod_raises_on_ssh_failure(monkeypatch):
    class _R:
        returncode = 255
        stdout = ""
        stderr = "Permission denied"

    monkeypatch.setattr(ded.subprocess, "run", lambda *a, **kw: _R())
    import pytest
    with pytest.raises(RuntimeError, match="exit 255"):
        ded.fetch_allowlist_from_prod("h", "22", "u")


def test_fetch_allowlist_from_prod_raises_on_bad_json(monkeypatch):
    class _R:
        returncode = 0
        stdout = "not json {"
        stderr = ""

    monkeypatch.setattr(ded.subprocess, "run", lambda *a, **kw: _R())
    import pytest
    with pytest.raises(RuntimeError, match="parse failed"):
        ded.fetch_allowlist_from_prod("h", "22", "u")


def test_check_allowlist_hit_and_miss():
    allow = {
        ded.hash_email("a@example.com"),
        ded.hash_email("b@example.com"),
    }
    hit = ded.check_allowlist("a@example.com", allow)
    assert hit["hit"] is True
    assert hit["allowlist_size"] == 2
    assert hit["hash"] == ded.hash_email("a@example.com")
    miss = ded.check_allowlist("c@example.com", allow)
    assert miss["hit"] is False


def test_format_report_surfaces_allowlist_miss_as_root_cause():
    """When --email is passed and the hash isn't on the list, the report
    must explicitly explain why no events showed up — otherwise the user
    chases 'is the debug script broken?' instead of 'is the email
    allowlisted?'."""
    chk = {
        "email": "c@example.com",
        "hash": "a" * 64,
        "hit": False,
        "allowlist_size": 268,
    }
    out = ded.format_report(
        [], {}, {"host": "h", "since": "s", "filter_desc": "email hash aaaa…"},
        allowlist_check=chk,
    )
    assert "MISS" in out
    assert "268-entry" in out
    assert "anti-enumeration" in out


def test_format_report_allowlist_hit_does_not_misleadingly_explain_empty_events():
    chk = {
        "email": "a@example.com",
        "hash": "b" * 64,
        "hit": True,
        "allowlist_size": 268,
    }
    out = ded.format_report(
        [], {}, {"host": "h", "since": "s", "filter_desc": None},
        allowlist_check=chk,
    )
    assert "HIT" in out
    # The "explains empty" prose must NOT appear on a hit — empty events with
    # a hit means something else is wrong (not the allowlist).
    assert "anti-enumeration" not in out


def test_fetch_postmark_token_from_prod_raises_on_ssh_failure(monkeypatch):
    class _R:
        returncode = 255
        stdout = ""
        stderr = "Permission denied"

    monkeypatch.setattr(ded.subprocess, "run", lambda *a, **kw: _R())
    import pytest
    with pytest.raises(RuntimeError, match="exit 255"):
        ded.fetch_postmark_token_from_prod("h", "22", "u", "pw")
