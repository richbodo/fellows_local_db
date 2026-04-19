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
    """End-to-end JSON path: mock ssh_journal, verify JSON structure."""
    monkeypatch.setattr(
        ded,
        "ssh_journal",
        lambda host, port, user, since: _journal_envelope(_send_event_json()),
    )
    rc = ded.main(["--json", "--since", "1 hour ago"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["host"] == ded.DEFAULT_HOST
    assert data["since"] == "1 hour ago"
    assert len(data["events"]) == 1
    assert data["events"][0]["result"] == "sent"
    assert data["postmark"] == {}
