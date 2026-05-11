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

import json
import re
import sqlite3
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
    """
    sha = label.rsplit("-", 1)[-1] if label else None
    return {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": sha,
        "build_label": label,
        "generator": "app/server.py (dev)",
    }


BUILD_LABEL: str = _build_pwa.compute_build_label(REPO_ROOT)
BUILD_META: dict = _dev_build_meta(BUILD_LABEL)

# Columns in fellows table (exclude extra_json for row dict)
FELLOW_COLUMNS = [
    "record_id", "slug", "name", "bio_tagline", "fellow_type", "cohort",
    "contact_email", "key_links", "key_links_urls", "image_url",
    "currently_based_in", "search_tags", "fellow_status", "gender_pronouns",
    "ethnicity", "primary_citizenship", "global_regions_currently_based_in",
    "has_image",
]


def row_to_fellow(row) -> dict:
    """Convert DB row (dict-like) to API fellow object; parse JSON columns and merge extra_json."""
    # Support sqlite3.Row (no .get); convert to dict for uniform access
    if hasattr(row, "keys"):
        row = {k: row[k] for k in row.keys()}
    out = {}
    for key in FELLOW_COLUMNS:
        val = row.get(key)
        if key == "key_links_urls" and val is not None:
            try:
                out[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                out[key] = val
        else:
            out[key] = val
    if row.get("extra_json"):
        try:
            extra = json.loads(row["extra_json"])
            if isinstance(extra, dict):
                out.update(extra)
        except (json.JSONDecodeError, TypeError):
            pass
    return out


def get_db():
    """Return a DB connection (caller should close or use as context)."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_fellows(conn) -> list:
    cur = conn.execute(
        "SELECT * FROM fellows ORDER BY name ASC"
    )
    return [row_to_fellow(row) for row in cur.fetchall()]


def get_fellows_list(conn) -> list:
    """Minimal list for instant directory: record_id, slug, name, has_contact_email."""
    cur = conn.execute(
        "SELECT record_id, slug, name,"
        " CASE WHEN contact_email IS NOT NULL AND contact_email != '' THEN 1 ELSE 0 END"
        " AS has_contact_email"
        " FROM fellows ORDER BY name ASC"
    )
    rows = cur.fetchall()
    return [
        {"record_id": r[0], "slug": r[1], "name": r[2], "has_contact_email": bool(r[3])}
        for r in rows
    ]


def get_fellow_by_slug_or_id(conn, slug_or_id: str) -> dict | None:
    cur = conn.execute(
        "SELECT * FROM fellows WHERE slug = ? OR record_id = ? LIMIT 1",
        (slug_or_id, slug_or_id),
    )
    row = cur.fetchone()
    return row_to_fellow(row) if row else None


def search_fellows(conn, q: str) -> list:
    if not (q or q.strip()):
        return []
    q = q.strip()
    # Guard against excessively long or pathological search strings
    if len(q) > 200:
        q = q[:200]
    cur = conn.execute(
        """
        SELECT f.* FROM fellows f
        WHERE f.rowid IN (
            SELECT rowid FROM fellows_fts WHERE fellows_fts MATCH ?
        )
        ORDER BY f.name ASC
        """,
        (q,),
    )
    return [row_to_fellow(row) for row in cur.fetchall()]


def get_stats(conn) -> dict:
    """Aggregate statistics for the stats page."""
    total = conn.execute("SELECT COUNT(*) FROM fellows").fetchone()[0]

    def group_counts(sql):
        return [{"label": r[0], "count": r[1]} for r in conn.execute(sql).fetchall()]

    # Region counts: split comma-separated global_regions_currently_based_in
    # so dual-region fellows are counted in each region
    from collections import Counter
    region_counter = Counter()
    for row in conn.execute(
        "SELECT global_regions_currently_based_in FROM fellows"
        " WHERE global_regions_currently_based_in IS NOT NULL"
        " AND global_regions_currently_based_in != ''"
    ).fetchall():
        for region in row[0].split(","):
            region = region.strip()
            if region:
                region_counter[region] += 1
    by_region = [{"label": r, "count": c} for r, c in region_counter.most_common()]

    # Field completeness: count non-empty values for each DB column and extra_json key
    field_counts = []
    # Friendly labels for DB columns
    col_labels = {
        "name": "Name", "bio_tagline": "Bio / Tagline", "fellow_type": "Fellow Type",
        "cohort": "Cohort", "contact_email": "Contact Email", "key_links": "Key Links",
        "image_url": "Image URL", "currently_based_in": "Currently Based In",
        "search_tags": "Search Tags", "fellow_status": "Fellow Status",
        "gender_pronouns": "Gender / Pronouns", "ethnicity": "Ethnicity",
        "primary_citizenship": "Primary Citizenship",
        "global_regions_currently_based_in": "Global Regions Based In",
    }
    for col, label in col_labels.items():
        count = conn.execute(
            f"SELECT COUNT(*) FROM fellows WHERE {col} IS NOT NULL AND {col} != ''"
        ).fetchone()[0]
        field_counts.append({"label": label, "count": count})
    # Extra JSON keys with friendly labels
    extra_labels = {
        "all_citizenships": "All Citizenships",
        "ventures": "Ventures", "industries": "Industries",
        "career_highlights": "Career Highlights",
        "key_networks": "Key Networks",
        "how_im_looking_to_support_the_nz_ecosystem": "How Supporting NZ Ecosystem",
        "what_is_your_main_mode_of_working": "Main Mode of Working",
        "do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories": "Investor Categories",
        "mobile_number": "Mobile Number",
        "five_things_to_know": "Five Things to Know",
        "skills_to_give": "Skills to Give",
        "skills_to_receive": "Skills to Receive",
    }
    for key, label in extra_labels.items():
        count = conn.execute(
            "SELECT COUNT(*) FROM fellows WHERE extra_json IS NOT NULL"
            " AND json_extract(extra_json, ?) IS NOT NULL"
            " AND json_extract(extra_json, ?) != ''",
            (f"$.{key}", f"$.{key}"),
        ).fetchone()[0]
        field_counts.append({"label": label, "count": count})
    field_counts.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total": total,
        "by_fellow_type": group_counts(
            "SELECT fellow_type, COUNT(*) FROM fellows"
            " WHERE fellow_type IS NOT NULL"
            " GROUP BY fellow_type ORDER BY COUNT(*) DESC"
        ),
        "by_cohort": group_counts(
            "SELECT cohort, COUNT(*) FROM fellows"
            " WHERE cohort IS NOT NULL"
            " GROUP BY cohort ORDER BY COUNT(*) DESC"
        ),
        "by_region": by_region,
        "field_completeness": field_counts,
    }


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

        # Diagnostics stub for the in-app `?diag=1` panel and the SW
        # health probe. The dev server has no auth, no allowlist, and no
        # Postmark wiring, so most fields are inert; this exists purely
        # so the panel renders cleanly in dev instead of showing a
        # network error. Mirrors the prod shape in `deploy/server.py`.
        if path == "/api/debug/diagnostics":
            self.send_json(
                {
                    "authActive": False,
                    "allowlistHashCount": 0,
                    "sessionSecretConfigured": False,
                    "postmarkTokenConfigured": False,
                    "fellowsDbPresent": DB_PATH.is_file(),
                    "build": BUILD_META,
                    "distRoot": str(APP_DIR),
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
