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

from playwright.sync_api import expect


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
    page.goto(
        f"{base_url_fixture}/#/edit/{gid}",
        wait_until="domcontentloaded",
    )
    page.locator("#loading").wait_for(state="hidden", timeout=10000)

    # `to_have_class` matches the full attribute string, not a containment
    # check. Use a regex so we don't have to mirror every other class on body.
    expect(page.locator("body")).to_have_class(
        re.compile(r"\broute-group-edit\b"),
        timeout=3000,
    )
    expect(page.locator("#edit-mode-banner")).to_be_visible()
    expect(page.locator("#directory")).to_be_visible()
    expect(page.locator("#group-rail")).to_be_visible()
