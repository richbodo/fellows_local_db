"""End-to-end round-trip tests for deploy/server.py magic-link auth (issue #18).

The dev server (app/server.py) has no auth, so the directory of e2e tests
under tests/e2e/ exercises gate UX against a server that returns
``authEnabled: false`` and never actually issues tokens. These tests fill the
gap: they spawn ``deploy/server.py`` in-process with auth on, a tmp dist root,
and a stubbed Postmark sender, then exercise the real send → verify → cookie →
gated-API path that PR #16 (standalone unlock) and PR #17 (silent send-unlock)
broke without anyone noticing.

The ``deploy_server`` fixture lives in ``tests/conftest.py``.
"""

from __future__ import annotations

import json
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest


def _conn(handle):
    parsed = urlparse(handle["base_url"])
    return HTTPConnection(parsed.hostname, parsed.port, timeout=3)


def _post_json(handle, path, body):
    conn = _conn(handle)
    payload = json.dumps(body).encode("utf-8")
    conn.request(
        "POST",
        path,
        body=payload,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        },
    )
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), (json.loads(raw) if raw else {})


def _get(handle, path, cookie=None):
    conn = _conn(handle)
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), raw


def _set_cookie_header(headers):
    return headers.get("Set-Cookie") or headers.get("set-cookie") or ""


def _extract_session_cookie(headers):
    """Return the ``fellows_session=<value>`` portion of Set-Cookie, or None."""
    sc = _set_cookie_header(headers)
    if not sc:
        return None
    head = sc.split(";", 1)[0].strip()
    if not head.startswith("fellows_session="):
        return None
    return head


def _token_from_url(magic_url):
    return magic_url.rsplit("/#/unlock/", 1)[-1]


@pytest.fixture(autouse=True)
def _reset_auth_state(deploy_server):
    """Each test starts with empty rate buckets, no live tokens, no
    consumed-token grace records, no registered sessions, and no
    recorded sends."""
    state = deploy_server["auth_state"]
    with state.lock:
        state.tokens.clear()
        state.consumed.clear()
        state.rate_buckets.clear()
        state.sessions.clear()
    deploy_server["sent"].clear()


# --- Item 1: unauthenticated landing -------------------------------------


def test_directory_api_is_403_without_session(deploy_server):
    status, headers, _ = _get(deploy_server, "/api/fellows")
    assert status == 403
    assert _extract_session_cookie(headers) is None


def test_auth_status_reports_unauthenticated_when_cookieless(deploy_server):
    status, _, raw = _get(deploy_server, "/api/auth/status")
    assert status == 200
    body = json.loads(raw)
    assert body["authEnabled"] is True
    assert body["authenticated"] is False
    assert body["hasSessionCookie"] is False


# --- Item 2: send-unlock round-trip --------------------------------------


def test_send_unlock_for_allowlisted_email_invokes_sender(deploy_server):
    status, _, body = _post_json(
        deploy_server, "/api/send-unlock", {"email": deploy_server["test_email"]}
    )
    assert status == 200
    assert body == {"sent": True}
    assert len(deploy_server["sent"]) == 1
    record = deploy_server["sent"][0]
    assert record["to"] == deploy_server["test_email"]
    assert "/#/unlock/" in record["url"]
    # Token in the magic-link URL is 64 hex chars (secrets.token_hex(32)).
    token = _token_from_url(record["url"])
    assert len(token) == 64
    assert all(c in "0123456789abcdef" for c in token)


def test_send_unlock_for_unknown_email_does_not_invoke_sender(deploy_server):
    """Anti-enumeration: response is identical, sender never runs."""
    status, _, body = _post_json(
        deploy_server, "/api/send-unlock", {"email": "stranger@example.com"}
    )
    assert status == 200
    assert body == {"sent": True}
    assert deploy_server["sent"] == []


def test_send_unlock_with_malformed_email_does_not_invoke_sender(deploy_server):
    status, _, body = _post_json(
        deploy_server, "/api/send-unlock", {"email": "not-an-email"}
    )
    assert status == 200
    assert body == {"sent": True}
    assert deploy_server["sent"] == []


# --- Item 3: token verification ------------------------------------------


def test_verify_token_sets_session_cookie_with_required_attributes(deploy_server):
    _post_json(
        deploy_server, "/api/send-unlock", {"email": deploy_server["test_email"]}
    )
    token = _token_from_url(deploy_server["sent"][-1]["url"])
    status, headers, body = _post_json(
        deploy_server, "/api/verify-token", {"token": token}
    )
    assert status == 200
    assert body == {"ok": True}
    sc = _set_cookie_header(headers)
    assert "fellows_session=" in sc
    assert "HttpOnly" in sc
    assert "SameSite=Strict" in sc
    assert "Path=/" in sc
    # Secure is environment-dependent: the localhost gate in
    # should_use_secure_cookie() (and FELLOWS_COOKIE_INSECURE=1 in this
    # fixture) suppresses it. Production sets it via the
    # X-Forwarded-Proto: https header from Caddy. Asserting it here would
    # fail-positive in the loopback test setup, so we don't.


def test_verify_token_with_unknown_token_returns_401_invalid(deploy_server):
    status, _, body = _post_json(
        deploy_server, "/api/verify-token", {"token": "0" * 64}
    )
    assert status == 401
    assert body == {"ok": False, "error": "invalid"}


def test_verify_token_with_empty_token_returns_401_invalid(deploy_server):
    status, _, body = _post_json(deploy_server, "/api/verify-token", {"token": ""})
    assert status == 401
    assert body == {"ok": False, "error": "invalid"}


def test_verify_token_reuse_within_grace_window_returns_ok(deploy_server):
    """A re-consume of the same token within ``GRACE_WINDOW`` seconds (M3
    follow-up to the Anne-Marie iOS report) returns ok again, so a bfcache
    replay or scanner pre-fetch doesn't break the legitimate user. Both
    responses end up with the same session contract: 200 ok + a fresh
    Set-Cookie carrying the original ``token_issued_at``. After the grace
    window the token reverts to ``invalid`` — see the test below."""
    _post_json(
        deploy_server, "/api/send-unlock", {"email": deploy_server["test_email"]}
    )
    token = _token_from_url(deploy_server["sent"][-1]["url"])
    s1, _, b1 = _post_json(deploy_server, "/api/verify-token", {"token": token})
    s2, _, b2 = _post_json(deploy_server, "/api/verify-token", {"token": token})
    assert s1 == 200 and b1 == {"ok": True}
    assert s2 == 200 and b2 == {"ok": True}


def test_verify_token_reuse_after_grace_window_returns_invalid(deploy_server):
    """Outside the grace window a re-consume reverts to ``invalid`` —
    re-asserts the original single-use property holds in the long run.
    We rewind the consumed record's ``consumed_at`` rather than sleeping."""
    state = deploy_server["auth_state"]
    ml = deploy_server["ml"]
    _post_json(
        deploy_server, "/api/send-unlock", {"email": deploy_server["test_email"]}
    )
    token = _token_from_url(deploy_server["sent"][-1]["url"])
    s1, _, _ = _post_json(deploy_server, "/api/verify-token", {"token": token})
    assert s1 == 200
    import time as _time

    with state.lock:
        rec = state.consumed.get(token)
        assert rec is not None
        rec["consumed_at"] = _time.time() - (ml.GRACE_WINDOW + 1)
    s2, _, b2 = _post_json(deploy_server, "/api/verify-token", {"token": token})
    assert s2 == 401
    assert b2 == {"ok": False, "error": "invalid"}


def test_verify_token_after_ttl_expiry_returns_401_expired(deploy_server):
    """Past-TTL tokens fail with the distinct ``expired`` error so the gate
    can render the right banner. We inject a stale token directly into
    AuthState rather than waiting 30 minutes."""
    state = deploy_server["auth_state"]
    expired_token = "deadbeef" * 8  # 64 hex chars
    with state.lock:
        # exp is ``time.time() + TOKEN_TTL`` at issue, so a value 10s in the
        # past makes the token's ``exp < now`` branch fire in consume_token.
        import time as _time

        state.tokens[expired_token] = _time.time() - 10
    status, _, body = _post_json(
        deploy_server, "/api/verify-token", {"token": expired_token}
    )
    assert status == 401
    assert body == {"ok": False, "error": "expired"}


# --- Item 4: gated API after cookie --------------------------------------


def test_directory_api_succeeds_with_session_cookie_and_fails_without(deploy_server):
    _post_json(
        deploy_server, "/api/send-unlock", {"email": deploy_server["test_email"]}
    )
    token = _token_from_url(deploy_server["sent"][-1]["url"])
    _, vh, _ = _post_json(deploy_server, "/api/verify-token", {"token": token})
    cookie = _extract_session_cookie(vh)
    assert cookie is not None

    # With cookie: 200 + non-empty list (the fixture seeds a copy of the dev
    # fellows.db, which has 515 rows on the canonical Knack rebuild).
    status, _, raw = _get(deploy_server, "/api/fellows", cookie=cookie)
    assert status == 200
    fellows = json.loads(raw)
    assert isinstance(fellows, list)
    assert len(fellows) > 0

    # Without cookie: still 403, even after another request had a valid one.
    status, _, _ = _get(deploy_server, "/api/fellows")
    assert status == 403


def test_protected_image_path_is_403_without_session(deploy_server):
    """Per is_protected_data_path, /images/* is gated alongside /fellows.db."""
    status, _, _ = _get(deploy_server, "/images/anyone.jpg")
    assert status == 403


# --- Item 6: rate limit --------------------------------------------------


def test_send_unlock_rate_limit_silently_drops_after_three(deploy_server):
    """Per RATE_MAX=3 in magic_link_auth: the 4th call still returns 200
    {sent:true} (anti-enum), but Postmark is not invoked. This is the silent
    failure mode that motivated the smoke-check hardening in PR #17."""
    email = deploy_server["test_email"]
    for _ in range(3):
        s, _, b = _post_json(deploy_server, "/api/send-unlock", {"email": email})
        assert s == 200 and b == {"sent": True}
    assert len(deploy_server["sent"]) == 3

    s4, _, b4 = _post_json(deploy_server, "/api/send-unlock", {"email": email})
    assert s4 == 200 and b4 == {"sent": True}  # response shape unchanged
    assert len(deploy_server["sent"]) == 3  # but no fourth send actually happened
