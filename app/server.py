#!/usr/bin/env python3
"""
EHF Fellows local directory server.
Serves static files, /api/fellows, /api/search, /api/groups, and
/images/<slug>.<ext>.

Run from repo root: python app/server.py
Then open http://localhost:8765/
"""

import json
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
# Allow running this as a script (`python app/server.py`) AND as a package
# member (`from app.server import ...` from tests). The script-mode launcher
# only puts ``app/`` on sys.path, so we add the repo root explicitly.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import relationships  # noqa: E402  (after sys.path manipulation)
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

    # --- Helpers for /api/groups CRUD --------------------------------------

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

    def _send_json_error(self, status, message):
        self.send_json({"error": message}, status=status)

    @staticmethod
    def _validate_group_payload(body, *, require_name=True):
        """Light validation. Returns (clean_dict, error_str)."""
        if not isinstance(body, dict):
            return None, "body must be a JSON object"
        out = {}
        if "name" in body:
            name = body["name"]
            if not isinstance(name, str):
                return None, "name must be a string"
            name = name.strip()
            if not name or len(name) > 200:
                return None, "name must be 1-200 characters"
            out["name"] = name
        elif require_name:
            return None, "name is required"
        if "note" in body:
            note = body["note"]
            if not isinstance(note, str):
                return None, "note must be a string"
            if len(note) > 4000:
                return None, "note must be at most 4000 characters"
            out["note"] = note
        if "fellow_record_ids" in body:
            ids = body["fellow_record_ids"]
            if not isinstance(ids, list):
                return None, "fellow_record_ids must be a list"
            for rid in ids:
                if not isinstance(rid, str) or not rid.strip():
                    return None, "fellow_record_ids must be non-empty strings"
            out["fellow_record_ids"] = [rid.strip() for rid in ids]
        return out, None

    def _open_relationships_db(self):
        """Open relationships.db with fellows.db ATTACHed read-only."""
        try:
            return relationships.open_db()
        except FileNotFoundError:
            return None

    # --- Method dispatch ---------------------------------------------------

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/api/groups":
            body = self._read_json_body()
            if body is None:
                return self._send_json_error(400, "invalid JSON body")
            clean, err = self._validate_group_payload(body, require_name=True)
            if err:
                return self._send_json_error(400, err)
            conn = self._open_relationships_db()
            if conn is None:
                return self._send_json_error(503, "relationships db unavailable")
            try:
                gid = relationships.create_group(
                    conn,
                    name=clean["name"],
                    note=clean.get("note", ""),
                    fellow_record_ids=clean.get("fellow_record_ids"),
                )
                full = relationships.get_group(conn, gid, attached=True)
            finally:
                conn.close()
            return self.send_json(full, status=201)
        self.send_error_404()

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path.startswith("/api/groups/"):
            try:
                gid = int(path[len("/api/groups/"):].strip("/"))
            except ValueError:
                return self.send_error_404()
            body = self._read_json_body()
            if body is None:
                return self._send_json_error(400, "invalid JSON body")
            clean, err = self._validate_group_payload(body, require_name=False)
            if err:
                return self._send_json_error(400, err)
            conn = self._open_relationships_db()
            if conn is None:
                return self._send_json_error(503, "relationships db unavailable")
            try:
                ok = relationships.update_group(
                    conn,
                    gid,
                    name=clean.get("name"),
                    note=clean.get("note"),
                    fellow_record_ids=clean.get("fellow_record_ids"),
                )
                if not ok:
                    return self.send_error_404()
                full = relationships.get_group(conn, gid, attached=True)
            finally:
                conn.close()
            return self.send_json(full)
        self.send_error_404()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path.startswith("/api/groups/"):
            try:
                gid = int(path[len("/api/groups/"):].strip("/"))
            except ValueError:
                return self.send_error_404()
            conn = self._open_relationships_db()
            if conn is None:
                return self._send_json_error(503, "relationships db unavailable")
            try:
                ok = relationships.delete_group(conn, gid)
            finally:
                conn.close()
            if not ok:
                return self.send_error_404()
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

        # API: groups list
        if path == "/api/groups":
            conn = self._open_relationships_db()
            if conn is None:
                # No fellows.db on disk yet → empty list, not an error
                self.send_json([])
                return
            try:
                groups = relationships.list_groups(conn)
            finally:
                conn.close()
            self.send_json(groups)
            return

        # API: one group by id
        if path.startswith("/api/groups/"):
            try:
                gid = int(path[len("/api/groups/"):].strip("/"))
            except ValueError:
                self.send_error_404()
                return
            conn = self._open_relationships_db()
            if conn is None:
                self.send_error_404()
                return
            try:
                group = relationships.get_group(conn, gid, attached=True)
            finally:
                conn.close()
            if group is None:
                self.send_error_404()
                return
            self.send_json(group)
            return

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
