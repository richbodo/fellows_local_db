"""Pytest configuration and shared fixtures."""
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

# Repo root on path for imports
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DB_PATH = os.path.join(REPO_ROOT, "app", "fellows.db")
# Production server runs on a separate port so tests can keep the dev
# (`app/server.py`, port 8765) and prod-shape (`deploy/server.py`, port 8766)
# servers up at the same time without colliding.
DEPLOY_PORT = 8766


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
def app_server(tmp_path_factory):
    """Start the app server on port 8765 once per test session (for M2 and e2e).

    If ``E2E_BASE_URL`` is set (e.g. ``https://fellows.globaldonut.com``), skips starting
    a local server so ``tests/e2e/`` can run against that origin. Use only when running
    ``pytest tests/e2e/``; unset for ``tests/test_api.py`` and full-suite runs.

    Sets ``FELLOWS_RELATIONSHIPS_DB_PATH`` to a session-scoped temp file so the
    test session never reads or writes the dev ``app/relationships.db``.
    Resolved at call time inside ``app.relationships.open_db``.
    """
    if os.environ.get("E2E_BASE_URL"):
        yield
        return
    rel_dir = tmp_path_factory.mktemp("relationships")
    os.environ["FELLOWS_RELATIONSHIPS_DB_PATH"] = str(rel_dir / "relationships.db")
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


@pytest.fixture(scope="session")
def deploy_server(tmp_path_factory):
    """Start ``deploy/server.py`` in-process on ``DEPLOY_PORT`` with auth on.

    The Postmark sender is replaced at the function-reference level — no
    ``FELLOWS_POSTMARK_TOKEN`` is consulted, so a real token in the dev shell
    cannot leak into the test path. The fixture yields a handle the tests use
    to drive the round-trip:

        {"base_url": "http://127.0.0.1:8766",
         "test_email": "<allowlisted address>",
         "sent": [{"to", "url"}, ...],   # recorder of stubbed Postmark calls
         "auth_state": ml.AuthState,     # in-memory token + rate-bucket dict
         "ml": <magic_link_auth module>,
         "dist_dir": Path}

    Why in-process rather than subprocess: the production server logs only the
    first 12 chars of an issued token, so a subprocess'd server would give
    tests no way to consume the token in /api/verify-token. Importing the
    module here lets us read tokens straight from ``AuthState`` (or, more
    cleanly, from the recorder's captured magic-link URL).
    """
    if os.environ.get("E2E_BASE_URL"):
        pytest.skip("deploy_server is local-only; unset E2E_BASE_URL to run")

    repo_root = Path(REPO_ROOT)
    src_db = repo_root / "app" / "fellows.db"
    if not src_db.is_file():
        pytest.skip(
            f"DB not found at {src_db}. Run: python build/restore_from_knack_scrapefile.py"
        )

    # Build a tmp dist root: app shell + a copy of fellows.db. Copy
    # (not symlink) so a stray write through any future code path
    # can't corrupt the dev DB. The allowlist now lives in memory on
    # the server (built from contact_email rows in fellows.db at
    # init_auth() time), so we INSERT a row for the test email rather
    # than writing a separate allowed_emails.json file.
    dist_dir = tmp_path_factory.mktemp("deploy_dist")
    shutil.copytree(repo_root / "app" / "static", dist_dir, dirs_exist_ok=True)
    shutil.copy2(src_db, dist_dir / "fellows.db")

    # Mirror what `build/build_pwa.py main()` does to a real prod dist:
    # stamp the build label, compute SRI hashes, write build-meta.json
    # and the signed bundle manifest. Without these the SW's install
    # path would 404 on /manifest.json or /manifest.sig and every e2e
    # test would fail at SW install time (no shell precached).
    sys.path.insert(0, str(repo_root / "build"))
    import build_pwa as _build_pwa  # noqa: E402  (path-dependent)
    label = _build_pwa.compute_build_label(repo_root)
    _build_pwa.stamp_static_assets(dist_dir, label)
    _build_pwa.stamp_sri_attributes(dist_dir)
    _build_pwa.write_build_meta(
        dist_dir / "build-meta.json",
        label,
        db_path=dist_dir / "fellows.db",
        sw_js_path=dist_dir / "sw.js",
    )
    _build_pwa.write_bundle_manifest(dist_dir, label)

    # Mirror build_pwa.main()'s image copy so /images/<slug>.{jpg,png}
    # work in e2e tests that hit the deploy server. No test currently
    # asserts on image bytes, but keeping the fixture's dist symmetric
    # with `scripts/serve_prod_local.py` (the manual staging launcher
    # that copy-pastes this recipe) means a future image-related e2e
    # doesn't have to track down "why does staging behave differently
    # from the test fixture."
    _build_pwa.copy_images_to_dist(dist_dir)

    # Sign the manifest with the committed dev test key (same key the
    # dev server uses on the fly). The SW's verify path will run in
    # full against e2e tests; an SRI / manifest / signing bug surfaces
    # at SW install time rather than only on a real prod deploy.
    import base64 as _b64
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives import serialization as _serialization
    from cryptography.hazmat.primitives.asymmetric import ec as _ec
    from cryptography.hazmat.primitives.asymmetric.utils import (
        decode_dss_signature as _decode_dss_signature,
    )
    _dev_key = _serialization.load_pem_private_key(
        (repo_root / "tests" / "fixtures" / "dev_signing_key.pem").read_bytes(),
        password=None,
    )
    _manifest_bytes = (dist_dir / "manifest.json").read_bytes()
    _der = _dev_key.sign(_manifest_bytes, _ec.ECDSA(_hashes.SHA256()))
    _r, _s = _decode_dss_signature(_der)
    _raw_sig = _r.to_bytes(32, "big") + _s.to_bytes(32, "big")
    (dist_dir / "manifest.sig").write_text(
        _b64.b64encode(_raw_sig).decode("ascii") + "\n",
        encoding="utf-8",
    )

    test_email = "round-trip-tester@example.com"
    test_db = dist_dir / "fellows.db"
    conn = sqlite3.connect(str(test_db))
    try:
        # `slug` is NOT NULL with a UNIQUE index — pick a stable slug
        # that won't collide with any real fellow.
        conn.execute(
            "INSERT OR REPLACE INTO fellows "
            "(record_id, slug, name, contact_email) VALUES (?, ?, ?, ?)",
            (
                "test-rt-record",
                "round-trip-tester",
                "Round Trip Tester",
                test_email,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # `deploy/server.py` reads DIST_DIR / PORT at import time. Set env first,
    # save originals so teardown leaves the process clean.
    saved_env = {}
    for k in (
        "FELLOWS_DIST_ROOT",
        "FELLOWS_SESSION_SECRET",
        "FELLOWS_ALLOWLIST_HMAC_KEY",
        "FELLOWS_COOKIE_INSECURE",
        "PORT",
        "FELLOWS_POSTMARK_TOKEN",
    ):
        saved_env[k] = os.environ.get(k)
    os.environ["FELLOWS_DIST_ROOT"] = str(dist_dir)
    os.environ["FELLOWS_SESSION_SECRET"] = "test-secret-for-round-trip-suite"
    os.environ["FELLOWS_ALLOWLIST_HMAC_KEY"] = "test-hmac-key-for-round-trip-suite"
    os.environ["FELLOWS_COOKIE_INSECURE"] = "1"
    os.environ["PORT"] = str(DEPLOY_PORT)
    os.environ.pop("FELLOWS_POSTMARK_TOKEN", None)

    deploy_dir = str(repo_root / "deploy")
    if deploy_dir not in sys.path:
        sys.path.insert(0, deploy_dir)
    # Force re-import so module-level globals (DIST_DIR, PORT) pick up our env.
    for mod_name in ("server", "magic_link_auth", "sqlite_api_support"):
        sys.modules.pop(mod_name, None)
    import server as deploy_srv  # noqa: E402
    import magic_link_auth as ml  # noqa: E402

    sent: list[dict] = []
    real_send = ml.send_postmark_magic_link

    def fake_send(to_email, magic_url, pubkey_fingerprint=None):
        sent.append({"to": to_email, "url": magic_url, "pubkey_fingerprint": pubkey_fingerprint})
        return {
            "status": 200,
            "message_id": "stub-message-id",
            "error_code": 0,
            "message": "OK (test stub)",
            "to": to_email,
            "submitted_at": None,
            "raw": {},
        }

    ml.send_postmark_magic_link = fake_send

    deploy_srv.init_auth()
    deploy_srv.BUILD_META = {}

    # SimpleHTTPRequestHandler resolves static paths against ``self.directory``
    # if set, falling back to cwd otherwise. ``deploy/server.py`` itself
    # chdirs in main(), but doing that from a session-scoped pytest fixture
    # leaks the cwd change into every later test, which destabilizes other
    # e2e tests. Wire the directory via partial() instead — same effect, no
    # process-global side effect.
    from functools import partial

    handler_factory = partial(deploy_srv.Handler, directory=str(dist_dir))

    _free_port(DEPLOY_PORT)
    httpd = deploy_srv.ThreadingHTTPServer(
        ("127.0.0.1", DEPLOY_PORT), handler_factory
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    if not _wait_for_server(DEPLOY_PORT):
        httpd.shutdown()
        raise RuntimeError(
            f"deploy server did not start on port {DEPLOY_PORT}"
        )

    handle = {
        "base_url": f"http://127.0.0.1:{DEPLOY_PORT}",
        "test_email": test_email,
        "sent": sent,
        "auth_state": ml.AuthState,
        "ml": ml,
        "dist_dir": dist_dir,
    }
    try:
        yield handle
    finally:
        httpd.shutdown()
        ml.send_postmark_magic_link = real_send
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
