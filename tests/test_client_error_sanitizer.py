"""Unit tests for deploy/client_error_sanitizer.py (no HTTP).

Anything that fails here is a privacy regression: the sanitizer is the
boundary between user-supplied diagnostic blobs and journald, and the
server's `_handle_client_errors` trusts whatever the sanitizer returns.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "deploy"))

import client_error_sanitizer as ces  # noqa: E402


# ---- redact_email -------------------------------------------------------

def test_redact_email_replaces_simple_address():
    assert ces.redact_email("hi foo@bar.com bye") == "hi <email> bye"


def test_redact_email_handles_subdomain_and_plus_tag():
    assert ces.redact_email("me+tag@mail.example.co.uk submitted") == "<email> submitted"


def test_redact_email_leaves_at_mentions_alone():
    # No top-level domain shape → not an email. Stack trace text like
    # "user @auth_decorator returned 401" must not be flagged.
    assert ces.redact_email("@auth_decorator returned 401") == "@auth_decorator returned 401"


def test_redact_email_handles_multiple_in_one_string():
    out = ces.redact_email("a@b.io / c@d.org")
    assert out == "<email> / <email>"


def test_redact_email_non_string_returns_empty():
    assert ces.redact_email(None) == ""
    assert ces.redact_email(42) == ""


# ---- redact_route -------------------------------------------------------

def test_redact_route_strips_query_string():
    assert ces.redact_route("/api/fellows?full=1") == "/api/fellows"


def test_redact_route_strips_query_in_hash_route():
    # The query lands AFTER the hash route in a typical bug report URL.
    assert (
        ces.redact_route("https://x/#/groups/3?ref=abc")
        == "https://x/#/groups/3"
    )


def test_redact_route_redacts_fellow_slug():
    assert (
        ces.redact_route("#/fellow/jane-doe")
        == "#/fellow/<redacted>"
    )


def test_redact_route_redacts_unlock_token():
    """Tokens in the URL are catastrophic to leak — they grant a session."""
    tok = "deadbeef" * 8
    assert (
        ces.redact_route(f"#/unlock/{tok}")
        == "#/unlock/<redacted>"
    )


def test_redact_route_keeps_group_id():
    """Group IDs are integers, shared among fellows, and high-signal for
    triage. Don't redact them."""
    assert ces.redact_route("#/groups/3/directory") == "#/groups/3/directory"


def test_redact_route_idempotent():
    once = ces.redact_route("#/fellow/jane?x=1")
    twice = ces.redact_route(once)
    assert once == twice


# ---- sanitize_text_field ------------------------------------------------

def test_sanitize_text_field_truncates_at_cap():
    long = "a" * 1000
    out = ces.sanitize_text_field(long, cap=10)
    assert len(out) == 11  # 10 chars + ellipsis
    assert out.endswith("…")


def test_sanitize_text_field_redacts_then_truncates():
    s = "send to foo@bar.com about #/fellow/secret-slug"
    out = ces.sanitize_text_field(s, cap=500)
    assert "foo@bar.com" not in out
    assert "secret-slug" not in out
    assert "<email>" in out
    assert "<redacted>" in out


# ---- sanitize_payload ---------------------------------------------------

def test_sanitize_payload_happy_path():
    body = {
        "events": [
            {"kind": "http", "ts": "2026-04-30T15:00:00Z",
             "msg": "GET /api/fellows → 404"},
        ],
        "ua": "Mozilla/5.0 (test)",
        "build": "abc1234 @ 2026-04-30T15:00:00Z",
        "route": "#/groups/3",
        "displayMode": "browser-tab",
        "online": True,
        "lastSubmitHashPrefix": "ab12cd34ef56",
    }
    out = ces.sanitize_payload(body)
    assert len(out["events"]) == 1
    assert out["events"][0]["kind"] == "http"
    assert out["ua"].startswith("Mozilla")
    assert out["displayMode"] == "browser-tab"
    assert out["online"] is True
    assert out["lastSubmitHashPrefix"] == "ab12cd34ef56"


def test_sanitize_payload_drops_email_in_msg():
    body = {"events": [{"kind": "http", "msg": "POST failed for me@example.com"}]}
    out = ces.sanitize_payload(body)
    assert "me@example.com" not in out["events"][0]["msg"]
    assert "<email>" in out["events"][0]["msg"]


def test_sanitize_payload_drops_slug_in_route():
    body = {
        "events": [{"kind": "window.error", "msg": "boom"}],
        "route": "#/fellow/secret-slug",
    }
    out = ces.sanitize_payload(body)
    assert "secret-slug" not in out["route"]
    assert out["route"] == "#/fellow/<redacted>"


def test_sanitize_payload_drops_unlock_token_in_route():
    tok = "feedface" * 8
    body = {
        "events": [{"kind": "http", "msg": "verify failed"}],
        "route": f"#/unlock/{tok}",
    }
    out = ces.sanitize_payload(body)
    assert tok not in out["route"]


def test_sanitize_payload_drops_unknown_event_kind():
    body = {"events": [{"kind": "admin_command", "msg": "drop tables"}]}
    out = ces.sanitize_payload(body)
    # Unknown kind → event filtered out entirely. No exception.
    assert out["events"] == []


def test_sanitize_payload_accepts_install_kind():
    """Install-funnel telemetry rides the same /api/client-errors sink as
    the existing kinds. The privacy boundary (free-text sanitizer on
    msg/extra) is the same; adding the kind to the allowlist doesn't
    widen what a caller can put in journald."""
    body = {"events": [
        {"kind": "install", "msg": "before_prompt_fired"},
        {"kind": "install", "msg": "outcome_accepted", "extra": "android"},
        {"kind": "install", "msg": "use_in_tab_clicked"},
    ]}
    out = ces.sanitize_payload(body)
    assert len(out["events"]) == 3
    assert all(e["kind"] == "install" for e in out["events"])
    assert out["events"][1]["extra"] == "android"


def test_sanitize_payload_accepts_worker_kind():
    """Worker spawn / init-handshake outcomes ride the same sink so the
    operator can grep journald for `event=client_error` lines with
    `"kind": "worker"`. Same free-text sanitization as other kinds."""
    body = {"events": [
        {"kind": "worker", "msg": "spawn_failed", "extra": "init timed out"},
        {"kind": "worker", "msg": "spawn_ok", "extra": "rpc=1 schema=1"},
    ]}
    out = ces.sanitize_payload(body)
    assert len(out["events"]) == 2
    assert all(e["kind"] == "worker" for e in out["events"])
    assert out["events"][0]["msg"] == "spawn_failed"
    assert out["events"][1]["extra"] == "rpc=1 schema=1"


def test_sanitize_payload_install_kind_still_redacts_email_in_msg():
    """The kind allowlist doesn't bypass the email-redaction rule on
    free-text fields. A buggy caller that tries to send the user's
    email in an install event still gets it scrubbed server-side."""
    body = {"events": [
        {"kind": "install", "msg": "outcome_accepted by me@example.com"},
    ]}
    out = ces.sanitize_payload(body)
    assert "me@example.com" not in out["events"][0]["msg"]
    assert "<email>" in out["events"][0]["msg"]


def test_sanitize_payload_caps_event_count():
    events = [{"kind": "http", "msg": f"e{i}"} for i in range(50)]
    out = ces.sanitize_payload({"events": events})
    assert len(out["events"]) == ces.MAX_EVENTS


def test_sanitize_payload_caps_msg_length():
    body = {"events": [{"kind": "http", "msg": "x" * 5000}]}
    out = ces.sanitize_payload(body)
    assert len(out["events"][0]["msg"]) <= ces.MAX_MSG_LEN + 1  # +1 for ellipsis


def test_sanitize_payload_drops_unknown_top_level_keys():
    body = {
        "events": [{"kind": "http", "msg": "ok"}],
        "secret_field": "ignored",
        "cookie_jar": "ignored",
    }
    out = ces.sanitize_payload(body)
    assert "secret_field" not in out
    assert "cookie_jar" not in out


def test_sanitize_payload_rejects_non_dict():
    import pytest
    with pytest.raises(ValueError):
        ces.sanitize_payload("not a dict")
    with pytest.raises(ValueError):
        ces.sanitize_payload([{"events": []}])


def test_sanitize_payload_rejects_missing_events_array():
    import pytest
    with pytest.raises(ValueError):
        ces.sanitize_payload({"ua": "x"})
    with pytest.raises(ValueError):
        ces.sanitize_payload({"events": "not a list"})


def test_sanitize_payload_drops_invalid_hash_prefix():
    body = {
        "events": [{"kind": "http", "msg": "ok"}],
        "lastSubmitHashPrefix": "not-hex-12-chars-and-too-long",
    }
    out = ces.sanitize_payload(body)
    assert "lastSubmitHashPrefix" not in out


def test_sanitize_payload_drops_invalid_display_mode():
    body = {
        "events": [{"kind": "http", "msg": "ok"}],
        "displayMode": "fullscreen",
    }
    out = ces.sanitize_payload(body)
    assert "displayMode" not in out


def test_sanitize_payload_truncates_extra():
    body = {
        "events": [{"kind": "window.error", "msg": "boom",
                    "extra": "x" * 1000}],
    }
    out = ces.sanitize_payload(body)
    assert len(out["events"][0]["extra"]) <= ces.MAX_EXTRA_LEN + 1


def test_sanitize_payload_redacts_email_inside_extra():
    body = {
        "events": [{"kind": "window.error", "msg": "boom",
                    "extra": "stack mentions foo@bar.com"}],
    }
    out = ces.sanitize_payload(body)
    assert "foo@bar.com" not in out["events"][0]["extra"]
    assert "<email>" in out["events"][0]["extra"]
