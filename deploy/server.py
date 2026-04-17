#!/usr/bin/env python3
"""Production static server for Fellows PWA (stdlib only).

Serves files from a directory (default: ./dist next to this script). Binds
127.0.0.1 only — place behind Caddy or another reverse proxy on 443.

When ``fellows.db`` is present in that directory, also serves the same read-only
JSON API as ``app/server.py`` so the installed PWA can fall back if sqlite-wasm
/ OPFS is unavailable (static distribution has no separate API process).

Phase 4 (optional): magic-link auth when ``allowed_emails.json`` exists in dist
and ``FELLOWS_SESSION_SECRET`` is set. See ``magic_link_auth.py`` and README.

Environment:
  PORT                  Listen port (default 8765).
  FELLOWS_DIST_ROOT     Absolute path to the static root (default: <this_dir>/dist).
  FELLOWS_SESSION_SECRET   HMAC secret for session cookie (required for auth).
  FELLOWS_POSTMARK_TOKEN   Send magic links via Postmark (required to actually email).
  FELLOWS_MAIL_FROM        From address (default noreply@fellows.globaldonut.com).
  FELLOWS_PUBLIC_ORIGIN    Base URL for magic links (default: infer from Host / X-Forwarded-Proto).
  FELLOWS_COOKIE_INSECURE  Set to 1 to omit Secure on session cookie (local HTTP testing).

Request lines are logged to stdout for journald under systemd.
"""

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import sys
import urllib.error
import urllib.parse

import magic_link_auth as ml
import sqlite_api_support as sq

PORT = int(os.environ.get("PORT", "8765"))
DEPLOY_DIR = Path(__file__).resolve().parent
DIST_DIR = Path(os.environ.get("FELLOWS_DIST_ROOT", str(DEPLOY_DIR / "dist"))).resolve()
DB_PATH = DIST_DIR / "fellows.db"

# Set by init_auth() before listen.
AUTH_ACTIVE = False
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


def init_auth() -> None:
    global AUTH_ACTIVE
    allow = ml.load_allowlist(DIST_DIR)
    sec = ml.session_secret_bytes()
    AUTH_ACTIVE = bool(sec and allow)
    if sec and not allow:
        print(
            "Warning: FELLOWS_SESSION_SECRET set but allowed_emails.json missing or empty — auth disabled.",
            file=sys.stderr,
        )
    if allow and not sec:
        print(
            "Warning: allowed_emails.json present but FELLOWS_SESSION_SECRET unset — auth disabled.",
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
    }

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

    def has_valid_session(self) -> bool:
        if not AUTH_ACTIVE:
            return True
        sec = ml.session_secret_bytes()
        if not sec:
            return False
        c = ml.parse_cookie_header(self.headers.get("Cookie"), ml.SESSION_COOKIE)
        return bool(c and ml.verify_session_value(c, sec))

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
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        if path == "/api/auth/status":
            has_cookie = bool(
                ml.parse_cookie_header(self.headers.get("Cookie"), ml.SESSION_COOKIE)
            )
            authed = self.has_valid_session()
            print(
                json.dumps(
                    {
                        "event": "auth_status",
                        "auth_active": AUTH_ACTIVE,
                        "authenticated": authed,
                        "has_session_cookie": has_cookie,
                        "user_agent": (self.headers.get("User-Agent") or "")[:240],
                    }
                ),
                file=sys.stderr,
            )
            payload = {
                "authEnabled": AUTH_ACTIVE,
                "authenticated": authed,
                "hasSessionCookie": has_cookie,
            }
            if BUILD_META:
                payload["build"] = BUILD_META.get("built_at")
                payload["buildGitSha"] = BUILD_META.get("git_sha")
            self.send_json(payload)
            return

        if path == "/api/debug/diagnostics":
            allow = ml.load_allowlist(DIST_DIR)
            sec = ml.session_secret_bytes()
            postmark = bool(os.environ.get("FELLOWS_POSTMARK_TOKEN", "").strip())
            self.send_json(
                {
                    "authActive": AUTH_ACTIVE,
                    "allowlistHashCount": len(allow),
                    "sessionSecretConfigured": bool(sec),
                    "postmarkTokenConfigured": postmark,
                    "fellowsDbPresent": DB_PATH.is_file(),
                    "build": BUILD_META,
                    "distRoot": str(DIST_DIR),
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

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        ln = int(self.headers.get("Content-Length", 0) or 0)
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
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _handle_send_unlock(self, body: dict) -> None:
        # Anti-enumeration: always 200 {"sent": true}
        email = (body.get("email") or "").strip()
        if not ml.is_valid_email_shape(email):
            self.send_json({"sent": True})
            return
        if not AUTH_ACTIVE:
            self.send_json({"sent": True})
            return
        h = ml.sha256_email(email)
        if not ml.check_rate_limit(h):
            print("Rate limit: send-unlock for hash prefix " + h[:12], file=sys.stderr)
            self.send_json({"sent": True})
            return
        allow = ml.load_allowlist(DIST_DIR)
        if h not in allow:
            self.send_json({"sent": True})
            return
        token = ml.issue_token()
        host = self.headers.get("Host", "localhost")
        origin = ml.public_origin_for_request(host, self.headers)
        magic_url = origin + "/#/unlock/" + token
        try:
            meta = ml.send_postmark_magic_link(email, magic_url)
            print(
                json.dumps(
                    {
                        "event": "send_unlock_email",
                        "result": "sent",
                        "email_hash_prefix": h[:12],
                        "token_prefix": token[:12],
                        "postmark": meta,
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
        if not tok or not ml.consume_token(tok):
            self.send_json({"ok": False, "error": "invalid_or_expired"}, status=401)
            return
        sec = ml.session_secret_bytes()
        if not sec:
            self.send_json({"ok": False, "error": "server_misconfigured"}, status=500)
            return
        val = ml.sign_session_value(sec)
        cookie = ml.set_session_cookie_line(val, self.headers)
        self.send_json_with_headers({"ok": True}, 200, [("Set-Cookie", cookie)])

    def end_headers(self):
        path = urllib.parse.urlparse(self.path).path
        pl = path.lower()
        if pl == "/" or pl.endswith(".html"):
            self.send_header("Cache-Control", "no-cache")
        elif pl.endswith("/sw.js") or pl.rsplit("/", 1)[-1] == "sw.js":
            self.send_header("Cache-Control", "no-cache")
        elif pl.endswith(".webmanifest") or pl.rsplit("/", 1)[-1] == "manifest.webmanifest":
            self.send_header("Cache-Control", "no-cache")
        elif pl.rsplit("/", 1)[-1] in ("app.js", "styles.css"):
            # App shell: must revalidate so browsers (and SW networkFirst) get auth UX updates.
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
            self.send_header("Cache-Control", LONG_CACHE_CONTROL)
        self._telemetry_headers()
        super().end_headers()


def main():
    global AUTH_ACTIVE, BUILD_META
    init_auth()
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
