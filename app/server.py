#!/usr/bin/env python3
"""
EHF Fellows local directory server.
Serves static files, /api/fellows, /api/search, and /images/<slug>.<ext>.

Run from repo root: python app/server.py
Then open http://localhost:8765/
"""

import json
import re
import sqlite3
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
DB_PATH = APP_DIR / "fellows.db"
STATIC_DIR = APP_DIR / "static"
IMAGES_DIR = APP_DIR / "fellow_profile_images_by_name"
# Fallback: images may live in final_fellows_set when not copied into app/
IMAGES_DIR_FALLBACK = REPO_ROOT / "final_fellows_set" / "fellow_profile_images_by_name"
PORT = 8765

# Columns in fellows table (exclude extra_json for row dict)
FELLOW_COLUMNS = [
    "record_id", "slug", "name", "bio_tagline", "fellow_type", "cohort",
    "contact_email", "key_links", "key_links_urls", "image_url",
    "currently_based_in", "search_tags", "fellow_status", "gender_pronouns",
    "ethnicity", "primary_citizenship", "global_regions_currently_based_in",
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
    """Minimal list for instant directory: record_id, slug, name only."""
    cur = conn.execute(
        "SELECT record_id, slug, name FROM fellows ORDER BY name ASC"
    )
    rows = cur.fetchall()
    return [{"record_id": r[0], "slug": r[1], "name": r[2]} for r in rows]


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
    # e.g. slug "shannon_o_leary_joy" matches file "shannon_oleary_joy.jpg"
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
        }
        ctype = content_types.get(suffix, "application/octet-stream")
        try:
            data = file_path.read_bytes()
        except OSError:
            self.send_error_404()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        print("Run: python build/import_json_to_sqlite.py")
        return 1
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    server = HTTPServer(("", PORT), Handler)
    print(f"Server at http://localhost:{PORT}/")
    print("  GET /api/fellows?full=1  - all fellows")
    print("  GET /api/fellows/<slug>  - one fellow")
    print("  GET /api/search?q=...    - FTS5 search")
    print("  GET /images/<slug>.jpg   - profile image")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
