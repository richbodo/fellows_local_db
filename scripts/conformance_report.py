#!/usr/bin/env python3
"""Generate the conformance report — the deterministic serialization of the
attestation gate (`scripts/conformance_lib.py`), plus a best-effort
abandoned-deferral check that the static gate structurally cannot do.

This is the "always know the status" readout. It is NOT the LLM evaluate flow
(architectural judgment) — that stays a human/agent step. Everything here is
deterministic and offline, except one fail-open `gh` call per tracked deferral.

What it emits (under docs/conformance/):
  - report.json  — typed artifact (status snapshot), committed + diffable.
  - report.md    — human view over the same data, committed.
  - log.jsonl    — append-only local run history (gitignored); drives the
                   PR3 staleness auto-regen (`git rev-list <last_sha>..HEAD`).

Headline is the deferral count vs the cap — the one number that's supposed to be
zero, kept where the attestation is read so creeping debt is loud, not a ledger
the eye glazes over.

Exit code: 1 if there are findings (so it can gate `deploy-preflight` in PR3),
else 0. A `gh`-unknown issue state is fail-open — never a finding.

Usage:
  python scripts/conformance_report.py            # write artifacts + log, print
  python scripts/conformance_report.py --no-gh    # skip the issue-state probe
  python scripts/conformance_report.py --no-write  # check only (don't touch fs)
  python scripts/conformance_report.py --if-stale  # regen only if HEAD is
                                                   # >= STALE_COMMITS past the
                                                   # last logged run; non-fatal
                                                   # (used by `just test`)
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

# Importable whether run as a script (sibling) or via the package path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.conformance_lib import (  # noqa: E402
    ARCH_MD,
    DEFERRAL_CAP,
    FLAVOR_DERIVED_ACS,
    collect_strict_xfails,
    evaluate_attestation,
    input_commit,
)

OUT_DIR = os.path.join(_REPO_ROOT, "docs", "conformance")
REPORT_JSON = os.path.join(OUT_DIR, "report.json")
REPORT_MD = os.path.join(OUT_DIR, "report.md")
LOG_JSONL = os.path.join(OUT_DIR, "log.jsonl")

# `just test` regenerates the committed snapshot when HEAD is this many commits
# past the last logged run (or there's no log yet). This is *snapshot freshness*
# — distinct from the deferral cap (3, in conformance_lib). The committed report
# is a convenience snapshot that rides along with work; the authoritative ship
# check is deploy-preflight, which gates on every deploy regardless of staleness.
STALE_COMMITS = 10

# --- PNT deep-linking --------------------------------------------------------
# Each attested row links to its definition in the Personal Network Toolkit, so
# a reader (possibly meeting "architectural constraint" for the first time) can
# click straight to the authority instead of scrolling a 50-section spec. The
# per-ID anchors (#ac-1, #cst-pwa-sandbox-sealed, #ex-cloud-llm) were added to
# PNT in PR #27.
PNT_REPO = "https://github.com/richbodo/personal_network_toolkit"
PNT_SPEC = PNT_REPO + "/blob/main/spec/"
PNT_AUDIT_GUIDE = (PNT_REPO + "/blob/main/docs/users-guide.md"
                   "#goal-2--audit-a-candidate-pna-before-installing-it")

# Flavor-derived ACs live in axes.md; every other AC lives in PNA_Spec.md.
# (Mirrors PNT's split — see the "gaps you'll see in the table" note in
# PNA_Spec.md.) Single source of truth is conformance_lib.FLAVOR_DERIVED_ACS,
# shared with scripts/evaluate_report.py so the two never drift.
_AXES_ACS = FLAVOR_DERIVED_ACS

_TOOLKIT_VERSION_RE = re.compile(r"Toolkit-Version:\*\*\s*\[([^\]]+)\]")


def _id_token(row_id):
    """The bare AC/CST/EX id leading a row label ('AC-1 (two-store …)' -> 'AC-1')."""
    return row_id.split()[0].strip() if row_id else ""


def pnt_anchor_url(row_id):
    """Deep link to this row's AC/CST/EX definition in PNT, or None if unknown."""
    tok = _id_token(row_id)
    anchor = "#" + tok.lower()
    if tok.startswith("EX-"):
        return PNT_SPEC + "exceptions.md" + anchor
    if tok.startswith("CST-"):
        return PNT_SPEC + "constraints.md" + anchor
    if tok.startswith("AC-"):
        return PNT_SPEC + ("axes.md" if tok in _AXES_ACS else "PNA_Spec.md") + anchor
    return None


def _toolkit_version(md_text):
    """The Toolkit-Version this design attests against ('0.1 (draft)'), or None."""
    m = _TOOLKIT_VERSION_RE.search(md_text)
    return m.group(1).strip() if m else None


def _short_status(status_text):
    """Normalize a verbose Status cell to a scannable token; the full prose stays
    in docs/Architecture.md (the source of truth this report links to)."""
    s = status_text.lower()
    if "not-applicable" in s or "not applicable" in s:
        return "not-applicable"
    if "partial" in s:
        return "partial-conformance"
    if "conformant" in s:
        return "conformant"
    return status_text.split("(")[0].strip() or status_text


def _head_short_sha():
    """Short HEAD sha — the staleness-log marker only ("where did we last
    regenerate?"), consumed by `_last_logged_sha` / `_commits_since`. Distinct
    from the report's *displayed* commit (`_report_short_sha`), which names the
    attested state, not the run point."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=_REPO_ROOT,
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _report_short_sha():
    """Short form of the self-stable input-commit (the commit that last touched
    docs/Architecture.md) for `meta.git_sha` — so report.json names the SAME
    evaluated commit as the keystone evaluate-report.json's `candidate.commit`,
    and committing the snapshot doesn't churn the sha on an unrelated commit.
    Sliced (not `git --short`) so the length is deterministic as the repo grows.
    See scripts/conformance_lib.input_commit."""
    full = input_commit()
    return full[:7] if full else None


def _commits_since(sha):
    """Number of commits from `sha` to HEAD, or None if unknown."""
    if not sha:
        return None
    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", "{}..HEAD".format(sha)],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
        return int(out.stdout.strip()) if out.returncode == 0 else None
    except Exception:
        return None


def _last_logged_sha():
    """git_sha of the most recent log entry, or None (no/empty/unreadable log)."""
    try:
        with open(LOG_JSONL, encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        return json.loads(lines[-1]).get("git_sha") if lines else None
    except Exception:
        return None


def _gh_issue_state(number):
    """Return 'OPEN' / 'CLOSED' / None (unknown). Fail-open: any error → None,
    so an offline run or a missing `gh` never manufactures a finding."""
    try:
        out = subprocess.run(
            ["gh", "issue", "view", str(number), "--json", "state"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0:
            return None
        return (json.loads(out.stdout).get("state") or "").upper() or None
    except Exception:
        return None


def build_report(probe_gh=True):
    with open(ARCH_MD, encoding="utf-8") as f:
        arch_md = f.read()
    rows = evaluate_attestation(arch_md)
    toolkit_version = _toolkit_version(arch_md)
    deferrals = collect_strict_xfails()

    findings = []  # structured: {kind, detail}

    # Attestation evidence findings (same set the pytest gate asserts on).
    for row in rows:
        for msg in row["findings"]:
            findings.append({"kind": "attestation-evidence", "detail": msg})

    # Deferral discipline (mirrors tests/test_xfail_discipline.py).
    if len(deferrals) > DEFERRAL_CAP:
        findings.append({
            "kind": "deferral-over-cap",
            "detail": "{} strict-xfail deferrals exceeds cap of {}".format(
                len(deferrals), DEFERRAL_CAP
            ),
        })
    for d in deferrals:
        if d["tracking_issue"] is None:
            findings.append({
                "kind": "deferral-unanchored",
                "detail": "{file}::{name} has no `tracking: #NNN` anchor".format(**d),
            })

    # Abandoned-deferral check — the asymmetry fix. A strict-xfail stays green
    # forever if its fix is abandoned; `strict=True` only trips on accidental
    # success. So we ask the tracker: is the issue CLOSED while the test is
    # still xfailing (it is, by virtue of being in this list)? If so the
    # deferral was abandoned, not completed. Fail-open on unknown state.
    for d in deferrals:
        issue = d["tracking_issue"]
        d["issue_state"] = _gh_issue_state(issue) if (probe_gh and issue) else None
        if d["issue_state"] == "CLOSED":
            findings.append({
                "kind": "deferral-abandoned",
                "detail": (
                    "{file}::{name} still xfails but its tracking issue #{issue} "
                    "is CLOSED — the deferral was abandoned, not completed. Reopen "
                    "#{issue} and finish it, or drop the deferral.".format(
                        file=d["file"], name=d["name"], issue=issue
                    )
                ),
            })

    conformant_rows = [r for r in rows if r["conformant"]]
    ok = not findings
    report = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_sha": _report_short_sha(),
            "source": "docs/Architecture.md",
            "generator": "scripts/conformance_report.py",
            "toolkit_version": toolkit_version,
            "note": (
                "Deterministic serialization of scripts/conformance_lib.py. "
                "'live' = a real, non-deferred assertion exists; pass/fail is "
                "enforced by the suite itself (`just test`). Not the LLM evaluate "
                "flow. See plans/conformance_report_and_gate.md."
            ),
        },
        "headline": {
            # The deterministic layer can only ever reach "conditionally
            # conformant" — full conformance also needs the LLM + human evaluate
            # flow. A finding is a definitive evidence gap at this layer.
            "verdict": "conditionally-conformant" if ok else "not-conformant",
            "deferral_count": len(deferrals),
            "deferral_cap": DEFERRAL_CAP,
            "conformant_rows": len(conformant_rows),
            "total_rows": len(rows),
            "findings_count": len(findings),
            "ok": ok,
        },
        "deferrals": deferrals,
        "findings": findings,
        "rows": rows,
    }
    return report


def render_md(report):
    h = report["headline"]
    m = report["meta"]
    tk = m.get("toolkit_version") or "unknown version"
    L = []

    # Title + what-this-is (written for a reader who may be meeting "conformance"
    # for the first time — say what it is, link the authority, name the stakes).
    L.append("# Conformance Report — EHF Fellows Local Directory")
    L.append("")
    L.append("> **What this is.** A check of whether this repository honestly "
             "conforms to the **Personal Network Application (PNA)** spec — a "
             "local-first, private-by-default app that mirrors contact data into a "
             "user-owned workspace with no remote authority. The spec and this "
             "conformance method come from the **[Personal Network Toolkit "
             "(PNT)]({repo})**. This report is generated by "
             "`scripts/conformance_report.py` (serializing "
             "`scripts/conformance_lib.py`); it is the **deterministic** layer — "
             "it verifies that every `conformant` claim in this app's Security "
             "Target (`docs/Architecture.md`) is backed by live, executable "
             "evidence. It does not run the spec's LLM/human evaluate flow."
             .format(repo=PNT_REPO))
    L.append(">")
    L.append("> _Why it matters: PNA conformance is the spec's proxy for **safe "
             "to install** — a local-first app with no remote authority over your "
             "data._")
    L.append("")

    # Verdict — the deterministic layer tops out at "conditionally conformant".
    if h["ok"]:
        L.append("## 🟡 Conditionally conformant to the PNA Spec (PNT {tk})".format(tk=tk))
        L.append("")
        L.append("Every conformance claim this app makes is backed by live, "
                 "executable evidence, and all deferrals are disciplined. This is "
                 "the **deterministic** layer of conformance — a full "
                 "determination also needs the spec's evaluate flow (below).")
    else:
        L.append("## 🔴 Not conformant (as attested) to the PNA Spec (PNT {tk})".format(tk=tk))
        L.append("")
        L.append("{n} finding(s) below: a `conformant` claim lacks live evidence, "
                 "or a deferral is undisciplined. These are concrete gaps to fix "
                 "before conformance can even be conditionally asserted."
                 .format(n=h["findings_count"]))
    L.append("")

    # Verification ladder — makes "conditionally" concrete and shows what's left.
    L.append("**Conformance is checked in layers, not awarded as a badge:**")
    L.append("")
    cond_here = " ← **this report**" if h["ok"] else ""
    not_here = " ← **this report**" if not h["ok"] else ""
    L.append("- 🟢 **Conformant** — deterministic ✓ · LLM evaluate ✓ · human "
             "review ✓ — _the goal; not grantable by this report_")
    L.append("- 🟡 **Conditionally conformant** — deterministic evidence "
             "verified; evaluate flow pending{h}".format(h=cond_here))
    L.append("- 🔴 **Not conformant** — a `conformant` claim lacks live "
             "evidence{h}".format(h=not_here))
    L.append("")
    L.append("→ To complete the determination (🟡 → 🟢), run the spec's audit "
             "flow: **[PNT User's Guide → Audit a candidate PNA]({url})**."
             .format(url=PNT_AUDIT_GUIDE))
    L.append("")
    L.append("_Generated {} for `{}`. Source of truth: "
             "[`docs/Architecture.md`](../Architecture.md)._"
             .format(m["generated_at"], m["git_sha"] or "unknown"))
    L.append("")

    # Plain-language legend (the reader may not know AC/CST/EX) + the metrics.
    L.append("**What the IDs mean** — "
             "[**AC**]({s}PNA_Spec.md) Architectural Commitment (a rule every "
             "safe PNA honors) · "
             "[**CST**]({s}constraints.md) Constraint (a platform limit handled "
             "honestly, not hidden) · "
             "[**EX**]({s}exceptions.md) Exception (a declared departure from PNA "
             "rules).".format(s=PNT_SPEC))
    L.append("")
    findings_mark = "✅" if h["findings_count"] == 0 else "❌"
    cap_mark = "✅" if h["deferral_count"] <= h["deferral_cap"] else "❌"
    L.append("- **Conformant rows:** {} of {}".format(
        h["conformant_rows"], h["total_rows"]))
    L.append("- **Deferrals:** {} of {} max {}".format(
        h["deferral_count"], h["deferral_cap"], cap_mark))
    L.append("- **Findings:** {} {}".format(h["findings_count"], findings_mark))
    L.append("")

    L.append("## Deferrals (strict-xfail)")
    L.append("")
    if report["deferrals"]:
        L.append("| Test | Tracking | Issue state |")
        L.append("|---|---|---|")
        for d in report["deferrals"]:
            issue = "#{}".format(d["tracking_issue"]) if d["tracking_issue"] else "—"
            state = d.get("issue_state") or "unknown"
            L.append("| `{file}::{name}` | {issue} | {state} |".format(
                file=d["file"], name=d["name"], issue=issue, state=state))
    else:
        L.append("_None — zero deferred invariants._")
    L.append("")

    L.append("## Findings")
    L.append("")
    if report["findings"]:
        for f in report["findings"]:
            L.append("- **[{kind}]** {detail}".format(**f))
    else:
        L.append("_None. Every `conformant` row cites live, non-deferred "
                 "evidence; every deferral is anchored and under cap._")
    L.append("")

    L.append("## Attestation rows")
    L.append("")
    L.append("Each row's ID links to its definition in the PNT spec. Status is "
             "summarized; the full realization + verification prose lives in "
             "[`docs/Architecture.md`](../Architecture.md).")
    L.append("")
    L.append("| Row | Status | Evidence (cited test → static state) |")
    L.append("|---|---|---|")
    for r in report["rows"]:
        if r["refs"]:
            ev = "; ".join("`{ref}` → {status}".format(**rs) for rs in r["refs"])
        elif r["review_kind"]:
            ev = "_declared review kind_"
        else:
            ev = "_—_"
        url = pnt_anchor_url(r["id"])
        label = "[{id}]({url})".format(id=r["id"], url=url) if url else r["id"]
        L.append("| {label} | {status} | {ev} |".format(
            label=label, status=_short_status(r["status_text"]), ev=ev))
    L.append("")
    return "\n".join(L) + "\n"


def write_artifacts(report):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=False)
        f.write("\n")
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(render_md(report))
    log_line = {
        "generated_at": report["meta"]["generated_at"],
        # The log marks the RUN POINT (HEAD), which the staleness short-circuit
        # measures distance from — deliberately NOT report.meta.git_sha (the
        # attested input-commit), or `_commits_since` would grow unbounded since
        # the last attestation change and force a regen every run.
        "git_sha": _head_short_sha(),
        "deferral_count": report["headline"]["deferral_count"],
        "conformant_rows": report["headline"]["conformant_rows"],
        "findings_count": report["headline"]["findings_count"],
        "ok": report["headline"]["ok"],
    }
    with open(LOG_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_line) + "\n")
    # Keep the toolkit-schema evaluate-report (docs/conformance/evaluate-report.json,
    # the PNT keystone's [verify].entrypoint output) current alongside report.json.
    # Local import avoids any load-order coupling; both modules share
    # conformance_lib as their single source of truth. Intentionally NOT wrapped
    # in try/except: an unmapped EX/CST row must fail this write loudly, the same
    # as it fails `just evaluate-report` and the pytest gate.
    from scripts import evaluate_report as _er
    _er.write_report()


def main(argv):
    probe_gh = "--no-gh" not in argv
    do_write = "--no-write" not in argv
    if_stale = "--if-stale" in argv

    # Snapshot-freshness short-circuit for `just test`: if the committed report
    # is recent enough, do nothing. Non-fatal regardless — findings are the
    # pytest gate's job, not this refresh's.
    if if_stale:
        n = _commits_since(_last_logged_sha())
        if n is not None and n < STALE_COMMITS:
            print("Conformance report fresh ({} commit(s) since last run).".format(n))
            return 0
        print("Conformance report stale ({}) — regenerating…".format(
            "no prior run" if n is None else "{} commits".format(n)))

    report = build_report(probe_gh=probe_gh)
    if do_write:
        write_artifacts(report)
    h = report["headline"]
    print("Conformance: {} conformant rows, {} deferrals (cap {}), {} findings — {}"
          .format(h["conformant_rows"], h["deferral_count"], h["deferral_cap"],
                  h["findings_count"], "OK" if h["ok"] else "FINDINGS"))
    for f in report["findings"]:
        print("  - [{kind}] {detail}".format(**f))
    if do_write:
        print("Wrote {}, {}, {}".format(
            os.path.relpath(REPORT_JSON, _REPO_ROOT),
            os.path.relpath(REPORT_MD, _REPO_ROOT),
            os.path.relpath(LOG_JSONL, _REPO_ROOT)))
    if if_stale:
        return 0  # snapshot refresh never fails a test run
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
