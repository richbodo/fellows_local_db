"""Round-trip tests for `POST /api/client-errors` against deploy/server.py.

Companion to ``tests/test_client_error_sanitizer.py`` (which pins the
sanitizer's pure functions). Here we drive the actual HTTP endpoint:
unauthenticated POST, sanitization in the handler path, rate-limit, body
cap, structured journald event emission. The ``deploy_server`` fixture
(in ``tests/conftest.py``) gives us the same in-process server the
auth round-trip suite uses.

The structured ``event=client_error`` line is what
``scripts/prod_stats.py`` parses, so these tests indirectly guard the
entire `just prod-errors` triage workflow.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import contextmanager
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest


def _conn(handle):
    parsed = urlparse(handle["base_url"])
    return HTTPConnection(parsed.hostname, parsed.port, timeout=3)


def _post_raw(handle, path, body_bytes, content_type="application/json"):
    conn = _conn(handle)
    conn.request(
        "POST",
        path,
        body=body_bytes,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body_bytes)),
        },
    )
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), raw


def _post_json(handle, path, body):
    raw = json.dumps(body).encode("utf-8")
    return _post_raw(handle, path, raw)


@contextmanager
def _captured_stderr():
    """Capture sys.stderr writes from the in-process deploy server.

    The fixture-spawned server runs in a daemon thread but writes its
    structured events via ``print(..., file=sys.stderr)``. Patching
    ``sys.stderr`` for the duration of the request lets the test inspect
    what landed in journald-equivalent output. (No journald exists in CI
    — this is the test surrogate for it.)
    """
    buf = io.StringIO()
    saved = sys.stderr
    sys.stderr = buf
    try:
        yield buf
    finally:
        sys.stderr = saved


@pytest.fixture(autouse=True)
def _reset_rate_buckets(deploy_server):
    """Clear the rate-limit dict between tests so each one runs in
    isolation. The bucket is process-global (deploy/magic_link_auth.py
    AuthState), so a previous test's leftover entries can starve a
    later test's rate-limit allowance."""
    state = deploy_server["auth_state"]
    state.rate_buckets.clear()


# ---- happy path ---------------------------------------------------------

def test_client_errors_204_and_logs_structured_event(deploy_server):
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
    }
    with _captured_stderr() as err:
        status, _, raw = _post_json(deploy_server, "/api/client-errors", body)
    assert status == 204
    assert raw == b""
    log = err.getvalue()
    assert '"event": "client_error"' in log
    # client_ip_prefix is populated (12 hex of sha256(loopback IP)).
    assert '"client_ip_prefix"' in log
    # Sanitized payload made it through.
    assert "GET /api/fellows" in log
    assert '"build": "abc1234' in log


def test_client_errors_redacts_email_in_msg(deploy_server):
    body = {
        "events": [{"kind": "http", "msg": "POST blew up for me@example.com"}],
    }
    with _captured_stderr() as err:
        status, _, _ = _post_json(deploy_server, "/api/client-errors", body)
    assert status == 204
    log = err.getvalue()
    assert "me@example.com" not in log
    assert "<email>" in log


def test_client_errors_redacts_slug_and_token_in_route(deploy_server):
    tok = "deadbeef" * 8
    body = {
        "events": [{"kind": "http", "msg": "ok"}],
        "route": f"#/unlock/{tok}",
    }
    with _captured_stderr() as err:
        status, _, _ = _post_json(deploy_server, "/api/client-errors", body)
    assert status == 204
    log = err.getvalue()
    assert tok not in log
    # Slug variant also redacted.
    body2 = {
        "events": [{"kind": "http", "msg": "ok"}],
        "route": "#/fellow/secret-slug",
    }
    with _captured_stderr() as err2:
        status2, _, _ = _post_json(deploy_server, "/api/client-errors", body2)
    assert status2 == 204
    assert "secret-slug" not in err2.getvalue()


# ---- unauthenticated by design -----------------------------------------

def test_client_errors_does_not_require_session_cookie(deploy_server):
    """The whole point is to capture reports from users who failed auth.
    Posting without any cookie must succeed (204) and emit a log line."""
    with _captured_stderr() as err:
        status, _, _ = _post_json(
            deploy_server, "/api/client-errors",
            {"events": [{"kind": "http", "msg": "no cookie here"}]},
        )
    assert status == 204
    assert '"event": "client_error"' in err.getvalue()


# ---- shape rejection ---------------------------------------------------

def test_client_errors_silently_drops_unrecoverable_shape(deploy_server):
    """Non-dict body → 204, no log line. The 204-on-everything posture is
    the anti-oracle stance: we don't help a probing attacker tell shapes
    apart."""
    with _captured_stderr() as err:
        status, _, _ = _post_raw(
            deploy_server, "/api/client-errors", b'"just a string"'
        )
    assert status == 204
    assert '"event": "client_error"' not in err.getvalue()


def test_client_errors_silently_drops_missing_events_array(deploy_server):
    with _captured_stderr() as err:
        status, _, _ = _post_json(deploy_server, "/api/client-errors", {"ua": "x"})
    assert status == 204
    assert '"event": "client_error"' not in err.getvalue()


def test_client_errors_silently_drops_invalid_json(deploy_server):
    """Invalid JSON → 400 (do_POST handles it before our handler). This
    exists pre-existing and we don't override it; documenting the
    behavior so a future refactor doesn't regress quietly."""
    status, _, _ = _post_raw(
        deploy_server, "/api/client-errors", b"{not json"
    )
    assert status == 400


def test_client_errors_drops_payload_with_only_invalid_events(deploy_server):
    """Events with kind not in the accept-list get filtered out. If
    nothing usable remains, no log line is emitted (still 204)."""
    body = {"events": [{"kind": "exfiltrate", "msg": "evil"}]}
    with _captured_stderr() as err:
        status, _, _ = _post_json(deploy_server, "/api/client-errors", body)
    assert status == 204
    assert '"event": "client_error"' not in err.getvalue()


# ---- abuse mitigations -------------------------------------------------

def test_client_errors_413_when_body_too_large(deploy_server):
    big = b'{"events":[{"kind":"http","msg":"' + b"x" * (16 * 1024 + 50) + b'"}]}'
    with _captured_stderr() as err:
        status, _, _ = _post_raw(deploy_server, "/api/client-errors", big)
    assert status == 413
    assert '"event": "client_error"' not in err.getvalue()


def test_client_errors_rate_limit_drops_4th_post_silently(deploy_server):
    """Per-IP rate limit (3 in window). The 4th POST returns 204 like
    the others but emits no log — anti-enumeration parity with
    /api/send-unlock at deploy/server.py:_handle_send_unlock."""
    body = {"events": [{"kind": "http", "msg": "thump"}]}
    log_count_before = 0
    log_count_after_three = 0
    log_count_after_four = 0
    with _captured_stderr() as err:
        for _ in range(3):
            status, _, _ = _post_json(deploy_server, "/api/client-errors", body)
            assert status == 204
        log_count_after_three = err.getvalue().count('"event": "client_error"')
        # 4th attempt: still 204, but no new log line.
        status, _, _ = _post_json(deploy_server, "/api/client-errors", body)
        assert status == 204
        log_count_after_four = err.getvalue().count('"event": "client_error"')
    assert log_count_after_three == 3
    assert log_count_after_four == 3  # rate-limited drop, no new log


# ---- last_submit correlation handle -----------------------------------

def test_client_errors_preserves_valid_last_submit_hash_prefix(deploy_server):
    """The 12-hex prefix is the join key into event=send_unlock_email's
    `email_hash_prefix`. The maintainer needs it intact to grep
    journald."""
    body = {
        "events": [{"kind": "http", "msg": "ok"}],
        "lastSubmitHashPrefix": "ab12cd34ef56",
    }
    with _captured_stderr() as err:
        status, _, _ = _post_json(deploy_server, "/api/client-errors", body)
    assert status == 204
    assert '"lastSubmitHashPrefix": "ab12cd34ef56"' in err.getvalue()


def test_client_errors_drops_garbage_last_submit_hash_prefix(deploy_server):
    body = {
        "events": [{"kind": "http", "msg": "ok"}],
        "lastSubmitHashPrefix": "DROP TABLE users",
    }
    with _captured_stderr() as err:
        status, _, _ = _post_json(deploy_server, "/api/client-errors", body)
    assert status == 204
    assert "DROP TABLE" not in err.getvalue()
    assert '"lastSubmitHashPrefix"' not in err.getvalue()
