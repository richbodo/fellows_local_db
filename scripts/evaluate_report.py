#!/usr/bin/env python3
"""Deterministic emitter for docs/conformance/evaluate-report.json — the
toolkit-schema artifact the Personal Network Toolkit (PNT) consumes as the
keystone's `[verify].entrypoint` output.

This is the DETERMINISTIC layer, NOT an LLM audit. It derives the whole report
from `docs/Architecture.md`'s attestation table (via `scripts/conformance_lib.py`)
plus the current git HEAD. Same commit + same attestation → byte-identical output
(no wall-clock timestamp is stamped), so the artifact is reproducible and
CI-able. Stdlib only.

Render contract (the success criterion):
    python3 ~/src/personal_network_toolkit/tools/report-fixtures-lint.py \
        docs/conformance/evaluate-report.json
must report "satisfies the render contract". `render_contract_violations()`
below mirrors that lint so the fellows suite can validate hermetically (without
the toolkit checked out); `just evaluate-report` runs the real toolkit lint when
it is present.

## Why AC-keyed (and where EX/CST go)

The toolkit schema (`tools/evaluate-report.schema.json`) is **AC-keyed**:
`findings[].ac_id` must match `^AC-[A-Z0-9-]+$`, and the schema's own `$comment`
states that EX-*/CST-* are "the only place EX-*/CST-* live — as references
inside the AC findings they bear on." So this emitter:

  * emits **one finding per AC-* attestation row** — the Universal-ACs and
    Flavor-derived-ACs tables, plus the not-applicable table;
  * **folds each EX-*/CST-* row into the `evidence` of the AC finding(s) it
    bears on**, via `EXTENSION_AC_HOME`. If `docs/Architecture.md` grows an
    EX/CST row this map doesn't cover, `build_evaluate_report()` RAISES rather
    than silently dropping a declared exception/constraint — the same
    fails-loudly discipline the rest of the conformance gate enforces;
  * leaves the fellows-local `UM-*` user-mediation rows and the
    mediated-boundary registry out of scope here (they sit *beneath* the AC
    families and are surfaced in the fellows-format `docs/conformance/report.json`
    instead — they are not part of the toolkit's AC-keyed evaluate model).

Status mapping: a row's `conformant` → `conformant`; `not-applicable` →
`not-applicable` (with the row's Reason as `rationale`); `partial-conformance`
→ `conformant` + `needs_human_review: true` (the toolkit schema has no
`partial` status, so the residual is recorded honestly as a human-review flag,
with the original Status text preserved in the evidence prose).

Usage:
  python scripts/evaluate_report.py            # build + validate + write the file
  python scripts/evaluate_report.py --check     # build + validate only (no write); exit 1 on violation
  python scripts/evaluate_report.py --no-write   # alias for --check
"""
import json
import os
import re
import sys

# Importable whether run as a script (sibling of conformance_lib) or via the
# package path (`from scripts.evaluate_report import ...`).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.conformance_lib import (  # noqa: E402
    ARCH_MD,
    FLAVOR_DERIVED_ACS,
    REPO_ROOT,
    evaluate_attestation,
    input_commit,
    is_separator,
    py_index,
    split_row,
)

OUT_PATH = os.path.join(_REPO_ROOT, "docs", "conformance", "evaluate-report.json")

REPORT_SCHEMA_VERSION = "0.1"
CANDIDATE_NAME = "fellows_local_db"
CANDIDATE_REPO_URL = "https://github.com/richbodo/fellows_local_db"
GENERATED_BY = "scripts/evaluate_report.py (deterministic; derived from docs/Architecture.md attestation)"

# EX-*/CST-* row -> the AC finding(s) whose evidence it belongs in. The schema
# keeps EX/CST as references inside AC findings; this is that linkage, drawn from
# the attestation's own semantics (each constraint/exception's Realization names
# the capability it bears on). Coverage of every EX/CST row in
# docs/Architecture.md is ENFORCED in build_evaluate_report(): an unmapped row
# raises, so a newly-declared constraint cannot vanish from the evaluate report.
EXTENSION_AC_HOME = {
    # The cloud-LLM exception relaxes AC-MCP-A and is realized through AC-PRM-A.
    "EX-CLOUD-LLM": ["AC-MCP-A", "AC-PRM-A"],
    # Private-data durability ceilings bear on AC-9 (auto-backup of private data).
    "CST-PWA-PRIVATE-SNAPSHOT": ["AC-9"],
    "CST-PWA-STORAGE-EVICTABLE": ["AC-9"],
    "CST-PWA-NO-SYNC": ["AC-9"],
    "CST-PWA-NO-BACKGROUND": ["AC-9"],
    # External-tool readability of the private store goes through the MCP path.
    "CST-PWA-SANDBOX-SEALED": ["AC-MCP-A"],
    # Multi-tab contention is detected via AC-11 (concurrent-access + Web Locks).
    "CST-PWA-SINGLE-OWNER": ["AC-11"],
    # The server floor is bounded to distribution — the AC-2 no-SaaS surface.
    "CST-PWA-SERVER-FLOOR": ["AC-2"],
}


# --- Markdown helpers --------------------------------------------------------

def _iter_tables(md_text):
    """Yield (header_cells, [row_cells, ...]) for every GFM table in md_text."""
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < len(lines) and is_separator(lines[i + 1]):
            header = split_row(line)
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|") and not is_separator(lines[j]):
                rows.append(split_row(lines[j]))
                j += 1
            yield header, rows
            i = j
            continue
        i += 1


def _id_token(row_id):
    """Leading id token of a row label ('AC-1 (two-store …)' -> 'AC-1')."""
    return row_id.split()[0].strip() if row_id else ""


def parse_axis_picks(md_text):
    """{axis-anchor: pick} from the 'fellows's six axis picks' table.
    The axis key is the canonical PNT axis anchor (#distribution, …) pulled from
    the cell's link target; the pick is the backticked identifier."""
    for header, rows in _iter_tables(md_text):
        lower = [h.lower() for h in header]
        if lower[:2] == ["axis", "pick"]:
            picks = {}
            for cells in rows:
                if len(cells) < 2:
                    continue
                m = re.search(r"#([a-z0-9-]+)\)", cells[0])
                axis = m.group(1) if m else re.sub(r"[^a-z0-9]+", "-", cells[0].lower()).strip("-")
                pick = cells[1].strip().strip("`").strip()
                if axis and pick:
                    picks[axis] = pick
            return picks
    return {}


def parse_not_applicable(md_text):
    """[(ac_id, reason)] from the 'ACs that are not applicable' table."""
    for header, rows in _iter_tables(md_text):
        if [h.lower() for h in header] == ["ac", "reason"]:
            return [(cells[0].strip(), cells[1].strip())
                    for cells in rows if len(cells) >= 2 and cells[0].strip()]
    return []


def parse_pna_spec_version(md_text):
    """'0.1' from the '**Toolkit-Version:** [0.1 (draft)]' line, or None."""
    m = re.search(r"Toolkit-Version:\*\*\s*\[([^\]]+)\]", md_text)
    if not m:
        return None
    return m.group(1).split()[0].strip() or None


# --- Citation / evidence construction ---------------------------------------

def _ref_to_citation(ref):
    """A `path.py[::name]` attestation ref -> a schema code_location with a
    repo-relative path (bare-filename shorthand resolved via the code index)."""
    path_part, _, name = ref.partition("::")
    if "/" in path_part:
        rel = path_part
    else:
        cands = py_index().get(os.path.basename(path_part), [])
        rel = os.path.relpath(cands[0], REPO_ROOT) if cands else path_part
    cit = {"path": rel.replace("\\", "/")}
    if name:
        cit["note"] = "cited test: {}".format(name)
    return cit


def _status_is_partial(status_text):
    return "partial" in status_text.lower()


def _map_status(status_text):
    s = status_text.lower()
    if "not-applicable" in s or "not applicable" in s:
        return "not-applicable"
    if "partial" in s:
        return "conformant"          # + needs_human_review, set by caller
    if "conformant" in s:
        return "conformant"
    return "unable-to-determine"


def _ac_finding(row, ext_evidence):
    """Build one schema `finding` from an AC attestation row + any EX/CST
    evidence folded in (ext_evidence: list of schema evidence dicts)."""
    ac_id = _id_token(row["id"])
    status_text = row["status_text"]
    status = _map_status(status_text)
    finding = {
        "ac_id": ac_id,
        "ac_source": "flavor-derived" if ac_id in FLAVOR_DERIVED_ACS else "universal",
        "status": status,
    }

    citations = [_ref_to_citation(rs["ref"]) for rs in row["refs"]]
    if citations:
        finding["citations"] = citations

    evidence = []
    if row["refs"]:
        joined = "; ".join("{} -> {}".format(rs["ref"], rs["status"]) for rs in row["refs"])
        evidence.append({
            "source": "deterministic",
            "tool": "conformance-attestation-gate",
            "detail": (
                "Attestation gate (scripts/conformance_lib.py) resolved {} cited test "
                "ref(s), all non-deferred: {}. Static existence + marker-state only — "
                "pass/fail is enforced by the suite (`just test`)."
            ).format(len(row["refs"]), joined),
        })
    if row["review_kind"]:
        evidence.append({
            "source": "human",
            "detail": (
                "docs/Architecture.md also declares a non-test verification kind for this "
                "row (human-review / code inspection / by construction / by bounding)."
            ),
        })
    if _status_is_partial(status_text):
        finding["needs_human_review"] = True
        evidence.append({
            "source": "human",
            "detail": (
                "docs/Architecture.md self-attests partial-conformance: \"{}\". The toolkit "
                "schema has no 'partial' status, so this is recorded as conformant with "
                "needs_human_review to keep the residual visible."
            ).format(status_text),
        })
    evidence.extend(ext_evidence)
    if evidence:
        finding["evidence"] = evidence
    return finding


# --- Report assembly ---------------------------------------------------------

def build_evaluate_report(commit="__AUTO__"):
    """Build the toolkit-schema evaluate-report dict from docs/Architecture.md.

    commit: pass an explicit sha, None to omit, or the sentinel '__AUTO__'
    (default) to derive the self-stable input-commit — the commit that last
    touched the attestation source docs/Architecture.md, NOT raw HEAD (see
    scripts/conformance_lib.input_commit for why). Tests pass a fixed value for
    determinism.
    """
    with open(ARCH_MD, encoding="utf-8") as f:
        arch_md = f.read()

    rows = evaluate_attestation(arch_md)

    # Partition parsed attestation rows by id prefix.
    ac_rows = [r for r in rows if _id_token(r["id"]).startswith("AC-")]
    ext_rows = {_id_token(r["id"]): r for r in rows
                if _id_token(r["id"]).startswith(("EX-", "CST-"))}

    ac_ids = {_id_token(r["id"]) for r in ac_rows}
    ac_ids |= {ac for ac, _ in parse_not_applicable(arch_md)}

    # Fail loudly if a declared EX/CST row has no AC home (would otherwise be
    # silently dropped from the report).
    for tok in sorted(ext_rows):
        if tok not in EXTENSION_AC_HOME:
            raise ValueError(
                "evaluate_report: attestation row {!r} has no EXTENSION_AC_HOME mapping. "
                "Add it (which AC finding does this exception/constraint bear on?) so the "
                "declared {} is not silently dropped from the evaluate report.".format(
                    tok, "exception" if tok.startswith("EX-") else "constraint"))

    # Fold each EX/CST row into the evidence of its home AC(s).
    ext_evidence_by_ac = {}
    for tok, row in ext_rows.items():
        kind = "exception" if tok.startswith("EX-") else "constraint"
        section = "Exception" if kind == "exception" else "Constraint"
        detail = (
            "Bears on {kind} {tok} ({status}); declared and handled in docs/Architecture.md "
            "§ {section} attestation, folded here per the toolkit schema rule that EX-*/CST-* "
            "live as references inside the AC findings they bear on."
        ).format(kind=kind, tok=tok, status=row["status_text"], section=section)
        for ac in EXTENSION_AC_HOME[tok]:
            if ac not in ac_ids:
                raise ValueError(
                    "evaluate_report: EXTENSION_AC_HOME maps {!r} to {!r}, which is not an "
                    "emitted AC finding. Fix the mapping.".format(tok, ac))
            ext_evidence_by_ac.setdefault(ac, []).append({"source": "human", "detail": detail})

    findings = [_ac_finding(r, ext_evidence_by_ac.get(_id_token(r["id"]), [])) for r in ac_rows]

    for ac_id, reason in parse_not_applicable(arch_md):
        findings.append({
            "ac_id": ac_id,
            "ac_source": "flavor-derived" if ac_id in FLAVOR_DERIVED_ACS else "universal",
            "status": "not-applicable",
            "rationale": reason,
        })

    statuses = [f["status"] for f in findings]
    if any(st == "non-conformant" for st in statuses):
        posture = "non-conformant"
    elif any(st == "unable-to-determine" for st in statuses):
        posture = "indeterminate"
    else:
        posture = "conformant"

    leading = [f["ac_id"] for f in findings if f.get("needs_human_review")]
    n_conf = sum(1 for st in statuses if st == "conformant")
    n_na = sum(1 for st in statuses if st == "not-applicable")
    spec_version = parse_pna_spec_version(arch_md) or "0.1"

    headline = (
        "fellows_local_db is deterministically attested conformant to PNA Spec {ver} for its "
        "declared flavor: {conf} conformant, {na} not-applicable, 0 non-conformant across {tot} "
        "evaluated ACs."
    ).format(ver=spec_version, conf=n_conf, na=n_na, tot=len(findings))
    if leading:
        headline += (
            " {k} AC(s) carry self-attested partial-conformance flagged for human review ({ids}); "
            "the EX-CLOUD-LLM exception and the CST-PWA-* platform constraints are handled honestly "
            "and folded into the AC findings they bear on."
        ).format(k=len(leading), ids=", ".join(leading))
    headline += " Derived from docs/Architecture.md by scripts/evaluate_report.py — not an LLM audit."

    summary = {"posture": posture, "headline": headline}
    if leading:
        summary["leading_concerns"] = leading

    candidate = {
        "name": CANDIDATE_NAME,
        "repo_url": CANDIDATE_REPO_URL,
    }
    # Self-stable commit (NOT raw HEAD): the commit that last touched the
    # attestation source. Keeps the archived keystone artifact byte-identical
    # on regen so committing it never dirties the tree. See input_commit().
    sha = input_commit() if commit == "__AUTO__" else commit
    if sha:
        candidate["commit"] = sha
    candidate["pna_spec_version"] = spec_version
    candidate["picks_source"] = "declared"
    axis_picks = parse_axis_picks(arch_md)
    if axis_picks:
        candidate["axis_picks"] = axis_picks

    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "candidate": candidate,
        "summary": summary,
        "findings": findings,
    }


# --- Render-contract validation (mirrors PNT tools/report-fixtures-lint.py) --

_AC_ID_RE = re.compile(r"^AC-[A-Z0-9-]+$")
_POSTURES = {"conformant", "non-conformant", "mixed", "indeterminate"}
_STATUSES = {"conformant", "non-conformant", "not-applicable", "unable-to-determine"}
_TOP_REQUIRED = ("report_schema_version", "candidate", "summary", "findings")


def render_contract_violations(obj):
    """Return render-contract violations for a parsed report (empty == ok).

    A faithful stdlib mirror of PNT's tools/report-fixtures-lint.py so the
    fellows suite can validate hermetically. The toolkit lint remains the
    authoritative check (run by `just evaluate-report`); this exists so CI
    without the toolkit checked out still catches a malformed report.
    """
    errs = []
    if not isinstance(obj, dict):
        return ["top level is not a JSON object"]
    for k in _TOP_REQUIRED:
        if k not in obj:
            errs.append("missing required top-level key {!r}".format(k))
    if obj.get("report_schema_version") not in (None, "0.1"):
        errs.append('report_schema_version must be "0.1", got {!r}'.format(
            obj.get("report_schema_version")))
    cand = obj.get("candidate")
    if isinstance(cand, dict):
        for k in ("pna_spec_version", "picks_source"):
            if k not in cand:
                errs.append("candidate is missing required key {!r}".format(k))
    elif "candidate" in obj:
        errs.append("candidate is not an object")
    summ = obj.get("summary")
    if isinstance(summ, dict):
        if summ.get("posture") not in _POSTURES:
            errs.append("summary.posture {!r} not one of {}".format(
                summ.get("posture"), sorted(_POSTURES)))
        if not isinstance(summ.get("headline"), str) or not summ.get("headline"):
            errs.append("summary.headline must be a non-empty string")
    elif "summary" in obj:
        errs.append("summary is not an object")
    findings = obj.get("findings")
    if not isinstance(findings, list) or not findings:
        errs.append("findings must be a non-empty array")
        return errs
    for i, f in enumerate(findings):
        where = "findings[{}]".format(i)
        if not isinstance(f, dict):
            errs.append("{} is not an object".format(where))
            continue
        ac = f.get("ac_id")
        if isinstance(ac, str) and _AC_ID_RE.match(ac):
            where = "findings[{}]({})".format(i, ac)
        else:
            errs.append("{}.ac_id {!r} does not match ^AC-[A-Z0-9-]+$".format(where, ac))
        st = f.get("status")
        if st not in _STATUSES:
            errs.append("{}.status {!r} not one of {}".format(where, st, sorted(_STATUSES)))
            continue
        has_cites = isinstance(f.get("citations"), list) and len(f["citations"]) > 0
        if st in ("conformant", "non-conformant") and not has_cites:
            errs.append("{}: status {} requires a non-empty 'citations' array".format(where, st))
        if st == "non-conformant" and not f.get("requirement"):
            errs.append("{}: status non-conformant requires 'requirement'".format(where))
        if st in ("not-applicable", "unable-to-determine") and not f.get("rationale"):
            errs.append("{}: status {} requires 'rationale'".format(where, st))
    return errs


def write_report(report=None):
    """Write the evaluate-report to OUT_PATH (pretty JSON + trailing newline)."""
    if report is None:
        report = build_evaluate_report()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return OUT_PATH


def main(argv):
    check_only = "--check" in argv or "--no-write" in argv
    report = build_evaluate_report()
    violations = render_contract_violations(report)
    if violations:
        print("evaluate-report FAILS the render contract:", file=sys.stderr)
        for v in violations:
            print("  - {}".format(v), file=sys.stderr)
        return 1
    summ = report["summary"]
    n = len(report["findings"])
    if check_only:
        print("evaluate-report: render contract OK — posture={}, {} AC findings (not written)."
              .format(summ["posture"], n))
        return 0
    write_report(report)
    print("Wrote {} — posture={}, {} AC findings; render contract OK.".format(
        os.path.relpath(OUT_PATH, _REPO_ROOT), summ["posture"], n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
