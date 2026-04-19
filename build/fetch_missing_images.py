#!/usr/bin/env python3
"""Download fellow profile images from Knack S3 for any fellow missing a local file.

Reads ``final_fellows_set/knack_api_detail_dump.json``. For each fellow:
  - Computes the slug from ``field_10_raw.full`` (same rule the DB uses).
  - Looks for an existing ``final_fellows_set/fellow_profile_images_by_name/<slug>.{jpg,jpeg,png}``.
  - If absent, downloads from ``field_299_raw.url`` (Knack's S3-hosted copy) and
    saves as ``<slug>.<ext>`` where ``<ext>`` is chosen from the response
    Content-Type. Defaults to ``.jpg`` for ``image/jpeg`` (including ``.jpeg``
    filenames on S3).

Stdlib-only. Concurrent via ``concurrent.futures.ThreadPoolExecutor``. Tolerant
of 403/404/network errors — logs and continues. Idempotent: re-runs skip
anything already on disk.

Usage:
    python build/fetch_missing_images.py            # ~60s for the typical gap
    python build/fetch_missing_images.py --dry-run  # list what would be fetched
    python build/fetch_missing_images.py --limit 5  # smoke-test a few
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DETAIL_JSON = REPO_ROOT / "final_fellows_set" / "knack_api_detail_dump.json"
IMAGES_DIR = REPO_ROOT / "final_fellows_set" / "fellow_profile_images_by_name"

CONTENT_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def slugify(text: str) -> str:
    if not text or not str(text).strip():
        return ""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.lower().strip()).strip("_") or ""


def existing_slugs() -> set[str]:
    """Return alpha-normalized stems of existing image files (matches the DB's fuzzy index)."""
    if not IMAGES_DIR.is_dir():
        return set()
    stems = set()
    for p in IMAGES_DIR.iterdir():
        if not p.is_file() or p.suffix.lower() not in IMG_EXTS:
            continue
        stems.add(re.sub(r"[^a-z0-9]", "", p.stem.lower()))
    return stems


def download_one(url: str, out_path_stem: Path, timeout: int = 30) -> tuple[bool, str]:
    """Download URL, save to out_path_stem + extension inferred from Content-Type.

    Returns (ok, message). Doesn't raise.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "fellows-local-db-image-recovery/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            ext = CONTENT_TYPE_TO_EXT.get(ctype, ".jpg")
            body = resp.read()
        final_path = out_path_stem.with_suffix(ext)
        final_path.write_bytes(body)
        return True, f"saved {final_path.name} ({len(body):,} B, {ctype})"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return False, f"error: {e}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--detail",
        default=str(DETAIL_JSON),
        help=f"Knack detail-dump JSON (default: {DETAIL_JSON})",
    )
    ap.add_argument(
        "--images-dir",
        default=str(IMAGES_DIR),
        help=f"Target directory (default: {IMAGES_DIR})",
    )
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="If >0, only fetch first N missing")
    ap.add_argument("--dry-run", action="store_true", help="List missing without downloading")
    args = ap.parse_args(argv)

    detail_path = Path(args.detail)
    images_dir = Path(args.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    with open(detail_path, "r", encoding="utf-8") as f:
        detail = json.load(f)
    if not isinstance(detail, dict):
        print(f"expected dict-of-records at top level; got {type(detail).__name__}", file=sys.stderr)
        return 1

    have = existing_slugs()
    todo: list[tuple[str, str, Path]] = []
    for rid, raw in detail.items():
        # Prefer the raw name's `full` (matches restore_from_knack_scrapefile.py).
        name_raw = raw.get("field_10_raw")
        if isinstance(name_raw, dict) and name_raw.get("full"):
            name = str(name_raw["full"]).strip("\n\r\t ")
        else:
            name = str(raw.get("field_10") or "").strip()
        if not name:
            continue
        slug = slugify(name)
        if not slug:
            continue
        alpha = re.sub(r"[^a-z0-9]", "", slug)
        if alpha in have:
            continue

        rv = raw.get("field_299_raw")
        url = rv.get("url") if isinstance(rv, dict) else None
        if not url:
            continue

        out_stem = images_dir / slug
        todo.append((name, url, out_stem))

    if args.limit > 0:
        todo = todo[: args.limit]

    print(f"Fellows with local image already: {len(have)}")
    print(f"Fellows missing local image (will fetch): {len(todo)}")

    if args.dry_run:
        for name, url, stem in todo[:20]:
            print(f"  would fetch: {name:30s} → {stem.with_suffix('.<ext>').name}")
        if len(todo) > 20:
            print(f"  … and {len(todo) - 20} more")
        return 0

    ok = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = {
            ex.submit(download_one, url, stem): (name, stem)
            for name, url, stem in todo
        }
        for i, fut in enumerate(as_completed(futures), start=1):
            name, stem = futures[fut]
            success, msg = fut.result()
            status = "ok " if success else "FAIL"
            # Limit per-line verbosity; only print fails or every 20th success
            if not success:
                failed += 1
                print(f"[{i:3}/{len(todo)}] {status}  {name}: {msg}")
            else:
                ok += 1
                if i % 20 == 0 or i == len(todo):
                    print(f"[{i:3}/{len(todo)}] {status}  {name}: {msg}")

    print(f"\nDone: {ok} ok, {failed} failed, {len(todo)} attempted.")
    print("Next: python build/restore_from_knack_scrapefile.py  (backfills has_image=1 for new files)")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
