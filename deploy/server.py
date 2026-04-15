#!/usr/bin/env python3
"""Production static server for Fellows PWA (stdlib only).

Serves files from a directory (default: ./dist next to this script). Binds
127.0.0.1 only — place behind Caddy or another reverse proxy on 443.

Environment:
  PORT              Listen port (default 8765).
  FELLOWS_DIST_ROOT Absolute path to the static root (default: <this_dir>/dist).

Request lines are logged to stdout for journald under systemd.
"""

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
import sys
import urllib.parse

PORT = int(os.environ.get("PORT", "8765"))
DEPLOY_DIR = Path(__file__).resolve().parent
DIST_DIR = Path(os.environ.get("FELLOWS_DIST_ROOT", str(DEPLOY_DIR / "dist"))).resolve()

# Cache static assets; always revalidate shell + SW + manifest (Phase 3).
LONG_CACHE_CONTROL = "public, max-age=604800"


class Handler(SimpleHTTPRequestHandler):
    """Serve static files from cwd (dist/) and expose /healthz."""

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

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
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
    print(f"Serving {DIST_DIR} on 127.0.0.1:{PORT}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
