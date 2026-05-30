#!/usr/bin/env python3
"""Production static server for Fellows PWA (stdlib only).

Serves files from a directory (default: ./dist next to this script). Binds
127.0.0.1 only — place behind Caddy or another reverse proxy on 443.

When ``fellows.db`` is present in that directory, also serves the same read-only
JSON API as ``app/server.py`` so the installed PWA can fall back if sqlite-wasm
/ OPFS is unavailable (static distribution has no separate API process).

Magic-link auth activates when both ``FELLOWS_SESSION_SECRET`` and
``FELLOWS_ALLOWLIST_HMAC_KEY`` are set, and ``fellows.db`` contains at
least one ``contact_email`` row. The allowlist is built in memory at
startup by HMAC-ing every distinct contact_email — no
``allowed_emails.json`` file is written. See ``magic_link_auth.py`` and
``docs/email_gate.md``.

Environment:
  PORT                          Listen port (default 8765).
  FELLOWS_DIST_ROOT             Absolute path to the static root (default: <this_dir>/dist).
  FELLOWS_SESSION_SECRET        HMAC secret for session cookie (required for auth).
  FELLOWS_ALLOWLIST_HMAC_KEY    HMAC key used to build the in-memory allowlist (required for auth).
  FELLOWS_POSTMARK_TOKEN        Send magic links via Postmark (required to actually email).
  FELLOWS_MAIL_FROM             From address (default: EHF Directory App <admin@fellows.globaldonut.com>).
  FELLOWS_PUBLIC_ORIGIN         Base URL for magic links (default: infer from Host / X-Forwarded-Proto).
  FELLOWS_COOKIE_INSECURE       Set to 1 to omit Secure on session cookie (local HTTP testing).

Request lines are logged to stdout for journald under systemd.
"""

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse

import client_error_sanitizer as ces
import magic_link_auth as ml
import sqlite_api_support as sq

PORT = int(os.environ.get("PORT", "8765"))
DEPLOY_DIR = Path(__file__).resolve().parent
DIST_DIR = Path(os.environ.get("FELLOWS_DIST_ROOT", str(DEPLOY_DIR / "dist"))).resolve()
DB_PATH = DIST_DIR / "fellows.db"

# Set by init_auth() before listen.
AUTH_ACTIVE = False
# In-memory allowlist of HMAC'd contact_emails, populated by init_auth() at
# startup. Replaces the prior dist/allowed_emails.json artifact — the
# allowlist now lives only in this process's RAM, derived from fellows.db
# at boot. Never written to disk; never served over HTTP.
ALLOWLIST: set[str] = set()
# HMAC key used to derive ALLOWLIST entries and to hash incoming emails on
# /api/send-unlock. Sourced from FELLOWS_ALLOWLIST_HMAC_KEY at init_auth();
# kept in memory for the life of the process.
HMAC_KEY: bytes | None = None
# SHA-384 of the prod signing key's public bytes, parsed out of
# dist/sw.js at startup. Embedded in outgoing magic-link emails as an
# out-of-band MITM mitigation: the email arrives via Postmark (a
# different channel than the HTTPS bundle), so a compromised prod
# server cannot trivially also rewrite the email body. None when
# signing isn't yet configured — magic-link emails simply omit the
# fingerprint block until the operator has run `just keygen`.
PUBKEY_FINGERPRINT: str | None = None
# Populated in main() from dist/build-meta.json (written by build/build_pwa.py).
BUILD_META: dict = {}

LONG_CACHE_CONTROL = "public, max-age=604800"


def load_build_meta(dist_dir: Path) -> dict:
    p = dist_dir / "build-meta.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _init_pubkey_fingerprint() -> None:
    """Cache the prod signing-key fingerprint at startup so every
    magic-link send doesn't re-read sw.js. Read from DIST_DIR/sw.js
    (the served bundle); ``None`` when signing isn't configured.
    """
    global PUBKEY_FINGERPRINT
    PUBKEY_FINGERPRINT = ml.compute_pubkey_fingerprint(DIST_DIR / "sw.js")


def init_auth() -> None:
    """Populate AUTH_ACTIVE / ALLOWLIST / HMAC_KEY from env + fellows.db.

    Called once at startup and from the test fixture. Auth is active
    when:
      * FELLOWS_SESSION_SECRET is set, and
      * FELLOWS_ALLOWLIST_HMAC_KEY is set, and
      * fellows.db exists and has at least one contact_email row.

    Any missing piece flips AUTH_ACTIVE to False and logs a one-line
    warning. The send-unlock / verify-token / cookie paths all gate on
    AUTH_ACTIVE, so the failure mode is "no magic links can be issued"
    rather than "anyone can sign in" — fail-closed.
    """
    global AUTH_ACTIVE, ALLOWLIST, HMAC_KEY
    sec = ml.session_secret_bytes()
    HMAC_KEY = ml.allowlist_hmac_key()
    if sec and not HMAC_KEY:
        print(
            "Warning: FELLOWS_SESSION_SECRET set but FELLOWS_ALLOWLIST_HMAC_KEY unset — auth disabled.",
            file=sys.stderr,
        )
    if HMAC_KEY and not sec:
        print(
            "Warning: FELLOWS_ALLOWLIST_HMAC_KEY set but FELLOWS_SESSION_SECRET unset — auth disabled.",
            file=sys.stderr,
        )
    if not sec or not HMAC_KEY:
        ALLOWLIST = set()
        AUTH_ACTIVE = False
        return
    ALLOWLIST = ml.load_allowlist_from_db(DB_PATH, HMAC_KEY)
    AUTH_ACTIVE = bool(ALLOWLIST)
    if not ALLOWLIST:
        print(
            "Warning: FELLOWS_ALLOWLIST_HMAC_KEY set but fellows.db missing or has no contact_email rows — auth disabled.",
            file=sys.stderr,
        )


class Handler(SimpleHTTPRequestHandler):
    """Serve static files from cwd (dist/), optional SQLite JSON API, /healthz, Phase 4 auth API."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".webmanifest": "application/manifest+json; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".wasm": "application/wasm",
        ".db": "application/octet-stream",
        ".mcpb": "application/octet-stream",
    }

    # Whitelist of MCP bundles served from DIST_DIR/mcpb/<name>.mcpb.
    # Mirrors mcpb/node/manifests/ — adding a new bundle means updating
    # this set in lockstep. Defensive against directory traversal even
    # though urllib's path-strip already collapses ``..`` segments.
    MCPB_NAMES = frozenset({"comms", "shared_data_ops", "private_data_ops"})

    def log_message(self, format, *args):
        sys.stdout.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), format % args)
        )
        sys.stdout.flush()

    def list_directory(self, path):
        """Never expose raw directory listings (empty dist was showing as HTML index)."""
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
        return None

    def send_json(self, data, status: int = 200):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_json_with_headers(self, data, status: int = 200, extra_headers=None):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def send_plain(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _telemetry_headers(self) -> None:
        """Stable headers for correlating browser DevTools / curl with journald."""
        bid = (BUILD_META.get("built_at") or BUILD_META.get("git_sha") or "").strip()
        if bid:
            self.send_header("X-Fellows-Build", bid[:64])
        self.send_header("X-Fellows-Auth-Active", "1" if AUTH_ACTIVE else "0")

    def _security_headers(self) -> None:
        """Strict CSP + adjacent hardening, on every response.

        CSP is the load-bearing one — without it a single XSS bug today
        exfiltrates the entire OPFS (relationships.db + fellows.db) to
        an attacker-controlled origin. The policy is strict by design:
        no inline scripts/styles, no third-party origins, no eval.
        `'wasm-unsafe-eval'` is the modern carve-out for sqlite3.wasm's
        WebAssembly compilation in the dedicated worker.

        HSTS, Cross-Origin-Opener-Policy and Cross-Origin-Embedder-Policy
        are set by Caddy at the edge (see
        ansible/roles/caddy/templates/Caddyfile.j2) and not duplicated
        here. The dev server (app/server.py) mirrors this exact CSP /
        Permissions-Policy / CORP block so dev and prod enforce
        identical policies — any drift is the bug that lets a
        CSP-incompatible pattern slip into a release.
        """
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'wasm-unsafe-eval'; "
            "worker-src 'self'; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self'; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none';",
        )
        # Disable browser features the app does not use, to reduce the
        # leverage available to an XSS payload that does land.
        self.send_header(
            "Permissions-Policy",
            "geolocation=(), camera=(), microphone=(), payment=(), "
            "accelerometer=(), gyroscope=(), magnetometer=(), usb=(), "
            "midi=(), serial=(), bluetooth=()",
        )
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Content-Type-Options", "nosniff")

    def has_valid_session(self) -> bool:
        return self.session_payload() is not None

    def session_payload(self):
        """Return ``{token_issued_at}`` for the verified cookie, else None.

        When auth is disabled, returns an empty dict (truthy) so existing
        guards keep working.
        """
        if not AUTH_ACTIVE:
            return {}
        sec = ml.session_secret_bytes()
        if not sec:
            return None
        c = ml.parse_cookie_header(self.headers.get("Cookie"), ml.SESSION_COOKIE)
        if not c:
            return None
        return ml.verify_session_value(c, sec)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/healthz":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return

        if path == "/allowed_emails.json":
            # Defence in depth. The file no longer exists in dist (the
            # allowlist is built in memory from fellows.db at startup),
            # but this stub stays so a future routing change or stale
            # dist tree can't accidentally reintroduce the leak.
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        if path == "/api/auth/status":
            has_cookie = bool(
                ml.parse_cookie_header(self.headers.get("Cookie"), ml.SESSION_COOKIE)
            )
            session = self.session_payload()
            authed = session is not None
            install_allowed = False
            if AUTH_ACTIVE and session and "token_issued_at" in session:
                install_allowed = ml.install_recently_allowed(
                    session.get("token_issued_at") or 0
                )
            print(
                json.dumps(
                    {
                        "event": "auth_status",
                        "auth_active": AUTH_ACTIVE,
                        "authenticated": authed,
                        "has_session_cookie": has_cookie,
                        "install_recently_allowed": install_allowed,
                        "user_agent": (self.headers.get("User-Agent") or "")[:240],
                    }
                ),
                file=sys.stderr,
            )
            payload = {
                "authEnabled": AUTH_ACTIVE,
                "authenticated": authed,
                "hasSessionCookie": has_cookie,
                "installRecentlyAllowed": install_allowed,
            }
            if BUILD_META:
                payload["build"] = BUILD_META.get("built_at")
                payload["buildGitSha"] = BUILD_META.get("git_sha")
            self.send_json(payload)
            return

        if path == "/api/debug/diagnostics":
            # Unauthenticated by design: scripts/smoke_prod.sh probes this
            # to catch a silently-broken send path (authActive but a secret
            # unconfigured). Because it's public, the body is kept to
            # config-presence booleans only — no exact roster size
            # (allowlist count) and no internal filesystem path (distRoot),
            # which are pure reconnaissance for an attacker and read by no
            # tooling. `allowlistConfigured` is a boolean so the smoke check
            # and operators can still tell auth is wired without disclosing N.
            sec = ml.session_secret_bytes()
            hkey = ml.allowlist_hmac_key()
            postmark = bool(os.environ.get("FELLOWS_POSTMARK_TOKEN", "").strip())
            self.send_json(
                {
                    "authActive": AUTH_ACTIVE,
                    "allowlistConfigured": bool(ALLOWLIST),
                    "sessionSecretConfigured": bool(sec),
                    "allowlistHmacKeyConfigured": bool(hkey),
                    "postmarkTokenConfigured": postmark,
                    "fellowsDbPresent": DB_PATH.is_file(),
                    "build": BUILD_META,
                }
            )
            return

        if AUTH_ACTIVE and not self.has_valid_session():
            if ml.is_gated_api_path(path) or ml.is_protected_data_path(path):
                if path.startswith("/api/"):
                    self.send_json({"error": "authentication required"}, status=403)
                else:
                    self.send_plain(
                        HTTPStatus.FORBIDDEN,
                        b"Forbidden\n",
                        "text/plain; charset=utf-8",
                    )
                return

        # MCP bundle download. Handled explicitly (rather than falling
        # through to super().do_GET()'s static serving) so we control
        # the whitelist, Content-Disposition, and a clean stderr log
        # line for download correlation.
        if path.startswith("/mcpb/") and path.endswith(".mcpb"):
            self._serve_mcpb_download(path)
            return

        conn = sq.connect(DB_PATH) if DB_PATH.is_file() else None

        if conn is not None:
            try:
                if path == "/api/fellows":
                    if query.get("full") == ["1"]:
                        data = sq.get_all_fellows(conn)
                    else:
                        data = sq.get_fellows_list(conn)
                    self.send_json(data)
                    return

                if path.startswith("/api/fellows/"):
                    slug_or_id = path[len("/api/fellows/") :].strip("/")
                    fellow = sq.get_fellow_by_slug_or_id(conn, slug_or_id)
                    if fellow is None:
                        self.send_plain(HTTPStatus.NOT_FOUND, b"Not Found", "text/plain; charset=utf-8")
                    else:
                        self.send_json(fellow)
                    return

                if path == "/api/search":
                    q = (query.get("q") or [""])[0]
                    self.send_json(sq.search_fellows(conn, q))
                    return

                if path == "/api/stats":
                    self.send_json(sq.get_stats(conn))
                    return
            finally:
                conn.close()

        super().do_GET()

    def _serve_mcpb_download(self, path: str) -> None:
        """Stream a `.mcpb` bundle from ``DIST_DIR/mcpb/<name>.mcpb``.

        Whitelist-gated: only the three names declared in
        ``MCPB_NAMES`` are valid. Anything else 404s without disclosing
        whether the file would exist. Same posture as `/fellows.db` —
        callers must hold a valid session when ``AUTH_ACTIVE`` is True;
        the gate check upstream of this method has already enforced
        that. Plan: ``plans/easy_mcp_install.md`` § 4.
        """
        # path is `/mcpb/<name>.mcpb` (caller guard ensures the
        # prefix/suffix). Strip both, leaving the bare name.
        name = path[len("/mcpb/"):-len(".mcpb")]
        if name not in self.MCPB_NAMES:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        file_path = DIST_DIR / "mcpb" / f"{name}.mcpb"
        try:
            stat = file_path.stat()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        size = stat.st_size
        print(
            json.dumps(
                {
                    "event": "mcpb_download",
                    "name": name,
                    "size_bytes": size,
                    "user_agent": (self.headers.get("User-Agent") or "")[:240],
                }
            ),
            file=sys.stderr,
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{name}.mcpb"',
        )
        self.send_header("Content-Length", str(size))
        # Each download is auth-gated and stamps a fresh log line; no
        # public proxy / shared cache should retain a copy.
        self.send_header("Cache-Control", "private, no-store")
        self._security_headers()
        self._telemetry_headers()
        self.end_headers()
        try:
            with file_path.open("rb") as fh:
                while True:
                    chunk = fh.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (OSError, ConnectionError):
            # Client may close mid-transfer (common when Claude Desktop
            # picks up the file then the browser tab navigates). Nothing
            # to do but stop streaming.
            return

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        ln = int(self.headers.get("Content-Length", 0) or 0)
        # Hard cap on POST bodies. send-unlock / verify-token / logout
        # are tiny by schema (a single email or token). client-errors is
        # the only open-ended one; 16KB is more than enough for the
        # diagnostics block + the 20-event ring.
        if ln > 16 * 1024:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Payload Too Large")
            return
        raw_body = self.rfile.read(ln) if ln > 0 else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json({"error": "invalid JSON"}, status=400)
            return

        if path == "/api/send-unlock":
            self._handle_send_unlock(body)
            return
        if path == "/api/verify-token":
            self._handle_verify_token(body)
            return
        if path == "/api/logout":
            self._handle_logout()
            return
        if path == "/api/client-errors":
            self._handle_client_errors(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _handle_logout(self) -> None:
        """Clear the session cookie regardless of current state.

        Always 200 — we don't reveal whether the caller had a valid session.
        Client navigates to ``/?gate=1`` after this.

        Also revokes the cookie's session_id from the in-memory registry
        when the cookie is well-formed, so the same cookie value cannot
        be replayed even if captured from a network log later. Logout
        does not require a valid session (idempotent by design), so a
        bad/expired cookie is silently accepted; only the registry side
        effect is gated on a parseable cookie.
        """
        sec = ml.session_secret_bytes()
        if sec:
            cookie_val = ml.parse_cookie_header(self.headers.get("Cookie"), ml.SESSION_COOKIE)
            if cookie_val:
                payload = ml.verify_session_value(cookie_val, sec)
                if payload:
                    ml.revoke_session(payload.get("session_id"))
        cookie = ml.clear_session_cookie_line(self.headers)
        self.send_json_with_headers({"ok": True}, 200, [("Set-Cookie", cookie)])

    def _handle_send_unlock(self, body: dict) -> None:
        # Anti-enumeration: always 200 {"sent": true}
        email = (body.get("email") or "").strip()
        if not ml.is_valid_email_shape(email):
            self.send_json({"sent": True})
            return
        if not AUTH_ACTIVE or HMAC_KEY is None:
            self.send_json({"sent": True})
            return
        # Rate-limit and journald correlation use plain SHA-256 of the
        # email — neither is security-load-bearing (rate-limit key is a
        # dict bucket; the prefix is a non-reversible 12-hex correlator
        # that the client also computes for lastSubmitHashPrefix). The
        # *allowlist* check uses HMAC, so a leaked log line cannot be
        # cross-referenced against any persisted hash file.
        h = ml.sha256_email(email)
        if not ml.check_rate_limit(h):
            print("Rate limit: send-unlock for hash prefix " + h[:12], file=sys.stderr)
            self.send_json({"sent": True})
            return
        if ml.hmac_email(email, HMAC_KEY) not in ALLOWLIST:
            self.send_json({"sent": True})
            return
        token = ml.issue_token()
        host = self.headers.get("Host", "localhost")
        origin = ml.public_origin_for_request(host, self.headers)
        magic_url = origin + "/#/unlock/" + token
        try:
            meta = ml.send_postmark_magic_link(
                email, magic_url, pubkey_fingerprint=PUBKEY_FINGERPRINT
            )
            print(
                json.dumps(
                    {
                        "event": "send_unlock_email",
                        "result": "sent",
                        "email_hash_prefix": h[:12],
                        "token_prefix": token[:12],
                        # `meta` carries the full Postmark response, which
                        # includes the raw recipient address (meta["to"] and
                        # meta["raw"]["To"]). journald is the only persistence
                        # for this event and is readable by every operator /
                        # adm / systemd-journal member — logging the raw email
                        # would build a plaintext list of everyone who ever
                        # requested a link, defeating the email_hash_prefix
                        # scheme used everywhere else. Log a PII-free subset;
                        # the recipient stays recoverable out-of-band from
                        # email_hash_prefix + fellows.db (`prod_stats
                        # --include-emails`) or the Postmark API
                        # (`just email-debug --postmark`) when triage needs it.
                        "postmark": {
                            k: meta.get(k)
                            for k in (
                                "status",
                                "message_id",
                                "error_code",
                                "message",
                                "submitted_at",
                            )
                        },
                    }
                ),
                file=sys.stderr,
            )
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except OSError:
                body = ""
            print(
                json.dumps(
                    {
                        "event": "send_unlock_email",
                        "result": "http_error",
                        "email_hash_prefix": h[:12],
                        "token_prefix": token[:12],
                        "status": getattr(e, "code", None),
                        "reason": str(e),
                        "body": body,
                    }
                ),
                file=sys.stderr,
            )
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            print(
                json.dumps(
                    {
                        "event": "send_unlock_email",
                        "result": "error",
                        "email_hash_prefix": h[:12],
                        "token_prefix": token[:12],
                        "error": str(e),
                    }
                ),
                file=sys.stderr,
            )
        self.send_json({"sent": True})

    def _handle_verify_token(self, body: dict) -> None:
        if not AUTH_ACTIVE:
            self.send_json({"ok": True})
            return
        tok = (body.get("token") or "").strip()
        if not tok:
            self.send_json({"ok": False, "error": "invalid"}, status=401)
            return
        result = ml.consume_token(tok)
        status = (result or {}).get("status")
        # Structured event for journald — captures the UA and the server's
        # currently-stamped build_label so triage can answer "what build is
        # this user on?" without a screenshot. token_prefix is the join key
        # back to the matching send_unlock_email event (which carries
        # email_hash_prefix). See plans/install_version_telemetry.md.
        print(
            json.dumps(
                ml.verify_token_event(
                    result_status=status,
                    token=tok,
                    user_agent=self.headers.get("User-Agent", ""),
                    build_label=BUILD_META.get("build_label")
                    or BUILD_META.get("git_sha", ""),
                )
            ),
            file=sys.stderr,
        )
        if status != "ok":
            # "expired" and "invalid" are both 401 but carry distinct error
            # strings so the client can render "link expired" vs "link invalid"
            # banners on the gate after a redirect.
            err = status if status in ("expired", "invalid") else "invalid"
            self.send_json({"ok": False, "error": err}, status=401)
            return
        sec = ml.session_secret_bytes()
        if not sec:
            self.send_json({"ok": False, "error": "server_misconfigured"}, status=500)
            return
        val = ml.sign_session_value(
            sec,
            token_issued_at=result.get("issued_at"),
            session_id=result.get("session_id"),
        )
        cookie = ml.set_session_cookie_line(val, self.headers)
        self.send_json_with_headers({"ok": True}, 200, [("Set-Cookie", cookie)])

    def _client_ip_hash_prefix(self) -> str:
        """Stable per-IP key for rate-limiting and journald correlation.

        We never log the raw IP — only the first 12 hex of its sha256.
        Stable enough that two reports from the same browser tie together
        in the recent-errors view; opaque enough that journald audit
        doesn't expose a per-fellow source map.
        """
        ip = ""
        try:
            ip = (self.client_address or ("",))[0] or ""
        except (AttributeError, IndexError):
            ip = ""
        if not ip:
            return ""
        return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:12]

    def _handle_client_errors(self, body: dict) -> None:
        """Accept a sanitized client-error report; log to journald.

        Unauthenticated by design — the whole point is to catch users
        who couldn't pass the auth gate. Privacy/abuse posture:
          * 16KB body cap (do_POST)
          * Per-IP rate limit via the same bucket as send-unlock
          * Schema accept-list + free-text sanitization (deploy/client_error_sanitizer.py)
          * Always 204 — no oracle, no echo, no error message
          * Structured journald event (`event=client_error`) is the
            ONLY persistence; no DB writes, no file writes
        Anything that doesn't fit the schema is dropped silently rather
        than 400'd, to discourage probe-based reconnaissance.
        """
        ip_prefix = self._client_ip_hash_prefix()
        if ip_prefix and not ml.check_rate_limit(f"clienterr:{ip_prefix}"):
            # Silently drop to keep parity with send-unlock anti-enum.
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        try:
            sanitized = ces.sanitize_payload(body)
        except ValueError:
            # Malformed-but-shape-not-recoverable. Still 204 — no oracle.
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        # Drop entries with no usable events; nothing worth logging.
        if not sanitized.get("events"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        event = {"event": "client_error", "client_ip_prefix": ip_prefix}
        event.update(sanitized)
        print(json.dumps(event), file=sys.stderr)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def send_response(self, code, message=None):
        # Track status so end_headers can pick the right Cache-Control. A long
        # max-age on a 404 is poison: a file that appears later gets shadowed
        # by the stale 404 in every browser that requested it once during the
        # 'missing' window. We learned this the hard way when missing fellow
        # photos cached 7-day 404s then failed to render after the S3 recovery.
        self._last_status = code
        super().send_response(code, message)

    def end_headers(self):
        path = urllib.parse.urlparse(self.path).path
        pl = path.lower()
        is_ok = getattr(self, "_last_status", 200) == 200
        if pl == "/" or pl.endswith(".html"):
            self.send_header("Cache-Control", "no-cache")
        elif pl.endswith("/sw.js") or pl.rsplit("/", 1)[-1] == "sw.js":
            self.send_header("Cache-Control", "no-cache")
        elif pl.endswith(".webmanifest") or pl.rsplit("/", 1)[-1] == "manifest.webmanifest":
            self.send_header("Cache-Control", "no-cache")
        elif pl.rsplit("/", 1)[-1] in ("app.js", "styles.css") or pl.endswith("/vendor/sqlite-worker.js"):
            # App shell: must revalidate so browsers (and SW networkFirst) get auth UX updates.
            # sqlite-worker.js is tightly versioned with app.js (same release cycle, same
            # postMessage protocol) — keep it on the no-cache rail so a prod deploy can't
            # leave a stale worker running against new app.js for up to 7 days.
            self.send_header("Cache-Control", "no-cache")
        elif pl.rsplit("/", 1)[-1] == "build-meta.json":
            self.send_header("Cache-Control", "no-cache")
        elif pl.endswith(
            (
                ".js",
                ".css",
                ".wasm",
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
                ".svg",
                ".ico",
                ".db",
                ".json",
            )
        ):
            # Only apply the 7-day cache to successful responses. 404 / 403
            # responses must NOT be long-cached — otherwise transient misses
            # become permanent client-side.
            if is_ok:
                self.send_header("Cache-Control", LONG_CACHE_CONTROL)
            else:
                self.send_header("Cache-Control", "no-cache")
        self._telemetry_headers()
        self._security_headers()
        super().end_headers()


def main():
    global AUTH_ACTIVE, BUILD_META
    init_auth()
    _init_pubkey_fingerprint()
    BUILD_META = load_build_meta(DIST_DIR)
    if BUILD_META:
        print(json.dumps({"event": "build_meta", "build": BUILD_META}), file=sys.stderr)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(DIST_DIR)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    bits = []
    if AUTH_ACTIVE:
        bits.append("auth")
    if DB_PATH.is_file():
        bits.append("sqlite API")
    bits.append("static")
    print(
        f"Serving {DIST_DIR} on 127.0.0.1:{PORT} ({', '.join(bits)})",
        file=sys.stderr,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
