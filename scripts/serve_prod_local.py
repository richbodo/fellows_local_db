#!/usr/bin/env python3
"""Local staging server — runs deploy/server.py with auth on, Postmark stubbed.

Bridges the gap between the dev server (`app/server.py`, no auth, no MCPB
routes) and prod (`deploy/server.py` on https://fellows.globaldonut.com,
which requires a real deploy to test). Use this to verify the magic-link
flow, the `/mcpb/<name>.mcpb` auth-gated routes, and any UI branch gated
on `authStatus.authEnabled === true` without pushing to prod.

NOT for production. Uses committed test-only secrets, signs with the
committed dev signing key (which the SW's origin check rejects on prod),
and allows insecure cookies so the session works over plain HTTP.

Mirrors the in-process setup in tests/conftest.py:deploy_server so the
two stay consistent. If a Phase-2 user-folder-storage test depends on a
behavior the launcher doesn't reproduce, that's a bug in one of them.

See docs/local_staging.md for the maintainer workflow.

Usage:
    python scripts/serve_prod_local.py            # foreground; Ctrl-C to stop
    python scripts/serve_prod_local.py --reset    # wipe tmp dist + rebuild
    python scripts/serve_prod_local.py --email me@example.com
"""

from __future__ import annotations

import argparse
import base64
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = REPO_ROOT / "tmp" / "prod-local"
DIST_DIR = TMP_DIR / "dist"
MAGIC_LINK_LOG = TMP_DIR / "magic_links.log"
TEST_EMAIL_FILE = TMP_DIR / "test_email.txt"
SRC_DB = REPO_ROOT / "app" / "fellows.db"
DEV_SIGNING_KEY = REPO_ROOT / "tests" / "fixtures" / "dev_signing_key.pem"
MCPB_SOURCE_DIR = REPO_ROOT / "deploy" / "dist" / "mcpb"

PORT = 8766
DEFAULT_TEST_EMAIL = "you@local-staging.example"
# Test-only secrets. The string literals are intentional — readers
# grepping a real prod env file for these values will know they hit a
# local-staging artifact, not a prod leak.
TEST_SESSION_SECRET = "local-staging-secret-DO-NOT-USE-IN-PROD"
TEST_HMAC_KEY = "local-staging-hmac-DO-NOT-USE-IN-PROD"


def _build_dist(force: bool) -> None:
    """Materialize tmp/prod-local/dist/ — a deploy-shaped static root.

    Mirrors tests/conftest.py:deploy_server fixture's setup:
    1. Copy app/static + app/fellows.db.
    2. Stamp build label + SRI hashes.
    3. Write build-meta.json + bundle manifest.
    4. Sign manifest with the committed dev key.
    5. Symlink (or copy) the .mcpb bundles from deploy/dist/mcpb/
       if they exist, so /mcpb/<name>.mcpb routes serve real bytes.
    """
    if DIST_DIR.is_dir() and (DIST_DIR / "fellows.db").is_file() and not force:
        print(f"  Reusing existing dist at {DIST_DIR.relative_to(REPO_ROOT)}")
        print(f"  (use --reset to rebuild from current sources)")
        return

    if not SRC_DB.is_file():
        sys.exit(
            f"DB not found at {SRC_DB.relative_to(REPO_ROOT)}.\n"
            f"Run: python build/restore_from_knack_scrapefile.py"
        )

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    if DIST_DIR.is_dir():
        shutil.rmtree(DIST_DIR)
    shutil.copytree(REPO_ROOT / "app" / "static", DIST_DIR)
    shutil.copy2(SRC_DB, DIST_DIR / "fellows.db")

    sys.path.insert(0, str(REPO_ROOT / "build"))
    import build_pwa  # noqa: E402

    label = build_pwa.compute_build_label(REPO_ROOT)
    build_pwa.stamp_static_assets(DIST_DIR, label)
    build_pwa.stamp_sri_attributes(DIST_DIR)
    build_pwa.write_build_meta(
        DIST_DIR / "build-meta.json",
        label,
        db_path=DIST_DIR / "fellows.db",
        sw_js_path=DIST_DIR / "sw.js",
    )
    build_pwa.write_bundle_manifest(DIST_DIR, label)

    # Mirror build_pwa.main()'s image copy so /images/<slug>.{jpg,png}
    # work on the staging server. Without this every fellow detail /
    # visual directory render fires ~1000 console 404s, which makes
    # staging look broken even though the app shell is fine.
    build_pwa.copy_images_to_dist(DIST_DIR)

    # Sign the manifest with the dev key. Same key tests/conftest.py uses;
    # the SW verify path runs in full but the origin check renders this
    # key inert on the real prod hostname, so leaking it doesn't matter.
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import (
        decode_dss_signature,
    )

    dev_key = serialization.load_pem_private_key(
        DEV_SIGNING_KEY.read_bytes(), password=None
    )
    manifest_bytes = (DIST_DIR / "manifest.json").read_bytes()
    der = dev_key.sign(manifest_bytes, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    (DIST_DIR / "manifest.sig").write_text(
        base64.b64encode(raw_sig).decode("ascii") + "\n",
        encoding="utf-8",
    )

    # Wire the .mcpb bundles so /mcpb/<name>.mcpb routes serve real bytes —
    # otherwise § 6/§ 7 of the maintainer test plan silently runs against
    # absent bundles (the staging analog of the prod ship bug where `build`
    # never produced them). Build them on demand if a prior
    # `just build-mcpb` / `just build` hasn't, unless FELLOWS_SKIP_MCPB=1.
    # Failing to build (e.g. no Node) surfaces loudly rather than leaving
    # the routes silently 404ing under a green-looking staging server.
    skip_mcpb = os.environ.get("FELLOWS_SKIP_MCPB", "0") == "1"
    have_bundles = MCPB_SOURCE_DIR.is_dir() and any(MCPB_SOURCE_DIR.glob("*.mcpb"))
    if not have_bundles and not skip_mcpb:
        print(
            "  No .mcpb bundles at deploy/dist/mcpb/ — building them "
            "(build/build_mcpb.py; needs Node 20+)…"
        )
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "build" / "build_mcpb.py")], check=True
        )
    bundles = sorted(MCPB_SOURCE_DIR.glob("*.mcpb")) if MCPB_SOURCE_DIR.is_dir() else []
    if bundles:
        target = DIST_DIR / "mcpb"
        target.mkdir(exist_ok=True)
        for b in bundles:
            shutil.copy2(b, target / b.name)
        print(f"  Wired {len(bundles)} .mcpb bundle(s) from deploy/dist/mcpb/")
    elif skip_mcpb:
        print(
            "  FELLOWS_SKIP_MCPB=1 — no .mcpb bundles wired "
            "(§ 6/§ 7 staging tests will be skipped)."
        )

    print(f"  Built dist at {DIST_DIR.relative_to(REPO_ROOT)} (label: {label})")


def _allowlist_test_email(email: str) -> None:
    """Insert the test email into the dist's fellows.db so init_auth()
    derives an HMAC for it and the allowlist accepts it."""
    db = DIST_DIR / "fellows.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO fellows "
            "(record_id, slug, name, contact_email) VALUES (?, ?, ?, ?)",
            (
                "local-staging-tester",
                "local-staging-tester",
                "Local Staging Tester",
                email,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    TEST_EMAIL_FILE.write_text(email + "\n")


def _start_server(email: str) -> None:
    """Configure env, import deploy/server.py, monkey-patch Postmark,
    subclass Handler to add COOP/COEP, run foreground."""
    os.environ["FELLOWS_DIST_ROOT"] = str(DIST_DIR)
    os.environ["FELLOWS_SESSION_SECRET"] = TEST_SESSION_SECRET
    os.environ["FELLOWS_ALLOWLIST_HMAC_KEY"] = TEST_HMAC_KEY
    os.environ["FELLOWS_COOKIE_INSECURE"] = "1"
    os.environ["PORT"] = str(PORT)
    # Never send real email from a local-staging run, even if the dev
    # shell has a real token in it.
    os.environ.pop("FELLOWS_POSTMARK_TOKEN", None)

    sys.path.insert(0, str(REPO_ROOT / "deploy"))
    # Force re-import so module-level globals (DIST_DIR, PORT) honor
    # our env. Safe to do at startup of a fresh process.
    for mod in ("server", "magic_link_auth", "sqlite_api_support"):
        sys.modules.pop(mod, None)
    import server as deploy_srv  # noqa: E402
    import magic_link_auth as ml  # noqa: E402

    # Replace the Postmark sender with a file-writer + stderr printer.
    # Maintainer reads the link from `just serve-prod-link` (latest) or
    # `tail -F tmp/prod-local/magic_links.log` (live stream).
    def fake_send(to_email, magic_url, pubkey_fingerprint=None):
        with MAGIC_LINK_LOG.open("a", encoding="utf-8") as f:
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write(f"To:   {to_email}\n")
            f.write(f"Link: {magic_url}\n")
            f.write("---\n")
        print(f"\n[fake-postmark] {magic_url}", file=sys.stderr, flush=True)
        return {
            "status": 200,
            "message_id": "stub-local-staging",
            "error_code": 0,
            "message": "OK (local staging stub)",
            "to": to_email,
            "submitted_at": None,
            "raw": {},
        }

    ml.send_postmark_magic_link = fake_send

    deploy_srv.init_auth()
    # Diagnostics blob has a build_meta field the prod server populates
    # from a separate code path; tests set it to {}, we do the same.
    deploy_srv.BUILD_META = {}

    # deploy/server.py omits COOP / COEP intentionally — they're set by
    # Caddy at the edge in prod (see deploy/server.py:210-216 and
    # ansible/roles/caddy/templates/Caddyfile.j2). Without them OPFS-
    # SAH-Pool refuses to install in the browser and folder mode can't
    # be tested. Add them at the local-staging layer so the in-browser
    # experience matches prod behavior.
    _OrigHandler = deploy_srv.Handler

    class LocalStagingHandler(_OrigHandler):
        def _security_headers(self) -> None:  # type: ignore[override]
            super()._security_headers()
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")

    handler_factory = partial(LocalStagingHandler, directory=str(DIST_DIR))
    httpd = deploy_srv.ThreadingHTTPServer(("127.0.0.1", PORT), handler_factory)

    sys.stderr.write(
        "\n"
        "╭──────────────────────────────────────────────────────╮\n"
        "│ Local staging server                                  │\n"
        f"│ http://127.0.0.1:{PORT}/                                │\n"
        f"│ Test email:  {email:<40s}│\n"
        "│ Magic links: just serve-prod-link (latest)            │\n"
        "│               tail -F tmp/prod-local/magic_links.log  │\n"
        "│ Stop:        Ctrl-C                                   │\n"
        "╰──────────────────────────────────────────────────────╯\n"
        "\n"
    )
    sys.stderr.flush()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nShutting down…\n")
        httpd.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local staging server (deploy/server.py + auth + stubbed Postmark)."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe tmp/prod-local/ and rebuild the dist from current sources.",
    )
    parser.add_argument(
        "--email",
        default=DEFAULT_TEST_EMAIL,
        help=f"Email to allowlist (default: {DEFAULT_TEST_EMAIL}).",
    )
    args = parser.parse_args()

    if args.reset and TMP_DIR.is_dir():
        shutil.rmtree(TMP_DIR)
        print(f"  Reset {TMP_DIR.relative_to(REPO_ROOT)}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    _build_dist(force=args.reset)
    _allowlist_test_email(args.email)
    _start_server(args.email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
