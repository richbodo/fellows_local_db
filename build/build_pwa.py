#!/usr/bin/env python3
"""Assemble deploy/dist/ from app/static/ for production (Python stdlib only).

Copies static assets, sqlite-wasm vendor files, fellows.db, and profile images.
"""

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "app" / "static"
DIST_DIR = REPO_ROOT / "deploy" / "dist"
DB_SRC = REPO_ROOT / "app" / "fellows.db"
IMAGES_SRC = REPO_ROOT / "app" / "fellow_profile_images_by_name"
IMAGES_FALLBACK = REPO_ROOT / "final_fellows_set" / "fellow_profile_images_by_name"


def main() -> int:
    if not STATIC_DIR.is_dir():
        print(f"Missing static directory: {STATIC_DIR}", file=sys.stderr)
        return 1
    DIST_DIR.parent.mkdir(parents=True, exist_ok=True)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    shutil.copytree(STATIC_DIR, DIST_DIR)
    if DB_SRC.is_file():
        shutil.copy2(DB_SRC, DIST_DIR / "fellows.db")
    else:
        print(f"Warning: no database at {DB_SRC} — run build/import_json_to_sqlite.py", file=sys.stderr)
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
