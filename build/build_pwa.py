#!/usr/bin/env python3
"""Assemble deploy/dist/ from app/static/ for production (Python stdlib only).

Phase 2 extends this to include fellows.db and profile images under dist/.
"""

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "app" / "static"
DIST_DIR = REPO_ROOT / "deploy" / "dist"


def main() -> int:
    if not STATIC_DIR.is_dir():
        print(f"Missing static directory: {STATIC_DIR}", file=sys.stderr)
        return 1
    DIST_DIR.parent.mkdir(parents=True, exist_ok=True)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    shutil.copytree(STATIC_DIR, DIST_DIR)
    nfiles = sum(1 for p in DIST_DIR.rglob("*") if p.is_file())
    print(f"Wrote {DIST_DIR} ({nfiles} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
