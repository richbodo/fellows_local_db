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

# Source-tracked placeholders in app/static/app.js and app/static/sw.js,
# substituted at build time (here) and at request time (app/server.py for
# dev). Format of the substituted value: <YYYY-MM-DD>-<short-sha>. Both
# substitutions use compute_build_label() below so dev and prod agree on
# what the badge shows.
PLACEHOLDER_UI_DIAG = "__FELLOWS_UI_DIAG__"
PLACEHOLDER_CACHE_VERSION = "__CACHE_VERSION__"


def get_short_sha(repo_root: Path = REPO_ROOT) -> str | None:
    """Current git short SHA, or None if git isn't available."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            return (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def compute_build_label(repo_root: Path = REPO_ROOT) -> str:
    """`<YYYY-MM-DD>-<short-sha>` — what gets baked into the bundle.

    Falls back to `<YYYY-MM-DD>-unknown` if git isn't reachable so the
    placeholder never survives substitution. The SHA piece is what makes
    each build uniquely identifiable; the date piece is for human eyes
    on the build badge.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sha = get_short_sha(repo_root) or "unknown"
    return f"{today}-{sha}"


def substitute_build_label(text: str, label: str) -> str:
    """Replace both PWA placeholders with `label`. Pure function — same
    text in dev and dist as long as the label matches."""
    return text.replace(PLACEHOLDER_UI_DIAG, label).replace(
        PLACEHOLDER_CACHE_VERSION, label
    )


def stamp_static_assets(dist_dir: Path, label: str) -> None:
    """Substitute `__FELLOWS_UI_DIAG__` and `__CACHE_VERSION__` in the
    files that carry them. No-op if the placeholders aren't present
    (e.g., a partial rebuild on already-stamped output).

    vendor/sqlite-worker.js carries the same placeholder so the worker
    handshake (init response → buildLabel) reports the running build —
    used by the ?diag=1 panel and bug reports for triage. Stamping it
    here keeps prod consistent with the dev server (app/server.py),
    which performs the same substitution on the same file list at serve
    time.
    """
    for relpath in ("app.js", "sw.js", "vendor/sqlite-worker.js"):
        target = dist_dir / relpath
        if not target.is_file():
            continue
        original = target.read_text(encoding="utf-8")
        stamped = substitute_build_label(original, label)
        if stamped != original:
            target.write_text(stamped, encoding="utf-8")


def compute_fellows_db_sha(db_path: Path) -> str | None:
    """SHA-256 hex of the `fellows.db` bytes, or None if the file is missing.

    The PWA worker's `ensureFellowsDb` compares this to the SHA recorded
    in OPFS-side `fellows.db.meta.json` to decide whether to re-fetch
    `/fellows.db`. Computed over the raw file bytes so the dev server
    and the build pipeline produce identical values for identical DBs.
    """
    if not db_path.is_file():
        return None
    h = hashlib.sha256()
    with db_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_build_meta(dest: Path, label: str, db_path: Path | None = None) -> None:
    """Fingerprint for deploy debugging (client vs server bundle drift).

    The git_sha here matches the SHA-half of the build label so a single
    server response can be cross-referenced against a single source
    revision. built_at is UTC, ISO-8601, second-resolution.

    `fellows_db_sha` (Phase 3 of the local-first worker plan) gates the
    PWA worker's per-boot re-import of `/fellows.db`: equal SHA → no
    fetch, different SHA → atomic re-import. Omitted when `db_path` is
    None or missing — the worker treats that as "no comparison
    available" and falls back to its Phase 1 cold-start-only behavior.
    """
    sha = label.rsplit("-", 1)[-1] if label else None
    meta = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": sha,
        "build_label": label,
        "generator": "build/build_pwa.py",
    }
    if db_path is not None:
        fellows_sha = compute_fellows_db_sha(db_path)
        if fellows_sha is not None:
            meta["fellows_db_sha"] = fellows_sha
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
    label = compute_build_label()
    stamp_static_assets(DIST_DIR, label)
    write_build_meta(DIST_DIR / "build-meta.json", label, db_path=DB_SRC)
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
    print(f"Wrote {DIST_DIR} ({nfiles} files)  build_label={label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
