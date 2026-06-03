"""Security-adjacent invariants of the private-data capability gate.

The gate is a DURABILITY control, not a confidentiality boundary
(plans/private_data_capability_gate.md): off-folder the app is meant to be
browse-only with NO durable private store. Two guards live here:

1. test_gate_defaults_to_browse_only_without_folder (GREEN) — the gate must
   never default to "private enabled" without a verified folder. A regression
   that flipped it open would let the app create private data it cannot keep
   (silent loss) and would expose a store the user didn't ask for.

2. test_no_durable_private_write_when_browse_only (XFAIL, strict) — the
   INTENDED invariant: a browse-only session must not durably persist private
   data. This is NOT YET ENFORCED on main — EPIC PR1's gate is deliberately
   INERT (see the gate block in app/static/app.js), so off-folder mutations
   still land in OPFS. Enforcement (browse-only => localStorage-only / refuse
   private writes) lands in C1 PR3 of plans/private_data_capability_gate.md.
   When it does, this test XPASSes; strict xfail turns that into a failure so
   we notice, drop the marker, and promote it to a hard guard.
"""
import pytest

from tests.e2e.conftest import make_worker_data


def _boot_no_folder(page, base_url):
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )


def test_gate_defaults_to_browse_only_without_folder(standalone_page, base_url_fixture):
    page = standalone_page
    _boot_no_folder(page, base_url_fixture)
    # Let the gate resolve against the ready worker provider.
    page.wait_for_function(
        "() => window.__privateDataTier "
        "&& window.__privateDataTier.indexOf('browse-only') === 0",
        timeout=10000,
    )
    state = page.evaluate(
        """() => ({
            tier: window.__privateDataTier,
            enabled: window.__privateDataEnabled ? window.__privateDataEnabled() : null,
            noPrivateClass: document.body.classList.contains('no-private-data')
        })"""
    )
    assert state["tier"] == "browse-only-desktop", state
    assert state["enabled"] is False, "gate must not enable private data without a folder"
    assert state["noPrivateClass"] is True, "body must carry no-private-data when locked"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "EPIC PR1 gate is INERT: off-folder still persists to OPFS. Enforcement "
        "(browse-only => no durable private store) lands in C1 PR3 of "
        "plans/private_data_capability_gate.md. An XPASS here means it landed — "
        "remove this marker and promote to a hard guard."
    ),
)
def test_no_durable_private_write_when_browse_only(standalone_page, base_url_fixture):
    page = standalone_page
    wd = make_worker_data(page, base_url_fixture)
    if wd.provider_kind() != "worker":
        pytest.skip("needs worker provider")
    wd.wipe_relationships()
    # Confirm we really are browse-only (no folder attached).
    assert page.evaluate("() => window.__privateDataEnabled()") is False
    # Attempt a private mutation; swallow a future 'refused' error so the test
    # reflects the durability OUTCOME, not the throw shape.
    page.evaluate(
        """async () => {
            try {
                await window.__dataProvider.createGroup(
                    { name: 'browse-only-should-not-persist', note: '', fellow_record_ids: [] }
                );
            } catch (e) { /* future: refused off-folder — fine */ }
        }"""
    )
    # Reload: only a DURABLE store survives a fresh boot. Off-folder, nothing
    # private should.
    _boot_no_folder(page, base_url_fixture)
    groups = wd.list_groups()
    try:
        assert groups == [], f"browse-only session durably persisted a group: {groups}"
    finally:
        try:
            wd.wipe_relationships()
        except Exception:
            pass
