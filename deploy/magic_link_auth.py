"""Magic-link authentication helpers for deploy/server.py (stdlib only).

Used when allowed_emails.json exists in the dist root and FELLOWS_SESSION_SECRET is set.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

SESSION_COOKIE = "fellows_session"
SESSION_MAX_AGE = 7 * 24 * 3600
TOKEN_TTL = 30 * 60
INSTALL_WINDOW = TOKEN_TTL  # window (from token issue) during which install landing may show
RATE_WINDOW = 3600
RATE_MAX = 3
SESSION_VERSION = "v2"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthState:
    lock = threading.Lock()
    tokens: dict[str, float] = {}
    rate_buckets: dict[str, list[float]] = {}


def load_allowlist(dist_dir: Path) -> set[str]:
    p = dist_dir / "allowed_emails.json"
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        hashes = data.get("hashes") or []
        return {str(h).lower() for h in hashes if h}
    except (json.JSONDecodeError, OSError):
        return set()


def sha256_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def is_valid_email_shape(email: str) -> bool:
    e = (email or "").strip()
    return bool(e) and len(e) <= 254 and bool(_EMAIL_RE.match(e))


def cleanup_stale_tokens() -> None:
    now = time.time()
    with AuthState.lock:
        for t, exp in list(AuthState.tokens.items()):
            if exp < now:
                del AuthState.tokens[t]


def check_rate_limit(email_hash: str) -> bool:
    """Return True if under limit (caller may send another email)."""
    now = time.time()
    with AuthState.lock:
        bucket = AuthState.rate_buckets.get(email_hash, [])
        bucket = [ts for ts in bucket if now - ts < RATE_WINDOW]
        if len(bucket) >= RATE_MAX:
            AuthState.rate_buckets[email_hash] = bucket
            return False
        bucket.append(now)
        AuthState.rate_buckets[email_hash] = bucket
        return True


def issue_token() -> str:
    cleanup_stale_tokens()
    tok = secrets.token_hex(32)
    with AuthState.lock:
        AuthState.tokens[tok] = time.time() + TOKEN_TTL
    return tok


def consume_token(tok: str) -> dict:
    """Consume a magic-link token.

    Returns one of:
      {"status": "ok", "issued_at": <epoch>} — token was valid and unexpired; caller
          should use issued_at when signing the session cookie.
      {"status": "expired"} — token existed but was past TTL. Shown to user as
          "that link expired".
      {"status": "invalid"} — token was never issued or already consumed. Shown
          to user as "that link isn't valid".
    """
    with AuthState.lock:
        exp = AuthState.tokens.pop(tok, None)
    if exp is None:
        return {"status": "invalid"}
    now = time.time()
    if exp < now:
        return {"status": "expired"}
    return {"status": "ok", "issued_at": exp - TOKEN_TTL}


def install_recently_allowed(token_issued_at: Optional[float], now: Optional[float] = None) -> bool:
    """True when the browser should still show the install landing.

    Tied to the token-issue timestamp, not the click time: a user has
    INSTALL_WINDOW seconds from the email being sent to finish installing.
    """
    if token_issued_at is None:
        return False
    if now is None:
        now = time.time()
    return (now - token_issued_at) < INSTALL_WINDOW


def send_postmark_magic_link(to_email: str, magic_url: str) -> dict:
    api_token = os.environ.get("FELLOWS_POSTMARK_TOKEN", "").strip()
    if not api_token:
        raise RuntimeError("FELLOWS_POSTMARK_TOKEN is not set")
    from_addr = os.environ.get("FELLOWS_MAIL_FROM", "noreply@fellows.globaldonut.com").strip()
    text_body = (
        "Tap or paste this link to open the install page:\n\n"
        f"{magic_url}\n\n"
        "This link will expire in 30 minutes. If it's expired, request a new one.\n"
    )
    html_body = (
        "<p>Tap or paste this link to open the install page:</p>"
        f'<p><a href="{magic_url}">{magic_url}</a></p>'
        "<p><em>This link will expire in 30 minutes. "
        "If it&rsquo;s expired, request a new one.</em></p>"
    )
    body = {
        "From": from_addr,
        "To": to_email,
        "Subject": "Your EHF Fellows Directory link (expires in 30 minutes)",
        "TextBody": text_body,
        "HtmlBody": html_body,
        "MessageStream": "outbound",
    }
    req = urllib.request.Request(
        "https://api.postmarkapp.com/email",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "X-Postmark-Server-Token": api_token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read().decode("utf-8") if resp else ""
        if resp.status != 200:
            raise RuntimeError("Postmark returned HTTP " + str(resp.status) + " body=" + payload)
        try:
            obj = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            obj = {"raw": payload}
        return {
            "status": resp.status,
            "message_id": obj.get("MessageID"),
            "error_code": obj.get("ErrorCode"),
            "message": obj.get("Message"),
            "to": obj.get("To"),
            "submitted_at": obj.get("SubmittedAt"),
            "raw": obj,
        }


def sign_session_value(secret: bytes, token_issued_at: Optional[float] = None) -> str:
    """Sign a v2 session cookie carrying token_issued_at.

    Payload format (utf-8): ``v2:<exp>:<token_issued_at>:<nonce>``
    token_issued_at is ``int(time.time())`` of the magic-link token that granted
    this session. Pass None only in legacy/test paths where no token context is
    available — callers in production must always pass a value.
    """
    exp = int(time.time()) + SESSION_MAX_AGE
    nonce = secrets.token_hex(16)
    tia = int(token_issued_at) if token_issued_at is not None else 0
    payload = f"{SESSION_VERSION}:{exp}:{tia}:{nonce}".encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return (
        base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=") + "." + sig
    )


def verify_session_value(cookie_val: str, secret: bytes) -> Optional[dict]:
    """Verify a v2 session cookie.

    Returns ``{"token_issued_at": <int>}`` on success. Returns None on any
    failure (bad signature, expired, malformed, v1 cookies). Callers relying on
    boolean semantics still work because None is falsy and a dict is truthy.
    """
    try:
        parts = cookie_val.strip().split(".", 1)
        if len(parts) != 2:
            return None
        b64payload, sig = parts
        pad = "=" * (-len(b64payload) % 4)
        payload = base64.urlsafe_b64decode(b64payload + pad)
        expect_sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect_sig, sig):
            return None
        text = payload.decode("utf-8")
        fields = text.split(":")
        if len(fields) < 4 or fields[0] != SESSION_VERSION:
            # v1 cookies (no version prefix) land here and are rejected by
            # design — forces a clean re-login after this deploy.
            return None
        _ver, exp_s, tia_s, _nonce = fields[0], fields[1], fields[2], ":".join(fields[3:])
        if int(exp_s) < time.time():
            return None
        return {"token_issued_at": int(tia_s)}
    except (ValueError, UnicodeDecodeError):
        return None


def clear_session_cookie_line(headers) -> str:
    """A Set-Cookie header line that expires the session cookie immediately."""
    parts = [
        f"{SESSION_COOKIE}=",
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
        "Max-Age=0",
    ]
    if should_use_secure_cookie(headers):
        parts.append("Secure")
    return "; ".join(parts)


def parse_cookie_header(cookie_header: Optional[str], name: str) -> Optional[str]:
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith(name + "="):
            return part[len(name) + 1 :].strip()
    return None


def session_secret_bytes() -> Optional[bytes]:
    s = os.environ.get("FELLOWS_SESSION_SECRET", "").strip()
    if not s:
        return None
    return s.encode("utf-8")


def is_protected_data_path(path: str) -> bool:
    """Paths that require a session when auth is active."""
    if path == "/fellows.db":
        return True
    if path.startswith("/images/"):
        return True
    return False


def is_gated_api_path(path: str) -> bool:
    """True for directory JSON API routes that require a session when auth is on."""
    if not path.startswith("/api/"):
        return False
    if path == "/api/auth/status":
        return False
    if path == "/api/send-unlock" or path == "/api/verify-token":
        return False
    if path.startswith("/api/debug/"):
        return False
    return True


def should_use_secure_cookie(headers) -> bool:
    if os.environ.get("FELLOWS_COOKIE_INSECURE", "").strip().lower() in ("1", "true", "yes"):
        return False
    if (headers.get("X-Forwarded-Proto") or "").lower() == "https":
        return True
    host = (headers.get("Host") or "").split(":")[0]
    if host in ("localhost", "127.0.0.1", ""):
        return False
    return False


def set_session_cookie_line(value: str, headers) -> str:
    parts = [
        f"{SESSION_COOKIE}={value}",
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
        f"Max-Age={SESSION_MAX_AGE}",
    ]
    if should_use_secure_cookie(headers):
        parts.append("Secure")
    return "; ".join(parts)


def public_origin_for_request(environ_host: str, headers) -> str:
    fixed = os.environ.get("FELLOWS_PUBLIC_ORIGIN", "").strip()
    if fixed:
        return fixed.rstrip("/")
    host = environ_host or "localhost"
    proto = (headers.get("X-Forwarded-Proto") or "").strip().lower()
    if proto not in ("http", "https"):
        proto = "https"
    if host.split(":")[0] in ("localhost", "127.0.0.1"):
        proto = "http"
    return f"{proto}://{host}"
