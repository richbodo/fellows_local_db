"""Unit tests for build/build_pwa.py helpers.

Phase 3 of plans/local_first_worker_architecture.md added
`compute_fellows_db_sha` and the `write_build_meta` `fellows_db_sha`
field. The worker side is exercised via tests/e2e/test_versioned_fellows_db.py;
this module pins the Python helper's contract independently — equal
SHA → no fetch hinges on both ends agreeing on `hashlib.sha256` over
the raw file bytes.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from build.build_pwa import (
    PLACEHOLDER_APP_JS_INTEGRITY,
    PLACEHOLDER_JSPDF_INTEGRITY,
    compute_fellows_db_sha,
    compute_sri_hash,
    compute_sri_hash_bytes,
    stamp_sri_attributes,
    write_build_meta,
)


def test_compute_fellows_db_sha_matches_hashlib(tmp_path: Path):
    """SHA must match `hashlib.sha256` over the raw file bytes — same
    invariant the worker assumes when comparing meta.sha to the
    server-reported `fellows_db_sha`. If the helper ever switches to a
    different digest or changes input encoding, this catches it before
    every returning visitor's worker silently re-imports."""
    db_path = tmp_path / "fellows.db"
    payload = b"some bytes that look like a sqlite file"
    db_path.write_bytes(payload)

    assert compute_fellows_db_sha(db_path) == hashlib.sha256(payload).hexdigest()


def test_compute_fellows_db_sha_handles_chunked_read(tmp_path: Path):
    """Hash is computed by streaming 1-MiB chunks; verify a >1 MiB file
    rolls up to the same digest as a one-shot hash. Guards against a
    chunk-boundary bug that would only surface on real production-sized
    fellows.db files."""
    db_path = tmp_path / "fellows.db"
    payload = b"a" * (3 * (1 << 20) + 137)  # 3 MiB + change → spans 4 chunks
    db_path.write_bytes(payload)

    assert compute_fellows_db_sha(db_path) == hashlib.sha256(payload).hexdigest()


def test_compute_fellows_db_sha_returns_none_for_missing_file(tmp_path: Path):
    """Returns None rather than raising; `write_build_meta` uses this to
    decide whether to omit `fellows_db_sha` from the meta blob."""
    assert compute_fellows_db_sha(tmp_path / "does-not-exist.db") is None


def test_write_build_meta_omits_sha_when_db_path_is_none(tmp_path: Path):
    """When the build does not point at a DB, `fellows_db_sha` must be
    omitted entirely — not emitted as null. The worker treats absence
    as 'no comparison available' and falls back to cold-start-only
    behavior; a stray null would compare unequal to every real digest
    and force a re-fetch on every boot."""
    dest = tmp_path / "build-meta.json"
    write_build_meta(dest, "2026-05-06-abcdef0", db_path=None)

    meta = json.loads(dest.read_text())
    assert "fellows_db_sha" not in meta
    assert meta["build_label"] == "2026-05-06-abcdef0"
    assert meta["git_sha"] == "abcdef0"
    assert meta["generator"] == "build/build_pwa.py"


def test_write_build_meta_omits_sha_when_db_file_is_missing(tmp_path: Path):
    """db_path given but file doesn't exist → still treated as 'no
    comparison available' rather than raising. A botched build that
    points at a missing DB shouldn't crash meta-emission."""
    dest = tmp_path / "build-meta.json"
    write_build_meta(dest, "2026-05-06-abcdef0", db_path=tmp_path / "nope.db")

    meta = json.loads(dest.read_text())
    assert "fellows_db_sha" not in meta


def test_write_build_meta_emits_sha_when_db_file_exists(tmp_path: Path):
    """Happy path: real db_path → `fellows_db_sha` appears in the JSON
    and matches `compute_fellows_db_sha` for the same bytes. End-to-end
    proof that build-meta.json is wired through to the worker's gate."""
    db_path = tmp_path / "fellows.db"
    db_path.write_bytes(b"hello")
    dest = tmp_path / "build-meta.json"

    write_build_meta(dest, "2026-05-06-abcdef0", db_path=db_path)
    meta = json.loads(dest.read_text())

    assert meta["fellows_db_sha"] == hashlib.sha256(b"hello").hexdigest()
    assert meta["fellows_db_sha"] == compute_fellows_db_sha(db_path)


def test_compute_sri_hash_bytes_matches_spec(tmp_path: Path):
    """SRI hash format is `sha384-<base64(digest)>` per the W3C spec.
    Browsers compute the digest the same way; if this helper drifts,
    every page load fails at script-tag-integrity-check time."""
    payload = b"console.log('hi');"
    expected = "sha384-" + base64.b64encode(hashlib.sha384(payload).digest()).decode("ascii")
    assert compute_sri_hash_bytes(payload) == expected
    assert compute_sri_hash_bytes(payload).startswith("sha384-")


def test_compute_sri_hash_reads_path_bytes(tmp_path: Path):
    """`compute_sri_hash(path)` is `compute_sri_hash_bytes(path.read_bytes())`.
    Pin the equivalence so a future "stream the file in chunks" rewrite
    doesn't silently change the hash for non-trivial inputs."""
    payload = b"a" * (3 * (1 << 20) + 7)  # >1 MiB so a chunked impl would matter
    p = tmp_path / "blob.js"
    p.write_bytes(payload)
    assert compute_sri_hash(p) == compute_sri_hash_bytes(payload)


def test_stamp_sri_attributes_substitutes_index_html(tmp_path: Path):
    """End-to-end: with a dist dir holding `index.html` (placeholders),
    `app.js`, and `vendor/jspdf-...js`, `stamp_sri_attributes` rewrites
    the placeholders in-place. Hashes must match the post-stamp bytes."""
    (tmp_path / "vendor").mkdir()
    app_js_bytes = b"// stamped app.js bytes"
    jspdf_bytes = b"// jspdf vendored bytes"
    (tmp_path / "app.js").write_bytes(app_js_bytes)
    (tmp_path / "vendor" / "jspdf-2.5.1.umd.min.js").write_bytes(jspdf_bytes)
    (tmp_path / "index.html").write_text(
        f'<script src="/vendor/jspdf-2.5.1.umd.min.js" '
        f'integrity="{PLACEHOLDER_JSPDF_INTEGRITY}" crossorigin="anonymous"></script>\n'
        f'<script src="/app.js" integrity="{PLACEHOLDER_APP_JS_INTEGRITY}" '
        f'crossorigin="anonymous"></script>\n',
        encoding="utf-8",
    )

    stamp_sri_attributes(tmp_path)

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert PLACEHOLDER_APP_JS_INTEGRITY not in html
    assert PLACEHOLDER_JSPDF_INTEGRITY not in html
    assert compute_sri_hash_bytes(app_js_bytes) in html
    assert compute_sri_hash_bytes(jspdf_bytes) in html


def test_stamp_sri_attributes_is_noop_when_index_missing(tmp_path: Path):
    """No `index.html` → silent return (no exception, no file created)."""
    stamp_sri_attributes(tmp_path)
    assert not (tmp_path / "index.html").exists()


def test_stamp_sri_attributes_leaves_placeholder_when_target_missing(tmp_path: Path):
    """If a target script is missing, the corresponding placeholder is
    left intact rather than silently dropped. Browser console then shows
    a clear "missing or invalid integrity" error — fail loud, not soft.
    Explicit choice: a missing script during build is a build bug, not
    a graceful-degradation case."""
    (tmp_path / "index.html").write_text(
        f'<script integrity="{PLACEHOLDER_APP_JS_INTEGRITY}"></script>\n'
        f'<script integrity="{PLACEHOLDER_JSPDF_INTEGRITY}"></script>\n',
        encoding="utf-8",
    )
    # Neither app.js nor vendor/jspdf-...js present.
    stamp_sri_attributes(tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert PLACEHOLDER_APP_JS_INTEGRITY in html
    assert PLACEHOLDER_JSPDF_INTEGRITY in html
