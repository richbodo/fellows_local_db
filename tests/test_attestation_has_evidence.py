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

A `conformant` row may NOT cite a test that is `xfail` or unconditionally
`skip`: a declared-false or declared-never-run invariant is not evidence of
conformance. (A conditional `skipif(cond)` is fine — it's an environment guard
that runs in real CI; its runtime status is the report generator's job, not
this static lint.) This is the "marker-state" check — it closes the exact seam
that let `CST-PWA-STORAGE-EVICTABLE` cite an `xfail(strict=True)` test as proof
(plans/conformance_report_and_gate.md). Existence alone was never enough; the
cited test must actually be a live, passing assertion.

Rationale + the convention this enforces: plans/conformance_discipline.md. This
is the regression net for the class of bug where the gate attested
`conformant` for durability properties its code never enforced
(plans/private_data_enforcement.md).
"""
import ast
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


# Markers that *statically* disqualify a cited test from being conformance
# evidence: `xfail` is a declared-false invariant, an unconditional `skip` is a
# declared-never-run one. A conditional `skipif(cond)` is deliberately NOT here
# — it's a legitimate environment guard (e.g. `skipif(not DB.is_file())`) that
# runs and passes in any real CI/dev run; whether it actually ran is a runtime
# fact for the report generator (PR2, which runs tests), not this static lint.
# Note `skipif` does not match `skip` (exact attr-name compare below), so a
# guarded test is left alone.
_DISQUALIFYING_MARKERS = ("xfail", "skip")


def _decorator_marker_names(decorator):
    """Yield every attribute/name id appearing in a decorator expression
    (`@pytest.mark.xfail(...)` -> 'pytest', 'mark', 'xfail'). Walks the whole
    node so multi-line / parametrized decorators are covered. 3.8-safe (no
    ast.unparse)."""
    for node in ast.walk(decorator):
        if isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, ast.Name):
            yield node.id


def _disqualifying_marker(ref):
    """Return the disqualifying marker name (`xfail`/`skip`/`skipif`) decorating
    the cited `path.py::name`, or None. Checks the named function/class node and,
    for a method, its enclosing class. File-only refs (no `::name`) can't be
    attributed to a node and return None (existence still covers them)."""
    path, _, name = ref.partition("::")
    if not name:
        return None
    if "/" in path:
        cands = [os.path.join(REPO_ROOT, path)]
        cands = [c for c in cands if os.path.isfile(c)]
    else:
        cands = _py_index().get(os.path.basename(path), [])
    for c in cands:
        with open(c, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue
        # (node, enclosing_class_decorators) for the matching def/class.
        for class_node, fn in _named_nodes(tree, name):
            decos = list(fn.decorator_list)
            if class_node is not None:
                decos += list(class_node.decorator_list)
            for d in decos:
                ids = set(_decorator_marker_names(d))
                hit = ids & set(_DISQUALIFYING_MARKERS)
                if hit:
                    return sorted(hit)[0]
    return None


def _named_nodes(tree, name):
    """Yield (enclosing_class_or_None, node) for every top-level or one-level-
    nested def/class named `name`."""
    defs = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in tree.body:
        if isinstance(node, defs) and node.name == name:
            yield None, node
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, defs) and child.name == name:
                    yield node, child


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
                    continue
                marker = _disqualifying_marker(ref)
                if marker:
                    findings.append(
                        f"{row_id}: cites `{ref}` as conformant evidence, but that "
                        f"test is `@pytest.mark.{marker}` — a known-false/unrun "
                        f"invariant is not evidence. Drop the citation (other cited "
                        f"tests carry the claim) or fix the test and remove the marker."
                    )
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
