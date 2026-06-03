#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Conformance guard shared by the Stop / SubagentStop hooks.

Fails loudly (the calling hook exits 2) when a session's changes either:
  A. touch the conformance attestation (docs/Architecture.md attestation rows)
     without touching any test, or
  B. add a deferral comment to a frontier file without also adding a strict-xfail.

See plans/conformance_discipline.md + CLAUDE.md § Conformance discipline. The
decision lives in the pure `_decide()` (unit-tested in
tests/test_conformance_guard.py); `check()` wires it to `git diff`. Everything
fails OPEN — any error returns None so the guard can never wedge a session.
"""
import os
import subprocess
from pathlib import Path

# .claude/hooks/utils/conformance_guard.py -> repo root is parents[3].
REPO_ROOT = Path(__file__).resolve().parents[3]

ATTESTATION_FILE = "docs/Architecture.md"
FRONTIER_FILES = (
    "app/static/app.js",
    "app/static/vendor/sqlite-worker.js",
    "deploy/server.py",
    "app/server.py",
)
# High-signal deferral phrases — the exact shapes that hid the gate-enforcement
# gap ("lands later/together", "inert for now"). Kept tight to avoid flagging
# every "TODO".
DEFERRAL_PHRASES = (
    "lands later", "lands together", "deferred", "not yet enforced",
    "will be enforced", "inert for now",
)

_ATTEST_MSG = (
    "[conformance-guard] docs/Architecture.md attestation changed without "
    "touching tests/. A `conformant` row needs executable evidence; a softened "
    "row needs an honest status. Run `pytest tests/test_attestation_has_evidence.py` "
    "and add/adjust the negative test, or explain why no test change is needed. "
    "(CLAUDE.md § Conformance discipline)"
)
_DEFERRAL_MSG = (
    "[conformance-guard] a deferral comment was added to a frontier file ({f}) "
    "without a strict-xfail. Deferrals live in the attestation or as a "
    "`@pytest.mark.xfail(strict=True)` test naming the plan PR — never a code "
    "comment. (CLAUDE.md § Conformance discipline)"
)


def _git(args):
    try:
        out = subprocess.run(
            ["git"] + args, cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def _changed_files():
    files = set()
    for spec in (["diff", "--name-only", "HEAD"], ["diff", "--name-only", "main...HEAD"]):
        for line in _git(spec).splitlines():
            line = line.strip()
            if line:
                files.add(line)
    return files


def _added_lines(path):
    added = []
    for spec in (["diff", "HEAD", "--", path], ["diff", "main...HEAD", "--", path]):
        for line in _git(spec).splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
    return added


def _attestation_rows_changed(added_arch_lines):
    """Only fire when actual attestation rows changed — not any doc edit."""
    return any(
        ("conformant" in l.lower() or "partial-conformance" in l.lower())
        for l in added_arch_lines
    )


def _decide(changed, added_by_file):
    """Pure decision. Returns a block message, or None to allow. Unit-tested."""
    msgs = []
    if ATTESTATION_FILE in changed and _attestation_rows_changed(
        added_by_file.get(ATTESTATION_FILE, [])
    ):
        if not any(f.startswith("tests/") for f in changed):
            msgs.append(_ATTEST_MSG)

    any_xfail_added = any(
        "xfail(strict" in l
        for lines in added_by_file.values()
        for l in lines
    )
    for f in FRONTIER_FILES:
        if f not in changed:
            continue
        added = added_by_file.get(f, [])
        if any(p in l.lower() for l in added for p in DEFERRAL_PHRASES):
            if not any_xfail_added:
                msgs.append(_DEFERRAL_MSG.format(f=f))
                break

    return "\n".join(msgs) if msgs else None


def check():
    """Run the guard against the live working tree. Returns a message or None."""
    try:
        changed = _changed_files()
        if not changed:
            return None
        watch = set(FRONTIER_FILES) | {ATTESTATION_FILE}
        added_by_file = {f: _added_lines(f) for f in watch if f in changed}
        return _decide(changed, added_by_file)
    except Exception:
        return None  # fail open — never wedge a session
