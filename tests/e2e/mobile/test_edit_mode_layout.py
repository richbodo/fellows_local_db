"""Mobile-viewport regression test for edit-mode layout.

PR #75 (mobile shell) shipped a focus-mode rule that hid `#directory`
and `#group-rail` on every non-directory route at <=1024px widths. That
collapsed `#/edit/<id>` to nothing, since edit mode is rail-driven and
the central `#detail` pane is already hidden by design. This test pins
the carve-out so the bug can't return silently.

Runs across the same Pixel 5 / iPhone 13 / narrow-360 matrix as the
screenshot smoke test (`tests/e2e/mobile/test_routes.py`).
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect


@pytest.mark.skip(
    reason="Mobile edit mode is removed under the private-data capability gate "
    "(no groups/edit on phones — see plans/private_data_capability_gate.md). "
    "This test and the other mobile group tests are rewritten/retired in the "
    "PR6 mobile rebuild. It also has a pre-existing boot-race flake "
    "(enterEditMode redirects to #/groups when route() runs before "
    "dataProvider is assigned), independent of the gate."
)
def test_edit_mode_keeps_rails_visible_on_mobile(
    mobile_page, base_url_fixture
):
    """On `#/edit/<id>` at mobile widths, the fellow-picker and editing rail
    must both be visible. Without them the page is blank and edit mode is
    unusable (PR #75 regression).

    Test group is seeded via window.__dataProvider — Phase 1 of
    plans/local_first_worker_architecture.md retired the dev server's
    /api/groups route, so the HTTP-fixture approach this test originally
    used now silently pytest.skips. OPFS is per-origin per-context, so
    the group survives the second goto inside the same mobile_page
    fixture."""
    page = mobile_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    record = page.evaluate(
        """() => window.__dataProvider.createGroup({
            name: 'Mobile edit-mode regression',
            note: 'Created by tests/e2e/mobile/test_edit_mode_layout.py.',
            fellow_record_ids: [],
        })"""
    )
    gid = int(record["id"])
    # In-app navigation (hash change), NOT a full reload: a reload races
    # route() against provider_ready, and enterEditMode redirects to
    # #/groups when dataProvider isn't assigned yet (app.js:6450) — a
    # pre-existing flake (~2/3 runs bounced one device). With the worker
    # provider already live from the first boot, enterEditMode loads the
    # group deterministically. The rail-visibility regression assertions
    # below (the test's actual point — PR #75 focus-mode carve-out) are
    # unchanged.
    page.evaluate(f"() => {{ window.location.hash = '#/edit/{gid}'; }}")

    # `to_have_class` matches the full attribute string, not a containment
    # check. Use a regex so we don't have to mirror every other class on body.
    expect(page.locator("body")).to_have_class(
        re.compile(r"\broute-group-edit\b"),
        timeout=3000,
    )
    expect(page.locator("#edit-mode-banner")).to_be_visible()
    expect(page.locator("#directory")).to_be_visible()
    expect(page.locator("#group-rail")).to_be_visible()
