"""Shared conformance-checking logic — the single source of truth for both the
pytest gate (`tests/test_attestation_has_evidence.py`,
`tests/test_xfail_discipline.py`) and the report generator
(`scripts/conformance_report.py`).

Keeping the primitives in one module is the whole point of this effort: the gate
and the report must never disagree about what an attestation row cites or
whether a cited test is a live, non-deferred assertion. If they parsed the
attestation or detected markers differently, the report could read "all green"
while the gate fails — the exact drift class we're trying to kill.

Importable both ways:
  - from tests (repo root is on sys.path via tests/conftest.py) as
    `from scripts.conformance_lib import ...`
  - as a sibling of `scripts/conformance_report.py` when that runs as a script.

Pure stdlib, 3.8-safe (no `ast.unparse`).
"""
import ast
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCH_MD = os.path.join(REPO_ROOT, "docs", "Architecture.md")
TESTS_DIR = os.path.join(REPO_ROOT, "tests")

# Declared non-test verification kinds (case-insensitive substring match).
REVIEW_KINDS = (
    "human-review", "human review", "llm rubric", "code inspection",
    "by architecture", "by bounding", "by construction", "architectural",
)

# A path-like Python ref, optionally `::name`. The leading boundary stops it
# matching mid-token (e.g. the `deploy` inside `test_deploy_*`); refs may be
# full (`tests/e2e/x.py`) or the doc's bare-filename shorthand (`x.py`).
TEST_REF = re.compile(r"(?<![\w./-])[\w./-]+\.py(?:::\w+)?")

# Dirs that hold referenceable code; used to resolve the bare-filename shorthand.
CODE_DIRS = ("tests", "build", "deploy", "app", "mcp_servers", "scripts")
_PY_INDEX = None

# Markers that *statically* disqualify a cited test from being conformance
# evidence: `xfail` is a declared-false invariant, an unconditional `skip` is a
# declared-never-run one. A conditional `skipif(cond)` is deliberately NOT here
# — it's a legitimate environment guard (e.g. `skipif(not DB.is_file())`) that
# runs and passes in any real CI/dev run; whether it actually ran is a runtime
# fact, not a static one. `skipif` does not match `skip` (exact attr-name
# compare), so a guarded test is left alone.
DISQUALIFYING_MARKERS = ("xfail", "skip")

# `tracking: #123` (the `#` is required so it's unambiguously an issue ref).
TRACKING_ANCHOR = re.compile(r"tracking:\s*#(\d+)", re.IGNORECASE)

# At most this many strict-xfail deferrals may exist at once. This project
# builds most features in ~3 PRs; a deferral load past one feature's worth is
# the smell. Keeps the attestation glanceable, not a debt ledger.
DEFERRAL_CAP = 3

# Flavor-derived ACs live in PNT's axes.md (triggered by an axis pick); every
# other AC lives in PNA_Spec.md (universal). Single source of truth for the
# split, consumed by scripts/conformance_report.py (PNT deep-linking) and
# scripts/evaluate_report.py (the toolkit-schema `ac_source` field). Kept here
# because neither can read the PNT repo at runtime.
FLAVOR_DERIVED_ACS = frozenset({
    "AC-2", "AC-3", "AC-5", "AC-8", "AC-12", "AC-13", "AC-14",
    "AC-PRM-B", "AC-PRM-C",
})


# --- Markdown attestation parsing -------------------------------------------

def py_index():
    """basename -> [abspaths] over the code dirs (built once)."""
    global _PY_INDEX
    if _PY_INDEX is None:
        _PY_INDEX = {}
        for d in CODE_DIRS:
            for root, _dirs, files in os.walk(os.path.join(REPO_ROOT, d)):
                for fn in files:
                    if fn.endswith(".py"):
                        _PY_INDEX.setdefault(fn, []).append(os.path.join(root, fn))
    return _PY_INDEX


def split_row(line):
    """Split a markdown table row into trimmed cells (drop leading/trailing |)."""
    parts = line.strip().strip("|").split("|")
    return [c.strip() for c in parts]


def is_separator(line):
    return bool(re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", line)) and "-" in line


def parse_attestation_rows(md_text):
    """Yield (row_id, verification_cell, status_cell) for every data row of every
    table that has both a 'Verification' and a 'Status' column header."""
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < len(lines) and is_separator(lines[i + 1]):
            header = split_row(line)
            lower = [h.lower() for h in header]
            if "verification" in lower and "status" in lower:
                v_idx, s_idx = lower.index("verification"), lower.index("status")
                j = i + 2
                while j < len(lines) and lines[j].lstrip().startswith("|") and not is_separator(lines[j]):
                    cells = split_row(lines[j])
                    if len(cells) > max(v_idx, s_idx):
                        yield cells[0], cells[v_idx], cells[s_idx]
                    j += 1
                i = j
                continue
        i += 1


def resolve_test_ref(ref):
    """Return (ok, detail) for a `path.py[::name]` ref. Full paths resolve from
    the repo root; bare filenames resolve via the code-dir index."""
    path, _, name = ref.partition("::")
    if "/" in path:
        cands = [os.path.join(REPO_ROOT, path)]
        cands = [c for c in cands if os.path.isfile(c)]
    else:
        cands = py_index().get(os.path.basename(path), [])
    if not cands:
        return False, "file {!r} not found".format(path)
    if name:
        for c in cands:
            with open(c, encoding="utf-8") as f:
                src = f.read()
            if "def {}".format(name) in src or "class {}".format(name) in src:
                return True, ""
        return False, "no `def {0}` / `class {0}` in {1!r}".format(name, path)
    return True, ""


# --- AST marker detection ----------------------------------------------------

def _decorator_marker_names(decorator):
    """Yield every attribute/name id in a decorator expression
    (`@pytest.mark.xfail(...)` -> 'pytest', 'mark', 'xfail'). Walks the whole
    node so multi-line / parametrized decorators are covered."""
    for node in ast.walk(decorator):
        if isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, ast.Name):
            yield node.id


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


def disqualifying_marker(ref):
    """Return the disqualifying marker name (`xfail`/`skip`) decorating the cited
    `path.py::name`, or None. Checks the named function/class node and, for a
    method, its enclosing class. File-only refs (no `::name`) can't be attributed
    to a node and return None (existence still covers them)."""
    path, _, name = ref.partition("::")
    if not name:
        return None
    if "/" in path:
        cands = [os.path.join(REPO_ROOT, path)]
        cands = [c for c in cands if os.path.isfile(c)]
    else:
        cands = py_index().get(os.path.basename(path), [])
    for c in cands:
        with open(c, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue
        for class_node, fn in _named_nodes(tree, name):
            decos = list(fn.decorator_list)
            if class_node is not None:
                decos += list(class_node.decorator_list)
            for d in decos:
                hit = set(_decorator_marker_names(d)) & set(DISQUALIFYING_MARKERS)
                if hit:
                    return sorted(hit)[0]
    return None


def is_full_conformant(status_cell):
    s = status_cell.lower()
    return "conformant" in s and "partial" not in s


# --- Per-ref classification + whole-attestation evaluation -------------------

def classify_ref(ref):
    """Static status of a cited test ref: ('live'|'xfail'|'skip'|'dangling',
    detail). 'live' means it resolves and carries no disqualifying static marker
    — a real, non-deferred assertion. It does NOT claim the test *passed*;
    pass/fail is enforced by the suite itself (`just test`). The report says
    'live' precisely so it never over-claims a green it didn't observe."""
    ok, detail = resolve_test_ref(ref)
    if not ok:
        return "dangling", detail
    marker = disqualifying_marker(ref)
    if marker:
        return marker, ""
    return "live", ""


def evaluate_attestation(md_text):
    """Structured evaluation of every attestation row. Returns a list of dicts:
      {id, status_text, conformant, review_kind, refs:[{ref,status,detail}],
       findings:[str]}
    `findings` is non-empty only for conformant rows whose evidence is bad —
    the same set the pytest gate asserts on."""
    out = []
    for row_id, verification, status in parse_attestation_rows(md_text):
        haystack = (verification + " " + status).lower()
        refs = TEST_REF.findall(verification + " " + status)
        ref_statuses = []
        for ref in refs:
            st, detail = classify_ref(ref)
            ref_statuses.append({"ref": ref, "status": st, "detail": detail})
        review_kind = any(k in haystack for k in REVIEW_KINDS)
        conformant = is_full_conformant(status)
        findings = []
        if conformant:
            if ref_statuses:
                for rs in ref_statuses:
                    if rs["status"] == "dangling":
                        findings.append(
                            "{}: dangling evidence — {}".format(row_id, rs["detail"])
                        )
                    elif rs["status"] in DISQUALIFYING_MARKERS:
                        findings.append(
                            "{0}: cites `{1}` as conformant evidence, but that test "
                            "is `@pytest.mark.{2}` — a known-false/unrun invariant is "
                            "not evidence. Drop the citation (other cited tests carry "
                            "the claim) or fix the test and remove the marker.".format(
                                row_id, rs["ref"], rs["status"]
                            )
                        )
            elif review_kind:
                pass  # declared non-test verification kind
            else:
                findings.append(
                    "{}: claims `conformant` with no executable test and no declared "
                    "verification kind (doc-only is not evidence) — verification={!r}"
                    .format(row_id, verification)
                )
        out.append({
            "id": row_id,
            "status_text": status,
            "conformant": conformant,
            "review_kind": review_kind,
            "refs": ref_statuses,
            "findings": findings,
        })
    return out


# --- Strict-xfail deferral collection ---------------------------------------

def _names_xfail(func):
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute) and node.attr == "xfail":
            return True
        if isinstance(node, ast.Name) and node.id == "xfail":
            return True
    return False


def is_strict_xfail(decorator):
    """True iff `decorator` is an xfail call with a truthy `strict=` keyword."""
    if not isinstance(decorator, ast.Call):
        return False
    if not _names_xfail(decorator.func):
        return False
    for kw in decorator.keywords:
        if kw.arg == "strict":
            v = kw.value
            if isinstance(v, ast.Constant):
                return bool(v.value)
            return True  # `strict=NameOrExpr` — treat as strict (conservative)
    return False


def _decorator_reason_text(decorator):
    """Concatenate every string literal in the decorator (the reason= text,
    single or implicitly-concatenated multi-line)."""
    parts = [
        node.value for node in ast.walk(decorator)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    return " ".join(parts)


def _strict_xfail_decorators(tree):
    """Yield (node_name, decorator) for every def/class carrying a strict xfail."""
    defs = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def visit(body):
        for node in body:
            if isinstance(node, defs):
                for d in node.decorator_list:
                    if is_strict_xfail(d):
                        yield node.name, d
            if isinstance(node, ast.ClassDef):
                yield from visit(node.body)

    yield from visit(tree.body)


def _iter_test_files():
    for root, _dirs, files in os.walk(TESTS_DIR):
        for fn in files:
            if fn.startswith("test_") and fn.endswith(".py"):
                yield os.path.join(root, fn)


def extract_tracking_issue(reason):
    """Return the int issue number from a `tracking: #NNN` anchor, or None."""
    m = TRACKING_ANCHOR.search(reason or "")
    return int(m.group(1)) if m else None


def collect_strict_xfails():
    """Return [{file, name, reason, tracking_issue}] for every strict-xfail in
    tests/."""
    found = []
    for path in _iter_test_files():
        with open(path, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue
        rel = os.path.relpath(path, REPO_ROOT)
        for name, deco in _strict_xfail_decorators(tree):
            reason = _decorator_reason_text(deco)
            found.append({
                "file": rel,
                "name": name,
                "reason": reason,
                "tracking_issue": extract_tracking_issue(reason),
            })
    return found
