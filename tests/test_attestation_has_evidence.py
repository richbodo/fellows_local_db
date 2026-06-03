"""The conformance attestation is a Security Target: a `conformant` claim with
no executable evidence is a finding.

This checker parses the AC/CST attestation tables in docs/Architecture.md and
asserts that every row claiming `conformant` (and not `partial`) cites either:
  - a resolvable test ref (`path/to/test.py[::name]` — file exists, and if a
    `::name` is given, a `def name` or `class name` exists in it); or
  - an explicitly declared non-test verification kind (human-review / LLM rubric
    / code inspection / by architecture / by bounding / by construction).

A bare doc pointer (`*.md`) is NOT evidence — a doc that asserts a property does
not prove it. `partial` / `Open` / `not-applicable` rows are exempt from
resolution (they're honestly aspirational) but keep their status.

Rationale + the convention this enforces: plans/conformance_discipline.md. This
is the regression net for the class of bug where the gate attested
`conformant` for durability properties its code never enforced
(plans/private_data_enforcement.md).
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCH_MD = os.path.join(REPO_ROOT, "docs", "Architecture.md")

# Declared non-test verification kinds (case-insensitive substring match).
_REVIEW_KINDS = (
    "human-review", "human review", "llm rubric", "code inspection",
    "by architecture", "by bounding", "by construction", "architectural",
)

# A path-like Python ref, optionally `::name`. The leading boundary stops it
# matching mid-token (e.g. the `deploy` inside `test_deploy_*`); refs may be
# full (`tests/e2e/x.py`) or the doc's bare-filename shorthand (`x.py`).
_TEST_REF = re.compile(r"(?<![\w./-])[\w./-]+\.py(?:::\w+)?")

# Dirs that hold referenceable code; used to resolve the bare-filename shorthand.
_CODE_DIRS = ("tests", "build", "deploy", "app", "mcp_servers", "scripts")
_PY_INDEX = None


def _py_index():
    """basename -> [abspaths] over the code dirs (built once)."""
    global _PY_INDEX
    if _PY_INDEX is None:
        _PY_INDEX = {}
        for d in _CODE_DIRS:
            for root, _dirs, files in os.walk(os.path.join(REPO_ROOT, d)):
                for fn in files:
                    if fn.endswith(".py"):
                        _PY_INDEX.setdefault(fn, []).append(os.path.join(root, fn))
    return _PY_INDEX


def _split_row(line):
    """Split a markdown table row into trimmed cells (drop leading/trailing |)."""
    parts = line.strip().strip("|").split("|")
    return [c.strip() for c in parts]


def _is_separator(line):
    return bool(re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", line)) and "-" in line


def _parse_attestation_rows(md_text):
    """Yield (row_id, verification_cell, status_cell) for every data row of every
    table that has both a 'Verification' and a 'Status' column header."""
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            header = _split_row(line)
            lower = [h.lower() for h in header]
            if "verification" in lower and "status" in lower:
                v_idx, s_idx = lower.index("verification"), lower.index("status")
                j = i + 2
                while j < len(lines) and lines[j].lstrip().startswith("|") and not _is_separator(lines[j]):
                    cells = _split_row(lines[j])
                    if len(cells) > max(v_idx, s_idx):
                        yield cells[0], cells[v_idx], cells[s_idx]
                    j += 1
                i = j
                continue
        i += 1


def _resolve_test_ref(ref):
    """Return (ok, detail) for a `path.py[::name]` ref. Full paths resolve from
    the repo root; bare filenames resolve via the code-dir index."""
    path, _, name = ref.partition("::")
    if "/" in path:
        cands = [os.path.join(REPO_ROOT, path)]
        cands = [c for c in cands if os.path.isfile(c)]
    else:
        cands = _py_index().get(os.path.basename(path), [])
    if not cands:
        return False, f"file {path!r} not found"
    if name:
        for c in cands:
            with open(c, encoding="utf-8") as f:
                src = f.read()
            if f"def {name}" in src or f"class {name}" in src:
                return True, ""
        return False, f"no `def {name}` / `class {name}` in {path!r}"
    return True, ""


def _is_full_conformant(status_cell):
    s = status_cell.lower()
    return "conformant" in s and "partial" not in s


def test_architecture_md_exists():
    assert os.path.isfile(ARCH_MD), f"attestation source missing: {ARCH_MD}"


def test_every_conformant_row_has_executable_evidence():
    with open(ARCH_MD, encoding="utf-8") as f:
        md = f.read()

    rows = list(_parse_attestation_rows(md))
    assert rows, "no attestation tables parsed — did the table format change?"

    findings = []
    for row_id, verification, status in rows:
        if not _is_full_conformant(status):
            continue  # partial / Open / not-applicable → exempt by design
        haystack = (verification + " " + status).lower()
        refs = _TEST_REF.findall(verification + " " + status)
        if refs:
            for ref in refs:
                ok, detail = _resolve_test_ref(ref)
                if not ok:
                    findings.append(f"{row_id}: dangling evidence — {detail}")
        elif any(kind in haystack for kind in _REVIEW_KINDS):
            continue  # declared non-test verification kind
        else:
            findings.append(
                f"{row_id}: claims `conformant` with no executable test and no "
                f"declared verification kind (doc-only is not evidence) — "
                f"verification={verification!r}"
            )

    assert not findings, (
        "Attestation rows claim conformance without executable evidence "
        "(see plans/conformance_discipline.md § Evidence rule):\n  - "
        + "\n  - ".join(findings)
    )
