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

    def test_download_userdata_button_present(
        self, standalone_page, base_url_fixture
    ):
        """PR D: Settings page exposes a Download my user data button.
        The actual export only works on the OPFS path (which the dev e2e
        harness doesn't have — see the SharedArrayBuffer warning in
        console). This test asserts the markup is in place; the OPFS
        round-trip is real-browser-only."""
        page = standalone_page
        page.goto(f"{base_url_fixture}/#/settings", wait_until="domcontentloaded")
        _wait_for_directory(page)
        expect(page.locator("#settings-export-section")).to_be_visible()
        expect(page.locator("#settings-download-userdata")).to_be_visible()
        expect(page.locator(".settings-section-title").first).to_contain_text("Your saved data")

    def test_restore_section_renders_with_picker_and_backup_list(
        self, standalone_page, base_url_fixture
    ):
        """Issue #85: Settings exposes a Restore from a file button + a
        Recent auto-backups list. Like the export half (PR #84), the
        actual restore round-trip needs OPFS, which the dev e2e harness
        doesn't have. This test asserts the markup renders; the OPFS
        round-trip is verified manually on prod (see issue #85 test plan)."""
        page = standalone_page
        page.goto(f"{base_url_fixture}/#/settings", wait_until="domcontentloaded")
        _wait_for_directory(page)
        # Restore section + heading.
        expect(page.locator("#settings-restore-section")).to_be_visible()
        expect(
            page.locator("#settings-restore-section .settings-section-title")
        ).to_contain_text("Restore from backup")
        # File-picker affordance: input is hidden by design; the visible
        # button click()s the input. Both must exist.
        expect(page.locator("#settings-restore-pick")).to_be_visible()
        file_input = page.locator("#settings-restore-file")
        expect(file_input).to_have_count(1)
        accept = file_input.get_attribute("accept") or ""
        assert ".db" in accept and ".sqlite" in accept
        # Recent auto-backups list region: in API mode (dev) the list
        # resolves to [] and the empty-state hint is what the user sees.
        expect(page.locator("#settings-backup-list-empty")).to_be_visible()
        # Live list itself is hidden until populated.
        backup_list = page.locator("#settings-backup-list")
        expect(backup_list).to_have_count(1)
        assert backup_list.evaluate("el => el.hidden") is True
