#!/usr/bin/env python3
"""Minimal production server for Fellows PWA static deployment."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os

PORT = int(os.environ.get("PORT", "8765"))
DEPLOY_DIR = Path(__file__).resolve().parent
DIST_DIR = DEPLOY_DIR / "dist"


class Handler(SimpleHTTPRequestHandler):
    """Serve static files from dist/ and expose /healthz."""

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        super().do_GET()

    def end_headers(self):
        # Service worker should revalidate on each request.
        if self.path.endswith("/sw.js") or self.path == "/sw.js":
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(DIST_DIR)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Serving {DIST_DIR} on 127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
