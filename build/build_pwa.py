#!/usr/bin/env python3
"""Assemble deploy/dist/ from app/static/ for production (Python stdlib only).

Copies static assets, sqlite-wasm vendor files, fellows.db, and profile images.

The magic-link allowlist is no longer written to ``dist/`` — the
production server builds it in memory at startup by HMAC-ing every
distinct ``contact_email`` in ``fellows.db`` (see
``deploy/magic_link_auth.py:load_allowlist_from_db``). Keeping it
off-disk means a routing or filesystem mistake cannot expose a hash
file to the public internet.
"""

import base64
import hashlib
import json
import re
import shutil
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

# Subresource Integrity placeholders in app/static/index.html. Substituted
# at build time and at request time so a tampered `app.js` or vendor
# `jspdf-...js` is rejected by the browser before execution. Compute order
# matters: stamp_static_assets must run before stamp_sri_attributes,
# because app.js carries build-label substitutions and the SRI hash must
# cover the *post-stamp* bytes the browser will fetch.
PLACEHOLDER_APP_JS_INTEGRITY = "__APP_JS_INTEGRITY__"
PLACEHOLDER_JSPDF_INTEGRITY = "__JSPDF_INTEGRITY__"

# Files included in the signed bundle manifest. The SW's
# precacheVerified iterates this list (via the served manifest.json),
# fetches each, and re-hashes against the manifest entry before
# accepting. Images are *not* included — they're not security-critical
# and the manifest would balloon to ~250 entries. `fellows.db` is also
# not in the manifest itself; its hash is in `build-meta.json` (which
# IS in the manifest), so its integrity flows transitively through the
# manifest signature.
MANIFEST_INCLUDE_PATHS = (
    "index.html",
    "app.js",
    "sw.js",
    "styles.css",
    "manifest.webmanifest",
    "build-meta.json",
    "vendor/jspdf-2.5.1.umd.min.js",
    "vendor/sqlite-worker.js",
    "vendor/sqlite3.js",
    "vendor/sqlite3.wasm",
    "icons/icon-180.png",
    "icons/icon-192.png",
    "icons/icon-512.png",
    "icons/icon-maskable-192.png",
    "icons/icon-maskable-512.png",
    "icons/favicon-16.png",
    "icons/favicon-32.png",
    "icons/donut-ehf.svg",
)

# Matches the `PROD_PUBLIC_KEY_HEX = '...'` constant in sw.js. The
# captured group is the hex string; if it's the unsubstituted
# `__PROD_PUBLIC_KEY_HEX__` placeholder or any other non-hex value, the
# fingerprint helper returns None.
_PROD_PUBKEY_RE = re.compile(
    r"PROD_PUBLIC_KEY_HEX\s*=\s*['\"]([0-9a-fA-F_]+)['\"]"
)


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


def compute_sri_hash_bytes(b: bytes) -> str:
    """Return ``sha384-<base64>`` for the given bytes — the value the
    browser puts in a script tag's ``integrity`` attribute. SHA-384 is
    SRI's middle option; SHA-256 is acceptable but SHA-384 is the
    common recommendation. Base64 (not base64url) per the SRI spec."""
    digest = hashlib.sha384(b).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def compute_sri_hash(path: Path) -> str:
    """SRI hash for the on-disk bytes at ``path``."""
    return compute_sri_hash_bytes(path.read_bytes())


def stamp_sri_attributes(dist_dir: Path) -> None:
    """Substitute SRI placeholders in ``index.html`` with hashes of the
    scripts the browser will actually fetch.

    Must run AFTER ``stamp_static_assets`` so the hash for ``app.js``
    reflects the build-label-stamped bytes, not the source placeholders.
    No-op when ``index.html`` is missing. If a target script is missing
    the placeholder ships unchanged — that's a fail-loud signal in the
    browser console (broken integrity), not a silent no-op.

    The dev server (``app/server.py``) performs the equivalent
    substitution on ``index.html`` at request time so dev and prod
    enforce the same integrity check.
    """
    index_path = dist_dir / "index.html"
    if not index_path.is_file():
        return
    text = index_path.read_text(encoding="utf-8")
    app_js = dist_dir / "app.js"
    if app_js.is_file():
        text = text.replace(PLACEHOLDER_APP_JS_INTEGRITY, compute_sri_hash(app_js))
    jspdf = dist_dir / "vendor" / "jspdf-2.5.1.umd.min.js"
    if jspdf.is_file():
        text = text.replace(PLACEHOLDER_JSPDF_INTEGRITY, compute_sri_hash(jspdf))
    index_path.write_text(text, encoding="utf-8")


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


def compute_pubkey_fingerprint(sw_js_path: Path) -> str | None:
    """Read ``PROD_PUBLIC_KEY_HEX`` from ``sw.js`` source and return the
    SHA-384 hex fingerprint of the decoded raw public key bytes.

    Returns ``None`` when the constant is missing, when it's the
    ``__PROD_PUBLIC_KEY_HEX__`` placeholder, or when the hex isn't a
    well-formed 65-byte uncompressed P-256 point (130 hex chars).
    Callers (build-meta, magic-link email, About page) treat ``None``
    as "signing not yet configured" and surface that to the user.

    The same fingerprint is what ``scripts/keygen_signing_key.py``
    prints when the operator generates their key, so what's shown on
    the About page should match what arrives in the magic-link email,
    which should match what `keygen` printed at setup. Three
    independent paths to the same value — a defense against any one
    of them being silently swapped.
    """
    try:
        text = sw_js_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _PROD_PUBKEY_RE.search(text)
    if not m:
        return None
    hex_str = m.group(1)
    if "_" in hex_str or len(hex_str) != 130:
        return None
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError:
        return None
    if len(raw) != 65 or raw[0] != 0x04:
        return None
    return hashlib.sha384(raw).hexdigest()


def write_build_meta(
    dest: Path,
    label: str,
    db_path: Path | None = None,
    sw_js_path: Path | None = None,
) -> None:
    """Fingerprint for deploy debugging (client vs server bundle drift).

    The git_sha here matches the SHA-half of the build label so a single
    server response can be cross-referenced against a single source
    revision. built_at is UTC, ISO-8601, second-resolution.

    `fellows_db_sha` (Phase 3 of the local-first worker plan) gates the
    PWA worker's per-boot re-import of `/fellows.db`: equal SHA → no
    fetch, different SHA → atomic re-import. Omitted when `db_path` is
    None or missing — the worker treats that as "no comparison
    available" and falls back to its Phase 1 cold-start-only behavior.

    `pubkey_fingerprint` (security/signed-bundles) carries the SHA-384
    of the prod signing-key public bytes when ``sw_js_path`` points at
    a sw.js whose ``PROD_PUBLIC_KEY_HEX`` has been replaced from the
    placeholder. Omitted otherwise; the About page renders "signing
    not yet configured" when the field is absent.
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
    if sw_js_path is not None:
        fp = compute_pubkey_fingerprint(sw_js_path)
        if fp is not None:
            meta["pubkey_fingerprint"] = fp
    dest.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def write_bundle_manifest(dist_dir: Path, build_label: str) -> Path:
    """Write ``dist/manifest.json`` listing every shell file with its
    SHA-384. The result is what the maintainer signs with
    ``scripts/sign_bundle.py``; the resulting ``manifest.sig`` is the
    trust anchor the service worker verifies on install.

    Must run AFTER ``stamp_static_assets``, ``stamp_sri_attributes``,
    AND ``write_build_meta`` — those each modify or write files this
    manifest hashes over. Missing files are silently skipped; a build
    that lacks an icon won't fail the manifest, but the file the SW
    fetches via the served manifest must match whatever's in this
    list, so any drift between disk and manifest fails-loud at the
    SW's precacheVerified step.

    Output is sorted-key + 2-space JSON so the bytes are deterministic
    for a given input set — important because the signature is over
    these exact bytes.
    """
    files: dict[str, str] = {}
    for relpath in MANIFEST_INCLUDE_PATHS:
        p = dist_dir / relpath
        if p.is_file():
            files[relpath] = compute_sri_hash(p)
    manifest = {
        "version": 1,
        "build_label": build_label,
        "alg": "ECDSA-P256-SHA256",
        "files": files,
    }
    out = dist_dir / "manifest.json"
    out.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out


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
    stamp_sri_attributes(DIST_DIR)
    write_build_meta(
        DIST_DIR / "build-meta.json",
        label,
        db_path=DB_SRC,
        sw_js_path=DIST_DIR / "sw.js",
    )
    write_bundle_manifest(DIST_DIR, label)
    if DB_SRC.is_file():
        shutil.copy2(DB_SRC, DIST_DIR / "fellows.db")
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
