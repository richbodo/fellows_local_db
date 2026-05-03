"""E2E for the PR 5 Settings page + self_email round-trip.

Pins:
- #/settings renders the page with one input.
- Saving self_email persists across reload.
- Saved value also appears as the "to" address in the export
  "email it to me" hint after saving.
"""
from __future__ import annotations

import json
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect


def _conn(base_url):
    parsed = urlparse(base_url)
    return HTTPConnection(parsed.hostname, parsed.port, timeout=10)


def _wipe_groups(base_url):
    c = _conn(base_url)
    c.request("GET", "/api/groups")
    r = c.getresponse()
    body = r.read()
    c.close()
    if r.status != 200:
        return
    try:
        groups = json.loads(body)
    except ValueError:
        return
    for g in groups:
        c2 = _conn(base_url)
        c2.request("DELETE", f"/api/groups/{g['id']}")
        c2.getresponse().read()
        c2.close()


def _wipe_settings(base_url):
    c = _conn(base_url)
    c.request("GET", "/api/settings")
    r = c.getresponse()
    body = r.read()
    c.close()
    if r.status != 200:
        return
    try:
        bag = json.loads(body)
    except ValueError:
        return
    for k in bag.keys():
        c2 = _conn(base_url)
        payload = json.dumps({"value": ""}).encode("utf-8")
        c2.request(
            "PUT", f"/api/settings/{k}", body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        c2.getresponse().read()
        c2.close()


def _wait_for_directory(page):
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    # #app-wrap rather than #directory: the directory rail is now
    # display:none on group routes, so it's no longer a route-independent
    # readiness signal.
    page.locator("#app-wrap").wait_for(state="visible", timeout=5000)


@pytest.fixture(autouse=True)
def _reset(base_url_fixture):
    _wipe_groups(base_url_fixture)
    _wipe_settings(base_url_fixture)
    yield


class TestSettingsPage:
    def test_nav_link_navigates_to_settings(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(f"{base_url_fixture}/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#nav-settings-link").click()
        page.wait_for_url(lambda u: u.endswith("#/settings"), timeout=3000)
        expect(page.locator(".settings-title")).to_have_text("Settings")
        expect(page.locator("#settings-self-email")).to_be_visible()

    def test_save_self_email_persists_across_reload(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(f"{base_url_fixture}/#/settings", wait_until="domcontentloaded")
        _wait_for_directory(page)
        input_el = page.locator("#settings-self-email")
        input_el.fill("rich@example.com")
        page.locator(".settings-save").click()
        expect(page.locator("#settings-status")).to_have_text("Saved.")
        # Reload — the value comes back from relationships.settings (and
        # localStorage; either is fine).
        page.reload(wait_until="domcontentloaded")
        _wait_for_directory(page)
        expect(page.locator("#settings-self-email")).to_have_value("rich@example.com")

    def test_self_email_surfaces_in_export_input(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        # Set the email.
        page.goto(f"{base_url_fixture}/#/settings", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#settings-self-email").fill("rich@example.com")
        page.locator(".settings-save").click()
        expect(page.locator("#settings-status")).to_have_text("Saved.")
        # Now create a group and open the Export panel; the email input
        # should be prefilled with the saved address.
        c = _conn(base_url_fixture)
        c.request("GET", "/api/fellows?full=1")
        r = c.getresponse()
        body = r.read()
        c.close()
        rows = json.loads(body)
        rid = rows[0]["record_id"]
        c2 = _conn(base_url_fixture)
        payload = json.dumps({
            "name": "Prefill check", "fellow_record_ids": [rid],
        }).encode("utf-8")
        c2.request(
            "POST", "/api/groups", body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        gid = json.loads(c2.getresponse().read())["id"]
        c2.close()
        page.goto(f"{base_url_fixture}/#/groups/{gid}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#group-action-export").click()
        addr = page.locator("#export-self-email-addr")
        expect(addr).to_have_value("rich@example.com")

    def test_userdata_sections_in_dom_and_exposed_in_api_mode(
        self, standalone_page, base_url_fixture
    ):
        """The Settings page emits both the "Your saved data" (PR #84) and
        "Restore from backup" (PR #88) sections in the DOM. Their *content*
        depends on the data provider:
        - OPFS-backed sqlite provider → original markup (Download button +
          Restore picker + recent-backups list).
        - API provider → the export section is replaced by the
          local-data-unavailable panel (PR-this), and the restore section
          is hidden. This keeps the failure visible to the user with the
          existing browser-aware copy ("Try a hard reload, open Diagnostics,
          …") instead of silently disappearing both sections.

        Dev e2e runs in API-provider mode (Playwright's chromium does not
        expose `FileSystemFileHandle.prototype.createSyncAccessHandle` on the
        main thread, so the SAH-pool VFS can't install). The OPFS round-trip
        is verified on prod manually — see issue #85 test plan."""
        page = standalone_page
        page.goto(f"{base_url_fixture}/#/settings", wait_until="domcontentloaded")
        _wait_for_directory(page)
        export_section = page.locator("#settings-export-section")
        restore_section = page.locator("#settings-restore-section")
        # Both sections must be in the DOM (so OPFS-mode users get them
        # back when the provider is sqlite — same gate from PR #92).
        expect(export_section).to_have_count(1)
        expect(restore_section).to_have_count(1)
        # In dev (API provider), the export section is replaced by the
        # unavailable-panel, and the restore section is hidden.
        panel = export_section.locator(".local-data-unavailable")
        expect(panel).to_have_count(1)
        # The panel headline ends with either "right now" (runtime-failure
        # branch — Playwright's chromium reports as Chrome >= 102) or
        # "on this browser" (browser-too-old branch). Either way it's a
        # visible, user-readable message — the bug we're fixing was
        # silent disappearance, not the specific copy.
        headline = panel.locator("h3").inner_text()
        assert "backup and restore" in headline.lower(), headline
        # Restore section stays hidden so the panel is the single source
        # of "what's wrong + what to do."
        assert restore_section.evaluate("el => el.style.display") == "none", (
            "expected restore section hidden in API-provider mode"
        )
        # The download button is gone (its containing section was overwritten
        # by the panel). The restore-pick button still exists in the DOM
        # because the restore section is hidden via display:none rather than
        # rewritten — but it isn't reachable from the user's perspective
        # because its parent section is hidden, so the panel is the only
        # thing they actually see.
        expect(page.locator("#settings-download-userdata")).to_have_count(0)
        expect(page.locator("#settings-restore-pick")).not_to_be_visible()
