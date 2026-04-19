#!/usr/bin/env python3
"""One-shot: restore app/fellows.db from the Apr 8 Knack-API snapshot.

The current app/fellows.db is the demo-filtered subset (442 fellows, 268
contact emails) — a regression from the Apr 8 full REST-API extraction
(515 fellows, 515 emails). The regression dropped ~73 fellows and 247
contact emails, breaking magic-link delivery for everyone not in the
demo subset — including the operator.

The Apr 8 backup (``app/fellows.db.backup.2026-04-08``) predates PR #19
which added the ``has_image`` column, so we ALTER TABLE and backfill by
scanning ``final_fellows_set/fellow_profile_images_by_name/`` using the
same alpha-fuzzy match as ``import_json_to_sqlite.py:slug_has_image``.
FTS5 is rebuilt defensively.

After running this:

    python build/build_pwa.py                      # regenerates dist + allowed_emails.json
    ./scripts/deploy_pwa.sh --ask-become-pass      # deploys
    scripts/debug_email_delivery.py --dump-allowlist  # verifies 515/515 in sync

Idempotent: re-running is safe. Existing has_image values are
recomputed; existing DB is backed up before overwrite.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DB = REPO_ROOT / "app" / "fellows.db.backup.2026-04-08"
DST_DB = REPO_ROOT / "app" / "fellows.db"
IMAGES_DIR_SOURCE = REPO_ROOT / "final_fellows_set" / "fellow_profile_images_by_name"
IMAGES_DIR_APP = REPO_ROOT / "app" / "fellow_profile_images_by_name"


def build_image_index() -> dict[str, Path]:
    """Alpha-normalized filename stem → Path, mirroring import_json_to_sqlite."""
    d = None
    if IMAGES_DIR_SOURCE.is_dir():
        d = IMAGES_DIR_SOURCE
    elif IMAGES_DIR_APP.is_dir():
        d = IMAGES_DIR_APP
    if not d:
        return {}
    index: dict[str, Path] = {}
    for p in d.iterdir():
        if not p.is_file() or p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        stem_alpha = re.sub(r"[^a-z0-9]", "", p.stem.lower())
        if stem_alpha and stem_alpha not in index:
            index[stem_alpha] = p
    return index


def main() -> int:
    if not SRC_DB.is_file():
        print(f"Source DB not found: {SRC_DB}", file=sys.stderr)
        print(
            "This script restores from app/fellows.db.backup.2026-04-08 which "
            "is the full Knack REST-API extraction snapshot. If that file is "
            "absent, the only recovery path is to re-run the Knack ETL against "
            "final_fellows_set/knack_api_detail_dump.json (see Fix B follow-up).",
            file=sys.stderr,
        )
        return 1

    if DST_DB.is_file():
        backup_name = f"fellows.db.before-restore.{date.today().isoformat()}"
        shutil.copy2(DST_DB, DST_DB.parent / backup_name)
        print(f"Backed up existing DB to app/{backup_name}")

    shutil.copy2(SRC_DB, DST_DB)
    print(f"Copied {SRC_DB.name} → {DST_DB.name}")

    conn = sqlite3.connect(DST_DB)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(fellows)").fetchall()}
    if "has_image" not in cols:
        conn.execute(
            "ALTER TABLE fellows ADD COLUMN has_image INTEGER NOT NULL DEFAULT 0"
        )
        print("Added has_image column (was absent in Apr 8 schema)")

    image_index = build_image_index()
    if not image_index:
        print(
            "Warning: no images directory found; has_image will be 0 for everyone. "
            "Run `ls final_fellows_set/fellow_profile_images_by_name` to confirm.",
            file=sys.stderr,
        )

    rows = conn.execute("SELECT record_id, slug FROM fellows").fetchall()
    for rid, slug in rows:
        if not slug:
            continue
        base_alpha = re.sub(r"[^a-z0-9]", "", slug.split("/")[-1].split(".")[0].lower())
        has_img = 1 if base_alpha and base_alpha in image_index else 0
        conn.execute(
            "UPDATE fellows SET has_image = ? WHERE record_id = ?", (has_img, rid)
        )

    # Defensive FTS5 rebuild — the backup's FTS index might not include new
    # rows or the right columns given older schema. Cheap and safe.
    conn.execute("INSERT INTO fellows_fts(fellows_fts) VALUES('rebuild')")
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM fellows").fetchone()[0]
    with_image = conn.execute(
        "SELECT COUNT(*) FROM fellows WHERE has_image = 1"
    ).fetchone()[0]
    with_email = conn.execute(
        "SELECT COUNT(*) FROM fellows "
        "WHERE contact_email IS NOT NULL AND trim(contact_email) != ''"
    ).fetchone()[0]
    conn.close()

    print(
        f"Restored {count} fellows ({with_image} with image, {with_email} with email)"
    )
    print("Next: python build/build_pwa.py && ./scripts/deploy_pwa.sh --ask-become-pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
