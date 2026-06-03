"""The conformance report generator must itself be correct — it's the readout
the whole "always know the status" goal rests on. These run offline
(`probe_gh=False`); the one networked path (issue-state probe) is exercised by
monkeypatching the fail-open `gh` shim, never by hitting GitHub.

See plans/conformance_report_and_gate.md (PR2).
"""
from scripts import conformance_report as cr


def test_report_is_clean_on_current_attestation():
    """The shipped attestation must produce a finding-free report — same
    invariant the pytest gate asserts, exercised through the report path."""
    report = cr.build_report(probe_gh=False)
    h = report["headline"]
    assert h["ok"] is True, report["findings"]
    assert h["findings_count"] == 0
    assert h["total_rows"] >= h["conformant_rows"] >= 1
    assert h["deferral_count"] <= h["deferral_cap"]


def test_deferrals_are_anchored_in_report():
    report = cr.build_report(probe_gh=False)
    for d in report["deferrals"]:
        assert d["tracking_issue"] is not None, d


def test_closed_tracking_issue_is_an_abandoned_finding(monkeypatch):
    """The asymmetry fix: a strict-xfail whose tracking issue is CLOSED (while
    the test still xfails) is an abandoned deferral — must surface as a finding.
    This is the case `strict=True` is structurally blind to."""
    monkeypatch.setattr(cr, "_gh_issue_state", lambda n: "CLOSED")
    report = cr.build_report(probe_gh=True)
    kinds = {f["kind"] for f in report["findings"]}
    # Only meaningful if there's at least one anchored deferral to close.
    if any(d["tracking_issue"] for d in report["deferrals"]):
        assert "deferral-abandoned" in kinds, report["findings"]
        assert report["headline"]["ok"] is False


def test_unknown_issue_state_is_fail_open(monkeypatch):
    """An offline run / missing gh (state None) must never manufacture a
    finding — conformance status can't depend on network reachability."""
    monkeypatch.setattr(cr, "_gh_issue_state", lambda n: None)
    report = cr.build_report(probe_gh=True)
    assert not any(f["kind"] == "deferral-abandoned" for f in report["findings"])


def test_markdown_renders_without_error():
    report = cr.build_report(probe_gh=False)
    md = cr.render_md(report)
    assert md.startswith("# Conformance Report")
    assert "## Headline" in md and "## Findings" in md
