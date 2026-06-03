"""Security-adjacent invariant of the private-data capability gate.

The gate is a DURABILITY control, not a confidentiality boundary
(plans/private_data_capability_gate.md): off-folder the app is meant to be
browse-only with NO durable private store.

This file guards the gate's *default*: it must never resolve to "private
enabled" without a verified folder. A regression that flipped it open would let
the app create private data it cannot keep (silent loss) and expose a store the
user didn't ask for.

The companion invariant — "a browse-only mutation writes nothing durable" — is
now ENFORCED at the data layer and pinned by the hard guards in
tests/e2e/test_private_data_enforcement.py (this file previously held a
strict-xfail placeholder for it, removed once enforcement landed).
"""


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
