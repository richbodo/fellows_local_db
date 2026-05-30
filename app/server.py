#!/usr/bin/env python3
"""
EHF Fellows local directory server.
Serves static files, /api/fellows, /api/search, /api/stats, and
/images/<slug>.<ext>.

Per Phase 1 of plans/local_first_worker_architecture.md the dev server no
longer serves /api/groups or /api/settings — relationships data lives in
the worker-owned OPFS-stored relationships.db, and dev was the only
deployment that ever shipped those routes. Tests drive the worker via
window.__dataProvider; see tests/e2e/conftest.py.

Run from repo root: python app/server.py
Then open http://localhost:8765/
"""

import base64
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
# Allow running this as a script (`python app/server.py`) AND as a package
# member (`from app.server import ...` from tests). The script-mode launcher
# only puts ``app/`` on sys.path, so we add the repo root explicitly.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# Add deploy/ so the dev server can share the client-error sanitizer with
# prod (deploy/client_error_sanitizer.py). Keeping a single source of
# truth for the privacy boundary so dev round-trip + prod logging behave
# identically.
_DEPLOY_DIR = str(REPO_ROOT / "deploy")
if _DEPLOY_DIR not in sys.path:
    sys.path.insert(0, _DEPLOY_DIR)
# build/ exposes the build-label substitution helpers shared with prod's
# build_pwa.py — keeps dev and dist identical on what gets stamped into
# app.js / sw.js.
_BUILD_DIR = str(REPO_ROOT / "build")
if _BUILD_DIR not in sys.path:
    sys.path.insert(0, _BUILD_DIR)

import client_error_sanitizer as ces  # noqa: E402
import build_pwa as _build_pwa  # noqa: E402  (build-label helpers)
from app.fellows_queries import (  # noqa: E402
    FELLOW_COLUMNS,
    row_to_fellow,
    get_all_fellows,
    get_fellows_list,
    get_fellow_by_slug_or_id,
    search_fellows,
    get_stats,
)
from app import fellows_queries as _fq  # noqa: E402
DB_PATH = APP_DIR / "fellows.db"
STATIC_DIR = APP_DIR / "static"
IMAGES_DIR = APP_DIR / "fellow_profile_images_by_name"
# Fallback: images may live in final_fellows_set when not copied into app/
IMAGES_DIR_FALLBACK = REPO_ROOT / "final_fellows_set" / "fellow_profile_images_by_name"
PORT = 8765


def _dev_build_meta(label: str) -> dict:
    """Synthesize a build-meta blob for the dev server.

    Mirrors the shape of `deploy/dist/build-meta.json` (written by
    `build/build_pwa.py`) so the PWA's drift-check, diagnostics panel,
    and build badge work identically in dev. The `git_sha` half of
    `label` reflects the currently checked-out commit when the server
    was started; `built_at` is the server start time.

    `pubkey_fingerprint` carries the SHA-384 of the **prod** signing
    key when sw.js's `PROD_PUBLIC_KEY_HEX` has been replaced from the
    placeholder. Dev *verifies* with the dev key (see sw.js), but the
    About-page fingerprint we surface to users is always the prod one
    — that's the value users compare against the magic-link email at
    install time, and the value that matters once we leave localhost.
    """
    sha = label.rsplit("-", 1)[-1] if label else None
    meta = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": sha,
        "build_label": label,
        "generator": "app/server.py (dev)",
    }
    fp = _build_pwa.compute_pubkey_fingerprint(STATIC_DIR / "sw.js")
    if fp is not None:
        meta["pubkey_fingerprint"] = fp
    return meta


def _dev_load_signing_key():
    """Lazily import + load the committed dev ECDSA P-256 private key.

    Imported lazily because `cryptography` is a dev dependency; we
    don't want `import app.server` to fail when the dev tools haven't
    been installed for a tests-only workflow.
    """
    global _DEV_SIGNING_KEY
    if _DEV_SIGNING_KEY is None:
        from cryptography.hazmat.primitives import serialization
        _DEV_SIGNING_KEY = serialization.load_pem_private_key(
            _DEV_SIGNING_KEY_PATH.read_bytes(),
            password=None,
        )
    return _DEV_SIGNING_KEY


def _dev_sign_bytes(manifest_bytes: bytes) -> bytes:
    """Sign manifest_bytes with the dev ECDSA P-256 key, return raw
    64-byte r||s (the Web Crypto-friendly form, what the SW expects
    after base64-decoding manifest.sig)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    key = _dev_load_signing_key()
    der = key.sign(manifest_bytes, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _dev_file_bytes_as_served(relpath: str) -> bytes | None:
    """Return the bytes the dev server WOULD write to the wire when a
    client requests `/relpath`. This is what the SW will compute
    SHA-384 over and compare to the manifest entry — so the manifest
    must be hashed over the same bytes. Mirrors the substitution rules
    in `do_GET`'s static-file branch (build-label stamp for
    app.js/sw.js/vendor/sqlite-worker.js, SRI substitution for
    index.html). Returns None when the file doesn't exist.
    """
    # build-meta.json is a synthesized blob, not a file on disk in dev.
    if relpath == "build-meta.json":
        meta = dict(BUILD_META)
        sha = _build_pwa.compute_fellows_db_sha(DB_PATH)
        if sha is not None:
            meta["fellows_db_sha"] = sha
        return json.dumps(meta).encode("utf-8")
    p = STATIC_DIR / relpath
    if not p.is_file():
        return None
    data = p.read_bytes()
    name = Path(relpath).name
    rel_str = relpath.replace("\\", "/")
    if name in ("app.js", "sw.js") or rel_str == "vendor/sqlite-worker.js":
        text = data.decode("utf-8")
        data = _build_pwa.substitute_build_label(text, BUILD_LABEL).encode("utf-8")
    if name == "index.html":
        text = data.decode("utf-8")
        app_js = STATIC_DIR / "app.js"
        if app_js.is_file():
            stamped_app = _build_pwa.substitute_build_label(
                app_js.read_text(encoding="utf-8"), BUILD_LABEL
            ).encode("utf-8")
            text = text.replace(
                _build_pwa.PLACEHOLDER_APP_JS_INTEGRITY,
                _build_pwa.compute_sri_hash_bytes(stamped_app),
            )
        jspdf = STATIC_DIR / "vendor" / "jspdf-2.5.1.umd.min.js"
        if jspdf.is_file():
            text = text.replace(
                _build_pwa.PLACEHOLDER_JSPDF_INTEGRITY,
                _build_pwa.compute_sri_hash(jspdf),
            )
        data = text.encode("utf-8")
    return data


def _dev_compute_manifest() -> bytes:
    """Build the same shape of manifest.json that `build/build_pwa.py`
    writes in prod, but using on-the-fly substituted bytes from
    `app/static/`. Recomputed per request; SHA-384 over ~1MB total is
    sub-millisecond. Deterministic encoding (sort_keys + indent) so
    repeated requests produce byte-identical output."""
    files: dict[str, str] = {}
    for relpath in _build_pwa.MANIFEST_INCLUDE_PATHS:
        b = _dev_file_bytes_as_served(relpath)
        if b is not None:
            files[relpath] = _build_pwa.compute_sri_hash_bytes(b)
    manifest = {
        "version": 1,
        "build_label": BUILD_LABEL,
        "alg": "ECDSA-P256-SHA256",
        "files": files,
    }
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


BUILD_LABEL: str = _build_pwa.compute_build_label(REPO_ROOT)
BUILD_META: dict = _dev_build_meta(BUILD_LABEL)
# Lazy-loaded ECDSA private key used to sign the dev /manifest.sig so
# the service worker's verify path runs in dev e2e tests exactly as in
# production. Loaded from tests/fixtures/dev_signing_key.pem on first
# need; see that file's sibling README.md for why a "private" test key
# in git is acceptable (origin gate in sw.js renders it inert on prod).
_DEV_SIGNING_KEY = None
_DEV_SIGNING_KEY_PATH = REPO_ROOT / "tests" / "fixtures" / "dev_signing_key.pem"

def get_db():
    """Return a DB connection (caller should close or use as context)."""
    return _fq.get_db(DB_PATH)


def find_image(slug: str) -> Path | None:
    """Return path to image file for slug (try .jpg then .png), or None."""
    if not slug:
        return None
    images_dir = IMAGES_DIR if IMAGES_DIR.is_dir() else (IMAGES_DIR_FALLBACK if IMAGES_DIR_FALLBACK.is_dir() else None)
    if not images_dir:
        return None
    base = slug.split("/")[-1].split(".")[0]
    for ext in (".jpg", ".png", ".jpeg"):
        p = images_dir / f"{base}{ext}"
        if p.is_file():
            return p
    # Fallback: compare alphanumeric-only to handle mismatched underscores/hyphens
    # e.g. slug "a_b_c_d" matches file "abcd.jpg"
    base_alpha = re.sub(r"[^a-z0-9]", "", base.lower())
    if not base_alpha:
        return None
    for p in images_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        stem_alpha = re.sub(r"[^a-z0-9]", "", p.stem.lower())
        if stem_alpha == base_alpha:
            return p
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # quiet by default; override to log

    def handle_one_request(self):
        # When Playwright tears down a page or the browser cancels an
        # in-flight asset fetch (common for the per-fellow image
        # requests this server fires off), the socket closes mid-
        # response and any subsequent `wfile.write(...)` raises
        # BrokenPipeError / ConnectionResetError. socketserver's
        # default `handle_error` then prints a full traceback to
        # stderr — which clutters every `just test` run and obscures
        # real failures. Caddy absorbs the same noise upstream in
        # production. Catch it here, mark the connection as closed
        # (the underlying socket is already gone) and return cleanly.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def end_headers(self):
        # Cross-origin isolation. sqlite3-wasm's OPFS-SAH-Pool VFS gates
        # SharedArrayBuffer / Atomics on this; without crossOriginIsolated
        # the VFS install fails ("Cannot install OPFS: Missing
        # SharedArrayBuffer and/or Atomics"), and the dev server falls back
        # to the API provider — which has no live relationships.db, so
        # backup/restore in Settings don't function. Setting these here
        # mirrors what a properly-configured production reverse proxy
        # should set; the app is fully first-party so require-corp is
        # safe (no cross-origin scripts / fonts / images to break).
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        # Strict CSP — without it a single XSS today exfiltrates the
        # entire OPFS (relationships.db + fellows.db) to an attacker-
        # controlled origin. The policy is strict by design: no inline
        # scripts/styles, no third-party origins. `'wasm-unsafe-eval'`
        # is the modern carve-out for sqlite3.wasm's WebAssembly
        # compilation. Mirrors deploy/server.py so dev and prod enforce
        # identical policies — drift is the bug that lets a CSP-
        # incompatible pattern slip into a release.
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
        super().end_headers()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_error_404(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Not Found")

    # --- Helpers ----------------------------------------------------------

    def _read_json_body(self, max_bytes=64 * 1024):
        """Parse a JSON request body. Returns the parsed value or None on error."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            length = 0
        if length <= 0 or length > max_bytes:
            return None
        try:
            raw = self.rfile.read(length)
        except OSError:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    # --- Method dispatch ---------------------------------------------------

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/api/client-errors":
            # Dev stub mirrors deploy/server.py:_handle_client_errors so
            # the round-trip works locally (`just serve-fg` tails the
            # event=client_error stderr line). No rate limit here — dev
            # is single-user. Same sanitizer + same anti-oracle 204.
            body = self._read_json_body(max_bytes=16 * 1024)
            if body is None:
                self.send_response(204)
                self.end_headers()
                return
            try:
                sanitized = ces.sanitize_payload(body)
            except ValueError:
                self.send_response(204)
                self.end_headers()
                return
            if sanitized.get("events"):
                event = {"event": "client_error", "client_ip_prefix": ""}
                event.update(sanitized)
                print(json.dumps(event), file=sys.stderr)
            self.send_response(204)
            self.end_headers()
            return
        self.send_error_404()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)

        # API: all fellows (list-only unless full=1)
        if path == "/api/fellows":
            conn = get_db()
            if not conn:
                self.send_error_404()
                return
            try:
                if query.get("full") == ["1"]:
                    fellows = get_all_fellows(conn)
                else:
                    fellows = get_fellows_list(conn)
                self.send_json(fellows)
            finally:
                conn.close()
            return

        # API: one fellow by slug or record_id
        if path.startswith("/api/fellows/"):
            slug_or_id = path[len("/api/fellows/"):].strip("/")
            conn = get_db()
            if not conn:
                self.send_error_404()
                return
            try:
                fellow = get_fellow_by_slug_or_id(conn, slug_or_id)
                if fellow is None:
                    self.send_error_404()
                    return
                self.send_json(fellow)
            finally:
                conn.close()
            return

        # API: search
        if path == "/api/search":
            q = (query.get("q") or [""])[0]
            conn = get_db()
            if not conn:
                self.send_json([])
                return
            try:
                fellows = search_fellows(conn, q)
                self.send_json(fellows)
            finally:
                conn.close()
            return

        # /api/groups and /api/settings retired in Phase 1 of the
        # local-first worker cutover (plans/local_first_worker_architecture.md).
        # The worker (vendor/sqlite-worker.js) is the sole owner of
        # relationships.db; tests drive it via window.__dataProvider rather
        # than HTTP. See tests/e2e/conftest.py:worker_data.

        # API: auth status stub — dev server has no auth, but the PWA client
        # (app/static/app.js) probes this on every non-standalone load.
        # Returning a valid shape prevents the browser from showing the auth
        # failure panel in local development.
        if path == "/api/auth/status":
            self.send_json(
                {
                    "authEnabled": False,
                    "authenticated": False,
                    "hasSessionCookie": False,
                    "installRecentlyAllowed": False,
                }
            )
            return

        # Build fingerprint stub. Prod (`deploy/server.py`) serves the
        # `dist/build-meta.json` file written by `build/build_pwa.py`;
        # dev synthesizes the same shape from the live git HEAD so the
        # build badge, drift check, and diagnostics panel all work
        # locally. Without this the SW + diag panel both 404 and the
        # browser console logs `Unexpected token 'N'` parse errors.
        #
        # `fellows_db_sha` is computed on the fly so that `just db-rebuild`
        # without a server restart still produces a coherent SHA. SHA-256
        # over a few-MB file is sub-50 ms in practice; if that changes,
        # mtime caching is the trivial follow-up.
        if path == "/build-meta.json":
            meta = dict(BUILD_META)
            sha = _build_pwa.compute_fellows_db_sha(DB_PATH)
            if sha is not None:
                meta["fellows_db_sha"] = sha
            self.send_json(meta)
            return

        # /manifest.json and /manifest.sig are the SW's signed-bundle
        # verification inputs. In prod they're static files written by
        # build_pwa.py + scripts/sign_bundle.py; in dev we compute the
        # manifest on the fly and sign it with the committed test key
        # so the SW's `fetchAndVerifyManifest` path runs in e2e tests
        # exactly as it does on real users' devices.
        if path == "/manifest.json":
            data = _dev_compute_manifest()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/manifest.sig":
            manifest = _dev_compute_manifest()
            raw_sig = _dev_sign_bytes(manifest)
            body = base64.b64encode(raw_sig) + b"\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
            return

        # Diagnostics stub for the in-app `?diag=1` panel and the SW
        # health probe. The dev server has no auth, no allowlist, and no
        # Postmark wiring, so most fields are inert; this exists purely
        # so the panel renders cleanly in dev instead of showing a
        # network error. Mirrors the prod shape in `deploy/server.py`.
        if path == "/api/debug/diagnostics":
            # Field set mirrors deploy/server.py's diagnostics body (dev/prod
            # parity): config-presence booleans only, no exact allowlist size
            # and no internal filesystem path.
            self.send_json(
                {
                    "authActive": False,
                    "allowlistConfigured": False,
                    "sessionSecretConfigured": False,
                    "postmarkTokenConfigured": False,
                    "fellowsDbPresent": DB_PATH.is_file(),
                    "build": BUILD_META,
                }
            )
            return

        # API: stats
        if path == "/api/stats":
            conn = get_db()
            if not conn:
                self.send_error_404()
                return
            try:
                stats = get_stats(conn)
                self.send_json(stats)
            finally:
                conn.close()
            return

        # Static DB snapshot for PWA offline (Phase 2)
        if path == "/fellows.db":
            if not DB_PATH.is_file():
                self.send_error_404()
                return
            try:
                data = DB_PATH.read_bytes()
            except OSError:
                self.send_error_404()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return

        # Images: /images/<slug>.jpg or .png
        if path.startswith("/images/"):
            rest = path[len("/images/"):].lstrip("/")
            if ".." in rest or not rest:
                self.send_error_404()
                return
            slug = rest
            img_path = find_image(slug)
            if img_path is None:
                self.send_error_404()
                return
            try:
                data = img_path.read_bytes()
            except OSError:
                self.send_error_404()
                return
            ext = img_path.suffix.lower()
            ctype = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # Static: / -> index.html, else file from static/
        if path == "/":
            path = "/index.html"
        file_path = STATIC_DIR.joinpath(path.lstrip("/")).resolve()
        if not file_path.is_relative_to(STATIC_DIR.resolve()) or ".." in path:
            self.send_error_404()
            return
        if not file_path.is_file():
            self.send_error_404()
            return
        suffix = file_path.suffix.lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".webmanifest": "application/manifest+json; charset=utf-8",
            ".ico": "image/x-icon",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".wasm": "application/wasm",
            ".db": "application/octet-stream",
        }
        ctype = content_types.get(suffix, "application/octet-stream")
        try:
            data = file_path.read_bytes()
        except OSError:
            self.send_error_404()
            return
        # Build-label substitution mirrors what build/build_pwa.py does
        # for deploy/dist/. Source has '__FELLOWS_UI_DIAG__' /
        # '__CACHE_VERSION__' placeholders so dev and dist agree on the
        # same substitution path; replacing here keeps the build badge,
        # SW cache name, and image cache-bust query string consistent
        # with the current git HEAD without a hand-maintained chore(version)
        # commit.
        # vendor/sqlite-worker.js carries the same BUILD_LABEL placeholder
        # so the worker handshake (init response → buildLabel) reflects
        # the running build for diagnostics.
        path_rel = file_path.relative_to(STATIC_DIR.resolve())
        path_rel_str = str(path_rel).replace("\\", "/")
        if file_path.name in ("app.js", "sw.js") or path_rel_str == "vendor/sqlite-worker.js":
            text = data.decode("utf-8")
            stamped = _build_pwa.substitute_build_label(text, BUILD_LABEL)
            data = stamped.encode("utf-8")
        # SRI substitution for index.html. The integrity for app.js must
        # cover the post-stamp bytes the dev server WILL serve, not the
        # source-tree bytes — otherwise the browser computes one hash and
        # rejects the script. We mirror the stamping rule above (file
        # name in {app.js, sw.js, vendor/sqlite-worker.js}) but here only
        # app.js's hash is consumed.
        if file_path.name == "index.html":
            text = data.decode("utf-8")
            app_js_path = STATIC_DIR / "app.js"
            if app_js_path.is_file():
                stamped_app_js = _build_pwa.substitute_build_label(
                    app_js_path.read_text(encoding="utf-8"), BUILD_LABEL
                ).encode("utf-8")
                text = text.replace(
                    _build_pwa.PLACEHOLDER_APP_JS_INTEGRITY,
                    _build_pwa.compute_sri_hash_bytes(stamped_app_js),
                )
            jspdf_path = STATIC_DIR / "vendor" / "jspdf-2.5.1.umd.min.js"
            if jspdf_path.is_file():
                text = text.replace(
                    _build_pwa.PLACEHOLDER_JSPDF_INTEGRITY,
                    _build_pwa.compute_sri_hash(jspdf_path),
                )
            data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


def main():
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        print("Run: python build/restore_from_knack_scrapefile.py")
        return 1
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    server = HTTPServer(("", PORT), Handler)
    print(f"Server at http://localhost:{PORT}/")
    print("  GET /api/fellows?full=1  - all fellows")
    print("  GET /api/fellows/<slug>  - one fellow")
    print("  GET /api/search?q=...    - FTS5 search")
    print("  GET /fellows.db          - SQLite snapshot (PWA offline)")
    print("  GET /images/<slug>.jpg   - profile image")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
