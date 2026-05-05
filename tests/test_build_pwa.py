"""Unit tests for build/build_pwa.py helpers.

Phase 3 of plans/local_first_worker_architecture.md added
`compute_fellows_db_sha` and the `write_build_meta` `fellows_db_sha`
field. The worker side is exercised via tests/e2e/test_versioned_fellows_db.py;
this module pins the Python helper's contract independently — equal
SHA → no fetch hinges on both ends agreeing on `hashlib.sha256` over
the raw file bytes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from build.build_pwa import compute_fellows_db_sha, write_build_meta


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
