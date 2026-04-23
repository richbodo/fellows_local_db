#!/usr/bin/env python3
"""Assemble deploy/dist/ from app/static/ for production (Python stdlib only).

Copies static assets, sqlite-wasm vendor files, fellows.db, and profile images.
Writes allowed_emails.json (SHA-256 of lowercased contact_email) for Phase 4 magic-link gate.
"""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "app" / "static"
DIST_DIR = REPO_ROOT / "deploy" / "dist"
DB_SRC = REPO_ROOT / "app" / "fellows.db"
IMAGES_SRC = REPO_ROOT / "app" / "fellow_profile_images_by_name"
IMAGES_FALLBACK = REPO_ROOT / "final_fellows_set" / "fellow_profile_images_by_name"


def write_build_meta(dest: Path) -> None:
    """Fingerprint for deploy debugging (client vs server bundle drift)."""
    git_sha = None
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            git_sha = (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        pass
    meta = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha,
        "generator": "build/build_pwa.py",
    }
    dest.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def write_allowed_email_hashes(db_path: Path, dest_json: Path) -> None:
    """SHA-256 hex of lowercased contact_email per Phase 4 plan."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            SELECT DISTINCT lower(trim(contact_email)) AS e
            FROM fellows
            WHERE contact_email IS NOT NULL AND trim(contact_email) != ''
            """
        )
        hashes = []
        seen = set()
        for (raw,) in cur.fetchall():
            if not raw:
                continue
            h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if h not in seen:
                seen.add(h)
                hashes.append(h)
        dest_json.write_text(json.dumps({"hashes": hashes}, indent=0) + "\n", encoding="utf-8")
    finally:
        conn.close()


def main() -> int:
    if not STATIC_DIR.is_dir():
        print(f"Missing static directory: {STATIC_DIR}", file=sys.stderr)
        return 1
    DIST_DIR.parent.mkdir(parents=True, exist_ok=True)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    shutil.copytree(STATIC_DIR, DIST_DIR)
    write_build_meta(DIST_DIR / "build-meta.json")
    if DB_SRC.is_file():
        shutil.copy2(DB_SRC, DIST_DIR / "fellows.db")
        write_allowed_email_hashes(DB_SRC, DIST_DIR / "allowed_emails.json")
    else:
        print(f"Warning: no database at {DB_SRC} — run build/restore_from_knack_scrapefile.py", file=sys.stderr)
    img_src = IMAGES_SRC if IMAGES_SRC.is_dir() else (IMAGES_FALLBACK if IMAGES_FALLBACK.is_dir() else None)
    if img_src:
        dest = DIST_DIR / "images"
        dest.mkdir(parents=True, exist_ok=True)
        for p in img_src.iterdir():
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                shutil.copy2(p, dest / p.name)
    nfiles = sum(1 for p in DIST_DIR.rglob("*") if p.is_file())
    print(f"Wrote {DIST_DIR} ({nfiles} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
