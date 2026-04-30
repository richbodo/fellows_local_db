"""Unit tests for deploy/magic_link_auth.py (no HTTP)."""
import base64
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "deploy"))

import magic_link_auth as ml  # noqa: E402


def test_sha256_email_normalizes():
    a = ml.sha256_email("  Test@Example.COM  ")
    b = ml.sha256_email("test@example.com")
    assert a == b
    assert len(a) == 64


def test_session_roundtrip_v2_carries_token_issued_at(monkeypatch):
    monkeypatch.setenv("FELLOWS_SESSION_SECRET", "unit-test-secret")
    sec = ml.session_secret_bytes()
    assert sec
    tia = int(time.time()) - 60
    v = ml.sign_session_value(sec, token_issued_at=tia)
    payload = ml.verify_session_value(v, sec)
    assert payload is not None
    assert payload["token_issued_at"] == tia
    assert ml.verify_session_value(v + "x", sec) is None


def test_verify_rejects_v1_cookies(monkeypatch):
    """Old v1 cookies must no longer verify — forces clean re-login on deploy."""
    monkeypatch.setenv("FELLOWS_SESSION_SECRET", "unit-test-secret")
    sec = ml.session_secret_bytes()
    import hmac as _hmac
    import hashlib as _hashlib

    exp = int(time.time()) + 3600
    payload = f"{exp}:deadbeef".encode("utf-8")
    sig = _hmac.new(sec, payload, _hashlib.sha256).hexdigest()
    v1_cookie = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=") + "." + sig

    assert ml.verify_session_value(v1_cookie, sec) is None


def test_install_recently_allowed_window_math():
    now = 1_000_000.0
    # Token just issued → inside the window.
    assert ml.install_recently_allowed(now - 10, now=now) is True
    # Token issued exactly at the boundary (30 min) → outside.
    assert ml.install_recently_allowed(now - ml.INSTALL_WINDOW, now=now) is False
    # Token issued 5 min ago → inside.
    assert ml.install_recently_allowed(now - 300, now=now) is True
    # None token (no session, or pre-v2 cookie) → never allowed.
    assert ml.install_recently_allowed(None, now=now) is False


def test_consume_token_distinguishes_invalid_expired_ok(monkeypatch):
    # Reset state in case other unit tests leaked into the module-level
    # AuthState (no autouse fixture here).
    with ml.AuthState.lock:
        ml.AuthState.tokens.clear()
        ml.AuthState.consumed.clear()

    # Unknown token → invalid.
    r = ml.consume_token("no-such-token-1234567890")
    assert r == {"status": "invalid"}

    # Expire path: inject a token with past expiry and consume it.
    with ml.AuthState.lock:
        ml.AuthState.tokens["expired-token"] = time.time() - 10
    r = ml.consume_token("expired-token")
    assert r == {"status": "expired"}

    # Happy path: issue then consume; check issued_at is populated.
    tok = ml.issue_token()
    r = ml.consume_token(tok)
    assert r["status"] == "ok"
    assert "issued_at" in r
    # Second consume within the grace window is ok with the original
    # issued_at (M3) — see test_consume_within_grace_window_returns_ok
    # below for the dedicated coverage.
    r2 = ml.consume_token(tok)
    assert r2["status"] == "ok"
    assert r2["issued_at"] == r["issued_at"]


def test_consume_within_grace_window_returns_ok_with_original_issued_at():
    """M3: a second consume within GRACE_WINDOW seconds returns ok with
    the issued_at captured at first consume (so the resulting session
    cookie carries the same install-window anchor as the first one)."""
    with ml.AuthState.lock:
        ml.AuthState.tokens.clear()
        ml.AuthState.consumed.clear()
    tok = ml.issue_token()
    r1 = ml.consume_token(tok)
    assert r1["status"] == "ok"
    # Re-consume inside the window: ok, same issued_at.
    r2 = ml.consume_token(tok)
    assert r2["status"] == "ok"
    assert r2["issued_at"] == r1["issued_at"]


def test_consume_after_grace_window_returns_invalid():
    """M3: outside the window the re-consume reverts to invalid. Rewind
    the consumed record's consumed_at rather than sleeping."""
    with ml.AuthState.lock:
        ml.AuthState.tokens.clear()
        ml.AuthState.consumed.clear()
    tok = ml.issue_token()
    r1 = ml.consume_token(tok)
    assert r1["status"] == "ok"
    with ml.AuthState.lock:
        rec = ml.AuthState.consumed.get(tok)
        assert rec is not None
        rec["consumed_at"] = time.time() - (ml.GRACE_WINDOW + 1)
    r2 = ml.consume_token(tok)
    assert r2 == {"status": "invalid"}
    # Opportunistic drop on miss: the consumed record should be gone now.
    with ml.AuthState.lock:
        assert tok not in ml.AuthState.consumed


def test_cleanup_stale_tokens_drops_expired_consumed_entries():
    """cleanup_stale_tokens drops both past-TTL live tokens AND consumed
    records past the grace window. Bounded memory across long uptimes."""
    with ml.AuthState.lock:
        ml.AuthState.tokens.clear()
        ml.AuthState.consumed.clear()
    # One stale live token, one stale consumed record, one fresh consumed record.
    now = time.time()
    with ml.AuthState.lock:
        ml.AuthState.tokens["stale-live"] = now - 10
        ml.AuthState.consumed["stale-consumed"] = {
            "issued_at": now - 200,
            "consumed_at": now - (ml.GRACE_WINDOW + 5),
        }
        ml.AuthState.consumed["fresh-consumed"] = {
            "issued_at": now - 5,
            "consumed_at": now - 5,
        }
    ml.cleanup_stale_tokens()
    with ml.AuthState.lock:
        assert "stale-live" not in ml.AuthState.tokens
        assert "stale-consumed" not in ml.AuthState.consumed
        assert "fresh-consumed" in ml.AuthState.consumed


def test_clear_session_cookie_line_has_max_age_0():
    class H:
        def get(self, key, default=None):
            return default

    line = ml.clear_session_cookie_line(H())
    assert ml.SESSION_COOKIE + "=" in line
    assert "Max-Age=0" in line
    assert "Path=/" in line


def test_allowlist_load(tmp_path):
    p = tmp_path / "allowed_emails.json"
    p.write_text('{"hashes": ["aa", "bb"]}', encoding="utf-8")
    s = ml.load_allowlist(tmp_path)
    assert s == {"aa", "bb"}


def test_gated_paths():
    assert ml.is_gated_api_path("/api/fellows")
    assert not ml.is_gated_api_path("/api/auth/status")
    assert not ml.is_gated_api_path("/api/debug/diagnostics")
    assert ml.is_protected_data_path("/fellows.db")
    assert ml.is_protected_data_path("/images/foo.jpg")


def test_build_postmark_body_default_sender_is_admin(monkeypatch):
    """Default FELLOWS_MAIL_FROM is admin@… (no-reply retired per Postmark guidance)."""
    monkeypatch.delenv("FELLOWS_MAIL_FROM", raising=False)
    monkeypatch.delenv("FELLOWS_REPLY_TO", raising=False)
    body = ml.build_postmark_body("user@example.com", "https://fellows.globaldonut.com/#/unlock/tok")
    assert body["From"] == "admin@fellows.globaldonut.com"
    assert body["To"] == "user@example.com"
    assert body["MessageStream"] == "outbound"
    assert "expires in 30 minutes" in body["Subject"]
    assert "30 minutes" in body["TextBody"]
    assert "30 minutes" in body["HtmlBody"]
    # Reply-To absent when env var unset — Postmark defaults reply to From.
    assert "ReplyTo" not in body


def test_build_postmark_body_reply_to_env_wins(monkeypatch):
    """FELLOWS_REPLY_TO becomes the ReplyTo header when set."""
    monkeypatch.setenv("FELLOWS_MAIL_FROM", "admin@fellows.globaldonut.com")
    monkeypatch.setenv("FELLOWS_REPLY_TO", "richbodo+fellows@gmail.com")
    body = ml.build_postmark_body("u@x.com", "https://example/#/unlock/tok")
    assert body["From"] == "admin@fellows.globaldonut.com"
    assert body["ReplyTo"] == "richbodo+fellows@gmail.com"


def test_build_postmark_body_reply_to_empty_string_is_ignored(monkeypatch):
    """Empty FELLOWS_REPLY_TO is treated as unset, not as an empty Reply-To header."""
    monkeypatch.setenv("FELLOWS_REPLY_TO", "   ")
    body = ml.build_postmark_body("u@x.com", "https://example/#/unlock/tok")
    assert "ReplyTo" not in body


def test_build_postmark_body_mail_from_override(monkeypatch):
    """FELLOWS_MAIL_FROM overrides the default."""
    monkeypatch.setenv("FELLOWS_MAIL_FROM", "hello@fellows.globaldonut.com")
    body = ml.build_postmark_body("u@x.com", "https://example/#/unlock/tok")
    assert body["From"] == "hello@fellows.globaldonut.com"
