"""Strict-xfail discipline: every deferral is anchored and the load is capped.

Two invariants, both offline/static, companion to
`tests/test_attestation_has_evidence.py`. Primitives live in
`scripts/conformance_lib.py` (shared with the report generator). See
`plans/conformance_report_and_gate.md`.

1. **Anchored.** Every `@pytest.mark.xfail(strict=True)` reason must carry a
   machine-readable `tracking: #NNN` issue anchor. An *issue* (not a PR): issues
   close when the *work* is done; a PR closes when *something* merges. The prose
   "names the PR that will satisfy it" convention was unenforceable — nothing
   parsed it, so a deferral could outlive every PR that named it. This makes the
   anchor data, and (in the report) lets us flag an anchor whose issue is closed
   while the test still xfails — the abandoned-deferral case `strict=True` is
   structurally blind to (it trips on accidental *success*, never on abandoned
   *deferral*).

2. **Capped at 3.** At most three strict-xfail deferrals may exist in `tests/`
   at once. This project builds most features in ~3 PRs; a deferral load past
   one feature's worth is the smell. Keeps the attestation glanceable — a short,
   bounded list of honest frontiers, not a ledger of debt the eye glazes over.
   The 4th deferral fails the build: pay down before you defer more.
"""
from scripts.conformance_lib import (
    DEFERRAL_CAP,
    TRACKING_ANCHOR,
    collect_strict_xfails,
)


def test_every_strict_xfail_has_tracking_anchor():
    findings = []
    for d in collect_strict_xfails():
        if not TRACKING_ANCHOR.search(d["reason"]):
            findings.append(
                "{file}::{name} is `xfail(strict=True)` with no `tracking: #NNN` "
                "issue anchor in its reason. A deferral must point at an open "
                "issue that stays open until the test XPASSes.".format(**d)
            )
    assert not findings, (
        "Strict-xfail deferrals missing a machine-readable issue anchor "
        "(see plans/conformance_report_and_gate.md):\n  - " + "\n  - ".join(findings)
    )


def test_strict_xfail_load_under_cap():
    deferrals = collect_strict_xfails()
    assert len(deferrals) <= DEFERRAL_CAP, (
        "{} strict-xfail deferrals exceeds the cap of {}. Pay down a deferral "
        "before adding another — the conformance attestation must stay "
        "glanceable, not become a debt ledger (see "
        "plans/conformance_report_and_gate.md):\n  - ".format(
            len(deferrals), DEFERRAL_CAP
        )
        + "\n  - ".join("{file}::{name}".format(**d) for d in deferrals)
    )
