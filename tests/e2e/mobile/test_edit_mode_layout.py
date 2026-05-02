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

import json
import re
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import expect


@pytest.fixture
def edit_target_group(base_url_fixture):
    """Create a throwaway group; yield its id; delete after test."""
    body = json.dumps(
        {
            "name": "Mobile edit-mode regression",
            "note": "Created by tests/e2e/mobile/test_edit_mode_layout.py.",
            "fellow_record_ids": [],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base_url_fixture + "/api/groups",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        pytest.skip(f"dev server unreachable for group creation: {exc}")
    gid = int(payload["id"])
    yield gid
    try:
        del_req = urllib.request.Request(
            f"{base_url_fixture}/api/groups/{gid}", method="DELETE"
        )
        urllib.request.urlopen(del_req, timeout=5).read()
    except urllib.error.URLError:
        pass


def test_edit_mode_keeps_rails_visible_on_mobile(
    mobile_page, base_url_fixture, edit_target_group
):
    """On `#/edit/<id>` at mobile widths, the fellow-picker and editing rail
    must both be visible. Without them the page is blank and edit mode is
    unusable (PR #75 regression)."""
    page = mobile_page
    page.goto(
        f"{base_url_fixture}/#/edit/{edit_target_group}",
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
