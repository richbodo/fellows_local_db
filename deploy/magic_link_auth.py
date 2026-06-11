"""Magic-link authentication helpers for deploy/server.py (stdlib only).

Auth is active when both ``FELLOWS_SESSION_SECRET`` and
``FELLOWS_ALLOWLIST_HMAC_KEY`` are set, and ``fellows.db`` contains at
least one ``contact_email`` row. The allowlist is materialised in
memory at server startup by HMAC-ing every distinct ``contact_email``
in the bundled DB — there is no longer any ``allowed_emails.json``
artifact on disk.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
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
# Re-consume policy: a token, once consumed, stays redeemable for the
# REMAINDER of its original TOKEN_TTL (not a brief fixed grace window). This
# defends against email-side link scanners (which GET/execute the link before
# the human clicks), bfcache / iOS back-button replays, and a second device
# opening the same link. The dominant real-world failure was "a passive
# scanner consumes the token, then the legit user's click seconds-to-minutes
# later sees 'invalid'." A fixed 60 s grace (the prior GRACE_WINDOW) did not
# cover the multi-minute gaps seen in prod — a scanner consumed at +222 s and
# the human clicked at +309 s, 87 s after the scanner, outside 60 s. Bounding
# re-use by TOKEN_TTL adds no exposure window: a never-consumed link is
# already valid for the full TTL, so this only removes the "first consumer
# wins, everyone else gets invalid" race. See
# plans/auth_debug_improvements.md (M3) for the original grace rationale.
RATE_WINDOW = 3600
RATE_MAX = 3
SESSION_VERSION = "v3"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Matches the `PROD_PUBLIC_KEY_HEX = '...'` constant in sw.js. The
# captured group is the hex; an unsubstituted `__PROD_PUBLIC_KEY_HEX__`
# placeholder (or any non-hex constant) yields None from
# compute_pubkey_fingerprint().
_PUBKEY_HEX_RE = re.compile(
    r"PROD_PUBLIC_KEY_HEX\s*=\s*['\"]([0-9a-fA-F_]+)['\"]"
)


def compute_pubkey_fingerprint(sw_js_path: Path) -> Optional[str]:
    """SHA-384 hex of the prod signing-key public bytes parsed out of
    ``sw.js``. Returns ``None`` when the constant is missing, is the
    placeholder, or isn't a 65-byte uncompressed P-256 point.

    Mirrors ``build/build_pwa.py:compute_pubkey_fingerprint``. The prod
    server can't import build_pwa (which doesn't ship to prod), so the
    small helper is duplicated here. Both paths must produce the same
    value so that the magic-link email body (this path) and the About
    page (build-meta.json path) show users the same fingerprint to
    compare.
    """
    try:
        text = sw_js_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _PUBKEY_HEX_RE.search(text)
    if not m:
        return None
    hex_str = m.group(1)
    if "_" in hex_str or len(hex_str) != 130:
        return None
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError:
        return None
    if len(raw) != 65 or raw[0] != 0x04:
        return None
    return hashlib.sha384(raw).hexdigest()


class AuthState:
    lock = threading.Lock()
    tokens: dict[str, float] = {}
    # tok -> {"issued_at": <epoch>, "consumed_at": <epoch>}. Populated by
    # consume_token on first success; used to honor a re-consume of the same
    # token for the remainder of its TOKEN_TTL. Cleaned up by
    # cleanup_stale_tokens once the token has aged past TOKEN_TTL.
    consumed: dict[str, dict] = {}
    rate_buckets: dict[str, list[float]] = {}
    # session_id (32-char hex) -> {"issued_at": float, "expires_at": float}.
    # Populated by consume_token on each successful magic-link verify;
    # required by verify_session_value (a cookie whose session_id isn't here
    # is rejected). This is the server-side binding that defends against a
    # leaked FELLOWS_SESSION_SECRET — without the registry an attacker
    # holding only the secret could mint arbitrary cookies. In-memory only:
    # a server restart revokes every outstanding session, which is the
    # intentional one-time logout behaviour on each deploy.
    sessions: dict[str, dict] = {}


def sha256_email(email: str) -> str:
    """Plain SHA-256 of the normalized email. Used for journald
    correlation prefixes (``email_hash_prefix``) and rate-limit bucket
    keys — both stable identifiers, neither security-load-bearing.
    Allowlist comparison uses ``hmac_email`` instead.
    """
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def hmac_email(email: str, key: bytes) -> str:
    """HMAC-SHA256 of the normalized email, hex-encoded.

    Used for allowlist membership comparison only. The HMAC key lives
    in ``/etc/fellows/fellows-pwa.env`` (``FELLOWS_ALLOWLIST_HMAC_KEY``)
    and never leaves the server's memory. With the key kept off-bundle,
    a wordlist crack of intercepted hashes is no longer feasible even
    for a known-org email pattern: an attacker would need both the
    hash set *and* the key, where the prior plain-SHA-256 scheme
    allowed crack-from-file-alone once the file was reachable.
    """
    normalized = email.strip().lower().encode("utf-8")
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()


def allowlist_hmac_key() -> Optional[bytes]:
    """Return the HMAC key bytes from env, or None if unset."""
    s = os.environ.get("FELLOWS_ALLOWLIST_HMAC_KEY", "").strip()
    if not s:
        return None
    return s.encode("utf-8")


def load_allowlist_from_db(db_path: Path, hmac_key: bytes) -> set[str]:
    """Build the allowlist set in memory by HMAC-ing every distinct
    ``contact_email`` in ``fellows.db``. No file artifact is written;
    the allowlist exists only as in-memory state on the server. A cold
    start re-reads the DB; a deploy that ships a new ``fellows.db``
    re-derives the set on the next restart.
    """
    if not db_path.is_file():
        return set()
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute(
                "SELECT DISTINCT lower(trim(contact_email)) FROM fellows "
                "WHERE contact_email IS NOT NULL AND trim(contact_email) != ''"
            )
            return {hmac_email(raw, hmac_key) for (raw,) in cur.fetchall() if raw}
        finally:
            conn.close()
    except sqlite3.Error:
        return set()


def is_valid_email_shape(email: str) -> bool:
    e = (email or "").strip()
    return bool(e) and len(e) <= 254 and bool(_EMAIL_RE.match(e))


def cleanup_stale_tokens() -> None:
    now = time.time()
    with AuthState.lock:
        for t, exp in list(AuthState.tokens.items()):
            if exp < now:
                del AuthState.tokens[t]
        for t, rec in list(AuthState.consumed.items()):
            # Consumed records must outlive the token's full TTL so a
            # legitimate re-consume within that window still resolves (a
            # scanner-then-human gap can be many minutes). Drop only once the
            # original token has aged past TOKEN_TTL.
            if (now - rec["issued_at"]) >= TOKEN_TTL:
                del AuthState.consumed[t]
        for sid, srec in list(AuthState.sessions.items()):
            if srec["expires_at"] < now:
                del AuthState.sessions[sid]


def _register_session(now: float, token_issued_at: float) -> str:
    """Mint and register a session_id. Caller must hold ``AuthState.lock``."""
    session_id = secrets.token_hex(16)
    AuthState.sessions[session_id] = {
        "issued_at": token_issued_at,
        "expires_at": now + SESSION_MAX_AGE,
    }
    return session_id


def revoke_session(session_id: Optional[str]) -> None:
    """Drop a session_id from the registry. Used by the logout handler
    so that explicitly-cleared cookies cannot be replayed even if
    captured from a network log later."""
    if not session_id:
        return
    with AuthState.lock:
        AuthState.sessions.pop(session_id, None)


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
      {"status": "ok", "issued_at": <epoch>, "session_id": <hex>} —
          token is valid: either freshly consumed (live and within
          TTL), or re-consumed while still inside its ORIGINAL
          TOKEN_TTL. On a fresh consume the issued_at is derived from
          the live token's stored expiry; on a re-consume it is the
          issued_at captured at first consume, so every minted session
          carries the same install-window anchor as the first. The
          session_id is freshly minted on each consume and registered
          in ``AuthState.sessions`` so the cookie that signs over it
          will pass ``verify_session_value`` until the session expires
          or is revoked.
      {"status": "expired"} — token existed but is past its 30-min TTL
          (whether never consumed, or consumed and now aged out). Shown
          to user as "that link expired".
      {"status": "invalid"} — token was never issued (or was cleaned up
          after its TTL elapsed). Shown to user as "that link isn't valid".

    A consumed token stays re-consumable for the remainder of its
    original TOKEN_TTL — see the module-level re-consume policy comment
    for why (link scanners / bfcache / a second device must not be able
    to burn the human's click).
    """
    now = time.time()
    with AuthState.lock:
        exp = AuthState.tokens.pop(tok, None)
        if exp is not None:
            if exp < now:
                # Past-TTL on first sight → expired, and NOT recorded in
                # `consumed` (re-presenting it lands in the invalid branch).
                return {"status": "expired"}
            issued_at = exp - TOKEN_TTL
            AuthState.consumed[tok] = {
                "issued_at": issued_at,
                "consumed_at": now,
            }
            session_id = _register_session(now, issued_at)
            return {
                "status": "ok",
                "issued_at": issued_at,
                "session_id": session_id,
            }
        # Token already consumed once. It stays usable for the remainder of
        # its original TOKEN_TTL (not a brief grace window) so a scanner /
        # second device / bfcache replay that consumed it first does not
        # invalidate the human's later click. See the re-consume policy
        # comment near TOKEN_TTL above.
        rec = AuthState.consumed.get(tok)
        if rec is not None:
            if (now - rec["issued_at"]) < TOKEN_TTL:
                session_id = _register_session(now, rec["issued_at"])
                return {
                    "status": "ok",
                    "issued_at": rec["issued_at"],
                    "session_id": session_id,
                }
            # Past the original 30-min TTL: the link genuinely aged out.
            # Drop opportunistically and report `expired` (not `invalid`) so
            # the gate shows "that link expired, request a new one".
            AuthState.consumed.pop(tok, None)
            return {"status": "expired"}
        return {"status": "invalid"}


_VALID_VERIFY_RESULTS = ("ok", "expired", "invalid")
_UA_MAX = 240


def verify_token_event(
    *,
    result_status: Optional[str],
    token: Optional[str],
    user_agent: Optional[str],
    build_label: Optional[str],
) -> dict:
    """Shape the journald event for a /api/verify-token attempt.

    Pure: no I/O. The handler in deploy/server.py emits the dict via
    ``print(json.dumps(...), file=sys.stderr)``.

    The join key is ``token_prefix`` (12 hex chars) — tokens are not
    bound to emails in AuthState, so we recover the email at query
    time by matching against the ``send_unlock_email`` event with the
    same ``token_prefix``. Both events land in journald within minutes
    of each other.

    Unknown ``result_status`` values clamp to ``"invalid"`` so a log
    consumer can rely on the three-value enum.
    """
    result = result_status if result_status in _VALID_VERIFY_RESULTS else "invalid"
    return {
        "event": "verify_token",
        "result": result,
        "token_prefix": (token or "")[:12],
        "user_agent": (user_agent or "")[:_UA_MAX],
        "build_label": build_label or "",
    }


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


DEFAULT_MAIL_FROM = "EHF Directory App <admin@fellows.globaldonut.com>"


def build_postmark_body(
    to_email: str,
    magic_url: str,
    pubkey_fingerprint: Optional[str] = None,
) -> dict:
    """Construct the Postmark /email payload. Pure function; no network.

    From defaults to ``EHF Directory App <admin@fellows.globaldonut.com>``.
    Postmark validates the address part against the verified Sender
    Signature / domain; the display name is what fellows actually see in
    their inbox (a bare address like ``admin@…`` shows as just ``admin``
    in most mail clients, which reads as spam-adjacent — see the 2026-05-06
    incident). Override via FELLOWS_MAIL_FROM only if you need a custom
    display name or address (e.g., a fork running a different org's
    deployment); pass either a bare address or the same
    ``Display Name <addr>`` shape. Reply-To is taken from FELLOWS_REPLY_TO
    when set — useful when admin@ doesn't route to a human mailbox yet
    and replies should land with the operator directly.

    ``pubkey_fingerprint``, when set, is the SHA-384 hex of the prod
    signing key's public bytes. It's appended to both body variants as
    an MITM-mitigation handle: the email arrives via Postmark (a
    different channel than the HTTPS install bundle), so a compromise
    of the prod server cannot trivially also rewrite the email body.
    The security-conscious fellow compares this value to the one on
    the install page's About row. When ``None`` (signing not yet
    configured on the deploy) we simply omit the block — no point
    showing a "your software is unsigned" warning to every user; the
    operator's job is to flip signing on before relying on it.
    """
    from_addr = os.environ.get("FELLOWS_MAIL_FROM", DEFAULT_MAIL_FROM).strip()
    reply_to = os.environ.get("FELLOWS_REPLY_TO", "").strip()

    fp_block_text = ""
    fp_block_html = ""
    if pubkey_fingerprint:
        fp_block_text = (
            "\nPublic key fingerprint (sha-384 of the signing key):\n"
            f"  {pubkey_fingerprint}\n"
            "\n"
            "If the fingerprint shown on the install page's About row"
            " does not match this, do not install. Report to"
            " richbodo@gmail.com.\n"
        )
        fp_block_html = (
            "<p style=\"margin-top:1.5em;font-size:0.9em;color:#555\">"
            "<strong>Public key fingerprint</strong> "
            "(sha-384 of the signing key):<br />"
            f"<code>{pubkey_fingerprint}</code><br />"
            "If the fingerprint shown on the install page&rsquo;s "
            "About row does not match this, do not install. Report to "
            "<a href=\"mailto:richbodo@gmail.com\">richbodo@gmail.com</a>."
            "</p>"
        )

    text_body = (
        "Tap or paste this link to open the install page:\n\n"
        f"{magic_url}\n\n"
        "This link will expire in 30 minutes. If it's expired, request a new one.\n"
        f"{fp_block_text}"
        "\n— EHF Fellows Directory\n"
    )
    html_body = (
        "<p>Tap or paste this link to open the install page:</p>"
        f'<p><a href="{magic_url}">{magic_url}</a></p>'
        "<p><em>This link will expire in 30 minutes. "
        "If it&rsquo;s expired, request a new one.</em></p>"
        f"{fp_block_html}"
        "<p>&mdash; EHF Fellows Directory</p>"
    )
    body = {
        "From": from_addr,
        "To": to_email,
        "Subject": "Your EHF Fellows Directory link (expires in 30 minutes)",
        "TextBody": text_body,
        "HtmlBody": html_body,
        "MessageStream": "outbound",
    }
    if reply_to:
        body["ReplyTo"] = reply_to
    return body


def send_postmark_magic_link(
    to_email: str,
    magic_url: str,
    pubkey_fingerprint: Optional[str] = None,
) -> dict:
    api_token = os.environ.get("FELLOWS_POSTMARK_TOKEN", "").strip()
    if not api_token:
        raise RuntimeError("FELLOWS_POSTMARK_TOKEN is not set")
    body = build_postmark_body(to_email, magic_url, pubkey_fingerprint=pubkey_fingerprint)
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


def sign_session_value(
    secret: bytes,
    token_issued_at: Optional[float] = None,
    session_id: Optional[str] = None,
) -> str:
    """Sign a v3 session cookie binding to a server-recorded session_id.

    Payload format (utf-8): ``v3:<exp>:<token_issued_at>:<session_id>:<nonce>``

    The session_id is required for verification: ``verify_session_value``
    rejects any cookie whose session_id is not in
    ``AuthState.sessions``. This means a leaked
    ``FELLOWS_SESSION_SECRET`` alone cannot mint a valid cookie — an
    attacker would also need to have written into the in-memory
    session registry, which no HTTP path exposes.

    Pass ``session_id=None`` (or empty) only in unit tests that pin
    the pure crypto path; such cookies will fail verification against
    a real running server. Production callers in
    ``deploy/server.py:_handle_verify_token`` always pass the
    session_id minted by ``consume_token``.
    """
    exp = int(time.time()) + SESSION_MAX_AGE
    nonce = secrets.token_hex(16)
    tia = int(token_issued_at) if token_issued_at is not None else 0
    sid = session_id or ""
    payload = f"{SESSION_VERSION}:{exp}:{tia}:{sid}:{nonce}".encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return (
        base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=") + "." + sig
    )


def verify_session_value(cookie_val: str, secret: bytes) -> Optional[dict]:
    """Verify a v3 session cookie.

    Returns ``{"token_issued_at": <int>, "session_id": <str>}`` on
    success. Returns None on any failure: bad signature, expired,
    malformed, v1/v2 cookies (always rejected — forces a clean
    re-login on each version bump), missing session_id, or session_id
    not present in ``AuthState.sessions``. Callers relying on boolean
    semantics still work because None is falsy and a dict is truthy.
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
        if len(fields) < 5 or fields[0] != SESSION_VERSION:
            # v1 / v2 cookies land here and are rejected by design —
            # forces a clean re-login on the v2→v3 cutover (server-
            # side session registry).
            return None
        _ver, exp_s, tia_s, sid = fields[0], fields[1], fields[2], fields[3]
        if int(exp_s) < time.time():
            return None
        if not sid:
            return None
        with AuthState.lock:
            rec = AuthState.sessions.get(sid)
            if rec is None:
                return None
            if rec["expires_at"] < time.time():
                AuthState.sessions.pop(sid, None)
                return None
        return {"token_issued_at": int(tia_s), "session_id": sid}
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
    # MCP bundle downloads — same posture as /fellows.db. The bundles
    # carry `fellows.db` (in shared-data-ops.mcpb) and the cross-DB
    # ATTACH wiring (in private-data-ops.mcpb), so an unauthenticated
    # download would defeat the same gate that /fellows.db protects.
    # See plans/easy_mcp_install.md § 4 and § 8.
    if path.startswith("/mcpb/") and path.endswith(".mcpb"):
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
