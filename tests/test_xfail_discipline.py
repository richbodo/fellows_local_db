"""Strict-xfail discipline: every deferral is anchored and the load is capped.

Two invariants, both offline/static (no network), companion to
`tests/test_attestation_has_evidence.py`. See
`plans/conformance_report_and_gate.md`.

1. **Anchored.** Every `@pytest.mark.xfail(strict=True)` reason must carry a
   machine-readable `tracking: #NNN` issue anchor. An *issue* (not a PR): issues
   close when the *work* is done; a PR closes when *something* merges. The prose
   "names the PR that will satisfy it" convention was unenforceable — nothing
   parsed it, so a deferral could outlive every PR that named it. This makes the
   anchor data, and (in a later PR) lets the report flag an anchor whose issue
   is closed while the test still xfails — the abandoned-deferral case that
   `strict=True` is structurally blind to (it trips on accidental *success*,
   never on abandoned *deferral*).

2. **Capped at 3.** At most three strict-xfail deferrals may exist in `tests/`
   at once. This project builds most features in ~3 PRs; a deferral load past
   one feature's worth is the smell. The cap keeps the conformance attestation
   glanceable — a short, bounded list of honest frontiers, not a ledger of debt
   that the eye glazes over. The 4th deferral fails the build: pay down before
   you defer more.
"""
import ast
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(REPO_ROOT, "tests")

# `tracking: #123` (the `#` is required so it's unambiguously an issue ref).
_TRACKING_ANCHOR = re.compile(r"tracking:\s*#\d+", re.IGNORECASE)

DEFERRAL_CAP = 3


def _strict_xfail_decorators(tree):
    """Yield (node_name, decorator) for every def/class carrying a
    `@pytest.mark.xfail(strict=True)` (or `xfail(..., strict=True)`)."""
    defs = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def visit(body):
        for node in body:
            if isinstance(node, defs):
                for d in node.decorator_list:
                    if _is_strict_xfail(d):
                        yield node.name, d
            if isinstance(node, ast.ClassDef):
                yield from visit(node.body)

    yield from visit(tree.body)


def _is_strict_xfail(decorator):
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
            # `strict=NameOrExpr` — treat as strict (conservative).
            return True
    return False


def _names_xfail(func):
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute) and node.attr == "xfail":
            return True
        if isinstance(node, ast.Name) and node.id == "xfail":
            return True
    return False


def _decorator_reason_text(decorator):
    """Concatenate every string literal in the decorator (the reason= text,
    whether a single string or an implicitly-concatenated multi-line one)."""
    parts = []
    for node in ast.walk(decorator):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            parts.append(node.value)
    return " ".join(parts)


def _iter_test_files():
    for root, _dirs, files in os.walk(TESTS_DIR):
        for fn in files:
            if fn.startswith("test_") and fn.endswith(".py"):
                yield os.path.join(root, fn)


def _collect_strict_xfails():
    """Return [(relpath, name, reason_text)] for every strict-xfail in tests/."""
    found = []
    for path in _iter_test_files():
        with open(path, encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue
        rel = os.path.relpath(path, REPO_ROOT)
        for name, deco in _strict_xfail_decorators(tree):
            found.append((rel, name, _decorator_reason_text(deco)))
    return found


def test_every_strict_xfail_has_tracking_anchor():
    findings = []
    for rel, name, reason in _collect_strict_xfails():
        if not _TRACKING_ANCHOR.search(reason):
            findings.append(
                f"{rel}::{name} is `xfail(strict=True)` with no `tracking: #NNN` "
                f"issue anchor in its reason. A deferral must point at an open "
                f"issue that stays open until the test XPASSes."
            )
    assert not findings, (
        "Strict-xfail deferrals missing a machine-readable issue anchor "
        "(see plans/conformance_report_and_gate.md):\n  - " + "\n  - ".join(findings)
    )


def test_strict_xfail_load_under_cap():
    deferrals = _collect_strict_xfails()
    assert len(deferrals) <= DEFERRAL_CAP, (
        f"{len(deferrals)} strict-xfail deferrals exceeds the cap of "
        f"{DEFERRAL_CAP}. Pay down a deferral before adding another — the "
        f"conformance attestation must stay glanceable, not become a debt "
        f"ledger (see plans/conformance_report_and_gate.md):\n  - "
        + "\n  - ".join(f"{rel}::{name}" for rel, name, _ in deferrals)
    )
