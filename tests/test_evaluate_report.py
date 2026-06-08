"""The deterministic evaluate-report emitter must itself be correct — its output
is the toolkit keystone's `[verify].entrypoint` artifact, the thing a PNT
maintainer (or CI) treats as ground truth for "does this candidate conform?".

These run hermetically: `render_contract_violations()` mirrors PNT's
`tools/report-fixtures-lint.py` so the fellows suite validates the render
contract without the toolkit checked out. When the toolkit *is* present locally,
`test_real_toolkit_lint_passes_when_available` runs the real lint as a
belt-and-suspenders cross-check.

See scripts/evaluate_report.py and plans/conformance_report_and_gate.md.
"""
import json
import os
import subprocess
import sys

import pytest

from scripts import evaluate_report as er

_FIXED_COMMIT = "0" * 40  # deterministic; avoids depending on git state


def _report():
    return er.build_evaluate_report(commit=_FIXED_COMMIT)


def test_satisfies_render_contract():
    """The whole point: the emitted report passes the toolkit render contract."""
    report = _report()
    violations = er.render_contract_violations(report)
    assert violations == [], violations


def test_is_reproducible():
    """Same commit + same attestation -> byte-identical output (no timestamp).
    This is what makes the artifact CI-able instead of churning every run."""
    a = json.dumps(_report(), sort_keys=True)
    b = json.dumps(_report(), sort_keys=True)
    assert a == b


def test_posture_is_conformant_on_current_attestation():
    """Current attestation has no non-conformances and nothing undetermined."""
    assert _report()["summary"]["posture"] == "conformant"


def test_top_level_shape():
    report = _report()
    assert report["report_schema_version"] == "0.1"
    cand = report["candidate"]
    assert cand["pna_spec_version"] == "0.1"
    assert cand["picks_source"] == "declared"
    assert cand["commit"] == _FIXED_COMMIT
    assert cand["axis_picks"]["distribution"] == "web-bundle-with-magic-link"


def test_every_finding_keys_by_ac_and_meets_status_rules():
    """ac_id matches the schema pattern; (non-)conformant carry citations;
    not-applicable / unable-to-determine carry a rationale."""
    for f in _report()["findings"]:
        assert er._AC_ID_RE.match(f["ac_id"]), f["ac_id"]
        if f["status"] in ("conformant", "non-conformant"):
            assert f.get("citations"), f["ac_id"]
        if f["status"] in ("not-applicable", "unable-to-determine"):
            assert f.get("rationale"), f["ac_id"]


def test_partial_rows_become_conformant_with_human_review():
    """The three self-attested partials map to conformant + needs_human_review,
    and lead the summary's concerns — the residual stays visible, not buried."""
    report = _report()
    flagged = {f["ac_id"] for f in report["findings"] if f.get("needs_human_review")}
    assert flagged == {"AC-16", "AC-PRM-A", "AC-MCP-A"}
    assert report["summary"]["leading_concerns"] == ["AC-16", "AC-PRM-A", "AC-MCP-A"]


def test_extensions_are_folded_not_dropped():
    """EX-* / CST-* are surfaced inside the AC findings they bear on (per the
    schema's $comment), never silently dropped — the honesty guarantee."""
    report = _report()
    blob = json.dumps(report)
    assert "EX-CLOUD-LLM" in blob
    # Every mapped extension id appears somewhere in the report's evidence.
    for ext_id in er.EXTENSION_AC_HOME:
        assert ext_id in blob, "{} dropped from evaluate-report".format(ext_id)


def test_unmapped_extension_fails_loudly(monkeypatch):
    """If the attestation grows an EX/CST row the home-map doesn't cover, the
    build RAISES rather than dropping a declared constraint. Drop EX-CLOUD-LLM's
    mapping and confirm the build refuses."""
    home = dict(er.EXTENSION_AC_HOME)
    home.pop("EX-CLOUD-LLM")
    monkeypatch.setattr(er, "EXTENSION_AC_HOME", home)
    with pytest.raises(ValueError, match="EXTENSION_AC_HOME"):
        er.build_evaluate_report(commit=_FIXED_COMMIT)


def test_committed_artifact_is_render_contract_valid():
    """The committed docs/conformance/evaluate-report.json — the file the toolkit
    actually reads — is itself valid (catches a stale/hand-edited commit)."""
    with open(er.OUT_PATH, encoding="utf-8") as f:
        committed = json.load(f)
    assert er.render_contract_violations(committed) == []


def test_real_toolkit_lint_passes_when_available(tmp_path):
    """Belt-and-suspenders: when the PNT checkout is present, the *real* lint
    (the authoritative render contract) accepts a freshly-built report. Skipped
    in environments without the toolkit (hermetic CI)."""
    lint = os.path.expanduser(
        os.environ.get("PNT_REPO", "~/src/personal_network_toolkit")
        + "/tools/report-fixtures-lint.py"
    )
    if not os.path.isfile(lint):
        pytest.skip("PNT toolkit lint not present at {}".format(lint))
    out_file = tmp_path / "evaluate-report.json"
    out_file.write_text(json.dumps(_report(), ensure_ascii=False))
    result = subprocess.run(
        [sys.executable, lint, str(out_file)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # The lint's per-file "ok" line + the "N/N reports satisfy the render
    # contract" summary (phrasing differs by version; returncode is the signal).
    assert "satisfy the render contract" in result.stdout
    assert "FAIL" not in result.stdout
