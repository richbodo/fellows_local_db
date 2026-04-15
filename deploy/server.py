#!/usr/bin/env python3
"""Production static server for Fellows PWA (stdlib only).

Serves files from a directory (default: ./dist next to this script). Binds
127.0.0.1 only — place behind Caddy or another reverse proxy on 443.

When ``fellows.db`` is present in that directory, also serves the same read-only
JSON API as ``app/server.py`` so the installed PWA can fall back if sqlite-wasm
/ OPFS is unavailable (static distribution has no separate API process).

Environment:
  PORT              Listen port (default 8765).
  FELLOWS_DIST_ROOT Absolute path to the static root (default: <this_dir>/dist).

Request lines are logged to stdout for journald under systemd.
"""

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import sys
import urllib.parse

import sqlite_api_support as sq

PORT = int(os.environ.get("PORT", "8765"))
DEPLOY_DIR = Path(__file__).resolve().parent
DIST_DIR = Path(os.environ.get("FELLOWS_DIST_ROOT", str(DEPLOY_DIR / "dist"))).resolve()
DB_PATH = DIST_DIR / "fellows.db"

# Cache static assets; always revalidate shell + SW + manifest (Phase 3).
LONG_CACHE_CONTROL = "public, max-age=604800"


class Handler(SimpleHTTPRequestHandler):
    """Serve static files from cwd (dist/), optional SQLite JSON API, /healthz."""

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

    def send_plain(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

    def end_headers(self):
        path = urllib.parse.urlparse(self.path).path
        pl = path.lower()
        if pl == "/" or pl.endswith(".html"):
            self.send_header("Cache-Control", "no-cache")
        elif pl.endswith("/sw.js") or pl.rsplit("/", 1)[-1] == "sw.js":
            self.send_header("Cache-Control", "no-cache")
        elif pl.endswith(".webmanifest") or pl.rsplit("/", 1)[-1] == "manifest.webmanifest":
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
        super().end_headers()


def main():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(DIST_DIR)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    api = "with /api/* + " if DB_PATH.is_file() else ""
    print(f"Serving {DIST_DIR} on 127.0.0.1:{PORT} ({api}static)", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
