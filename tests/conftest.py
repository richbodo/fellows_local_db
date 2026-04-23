"""Pytest configuration and shared fixtures."""
import os
import sqlite3
import subprocess
import sys
import threading
import time
from http.client import HTTPConnection

import pytest

# Repo root on path for imports
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DB_PATH = os.path.join(REPO_ROOT, "app", "fellows.db")


@pytest.fixture(scope="module")
def db():
    """Shared SQLite connection to fellows.db; skip if missing."""
    if not os.path.exists(DB_PATH):
        pytest.skip(
            f"DB not found at {DB_PATH}. Run: python build/restore_from_knack_scrapefile.py"
        )
    conn = sqlite3.connect(DB_PATH)
    yield conn
    conn.close()

# Session-scoped server: started once for M2 and e2e tests, so we don't double-bind port 8765
_server = None


def _free_port(port):
    """If something is bound to the given port, try to kill it so tests can bind."""
    try:
        out = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        pids = (out.stdout or "").strip().split()
        for pid in pids:
            if pid.isdigit():
                subprocess.run(["kill", "-9", pid], capture_output=True, timeout=2)
                time.sleep(0.2)
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass


def _wait_for_server(port, max_attempts=15):
    for _ in range(max_attempts):
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=1)
            conn.request("GET", "/")
            r = conn.getresponse()
            r.read()
            conn.close()
            if r.status == 200:
                return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


@pytest.fixture(scope="session")
def app_server():
    """Start the app server on port 8765 once per test session (for M2 and e2e).

    If ``E2E_BASE_URL`` is set (e.g. ``https://fellows.globaldonut.com``), skips starting
    a local server so ``tests/e2e/`` can run against that origin. Use only when running
    ``pytest tests/e2e/``; unset for ``tests/test_api.py`` and full-suite runs.
    """
    if os.environ.get("E2E_BASE_URL"):
        yield
        return
    global _server
    from app.server import PORT, HTTPServer, Handler, DB_PATH
    if not os.path.isfile(DB_PATH):
        pytest.skip(f"DB not found: {DB_PATH}. Run: python build/restore_from_knack_scrapefile.py")
    # Free port 8765 so we can bind (e.g. if a previous server or AI-run server is still running)
    _free_port(PORT)
    _server = HTTPServer(("", PORT), Handler)
    thread = threading.Thread(target=_server.serve_forever, daemon=True)
    thread.start()
    if not _wait_for_server(PORT):
        _server.shutdown()
        raise RuntimeError("Server did not start in time on port %s" % PORT)
    yield
    if _server:
        _server.shutdown()
        _server = None
