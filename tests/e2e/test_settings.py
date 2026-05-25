"""E2E for the PR 5 Settings page + self_email round-trip.

Pins:
- #/settings renders the page with one input.
- Saving self_email persists across reload.
- Saved value also appears as the "to" address in the export
  "email it to me" hint after saving.

Phase 1 (plans/local_first_worker_architecture.md): setup that previously
went through the dev server's /api/groups + /api/settings HTTP routes
now drives window.__dataProvider via the worker_data fixture.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect


def _wait_for_directory(page):
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    # #app-wrap rather than #directory: the directory rail is now
    # display:none on group routes, so it's no longer a route-independent
    # readiness signal.
    page.locator("#app-wrap").wait_for(state="visible", timeout=5000)


class TestSettingsPage:
    def test_nav_link_navigates_to_settings(self, worker_data, base_url_fixture):
        # worker_data already navigated, populated __dataProvider, and wiped
        # state. The page is on the directory; nav link to settings.
        page = worker_data.page
        _wait_for_directory(page)
        page.locator("#nav-settings-link").click()
        page.wait_for_url(lambda u: u.endswith("#/settings"), timeout=3000)
        expect(page.locator(".settings-title")).to_have_text("Settings")
        expect(page.locator("#settings-self-email")).to_be_visible()

    def test_save_self_email_persists_across_reload(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        page.goto(f"{base_url_fixture}/#/settings", wait_until="domcontentloaded")
        _wait_for_directory(page)
        input_el = page.locator("#settings-self-email")
        input_el.fill("rich@example.com")
        page.locator(".settings-save").click()
        expect(page.locator("#settings-status")).to_have_text("Saved.")
        # Reload — the value comes back from relationships.settings (and
        # localStorage; either is fine).
        page.reload(wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        expect(page.locator("#settings-self-email")).to_have_value("rich@example.com")

    def test_self_email_surfaces_in_export_input(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        # Set the email via the UI so the test exercises the same code
        # path the user does (settings UI → setSetting RPC).
        page.goto(f"{base_url_fixture}/#/settings", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#settings-self-email").fill("rich@example.com")
        page.locator(".settings-save").click()
        expect(page.locator("#settings-status")).to_have_text("Saved.")
        # Now create a group via the worker (the test doesn't care about
        # the create-group UI; just needs a group to land on).
        full = worker_data.get_full_fellows()
        rid = full[0]["record_id"]
        group = worker_data.create_group("Prefill check", fellow_record_ids=[rid])
        gid = group["id"]
        page.goto(f"{base_url_fixture}/#/groups/{gid}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        page.locator("#group-action-export").click()
        addr = page.locator("#export-self-email-addr")
        expect(addr).to_have_value("rich@example.com")

    def test_userdata_sections_in_dom_and_failure_is_never_silent(
        self, worker_data, base_url_fixture
    ):
        """The Settings page emits both the "Your saved data" (PR #84) and
        "Restore from backup" (PR #88) sections in the DOM. Their *content*
        depends on which backend the data provider picked:

        - worker ('worker', this PR onward) → original markup (Download +
          Restore + recent-backups list).
        - api+idb fallback ('api+idb') → the export section is replaced
          by the local-data-unavailable panel (PR #95), and the restore
          section is hidden.

        The shipped guarantee from PR #95 is that the failure is never
        silent: a user who came to back up their data either sees a
        working backup section OR sees an explanation of what's wrong.
        This test asserts that invariant — exactly one of the two
        renders, regardless of which backend Playwright's chromium ends
        up with.
        """
        page = worker_data.page
        page.goto(f"{base_url_fixture}/#/settings", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        # Post-PR-#205: the Download button lives inside the Private
        # data folder section; the api+idb fallback panel renders into
        # a dedicated container inside the same section.
        folder_section = page.locator("#settings-folder-section")
        restore_section = page.locator("#settings-restore-section")
        expect(folder_section).to_have_count(1)
        expect(restore_section).to_have_count(1)
        file_input = page.locator("#settings-restore-file")
        expect(file_input).to_have_count(1)
        accept = file_input.get_attribute("accept") or ""
        assert ".db" in accept and ".sqlite" in accept

        # The shipped guarantee: either backup works or we say why.
        download_btn = page.locator("#settings-download-userdata")
        panel = page.locator("#settings-local-data-fallback .local-data-unavailable")
        button_visible = download_btn.count() == 1 and download_btn.is_visible()
        panel_present = panel.count() == 1

        assert button_visible or panel_present, (
            "expected EITHER a working Download button (worker mode) "
            "OR the local-data-unavailable panel (api+idb fallback) — got neither"
        )
        assert not (button_visible and panel_present), (
            "didn't expect both the Download button AND the panel to render; "
            "they're mutually exclusive states"
        )

        if panel_present:
            # api+idb fallback (no worker available). PR #95 invariants.
            headline = panel.locator("h3").inner_text()
            assert "backup and restore" in headline.lower(), headline
            assert restore_section.evaluate("el => el.style.display") == "none", (
                "panel mode should hide the restore section"
            )
            # PR #96 invariant — boot trace is embedded inline, not
            # buried behind a Diagnostics click.
            trace = panel.locator("details.local-data-unavailable-trace")
            expect(trace).to_have_count(1)
            trace_text = trace.locator("pre").text_content() or ""
            assert len(trace_text.strip()) > 0, "expected non-empty boot trace"
            assert "opfs" in trace_text.lower(), trace_text
        else:
            # worker mode — backup section is real.
            # Restore section visible, picker button present.
            expect(restore_section).to_be_visible()
            expect(page.locator("#settings-restore-pick")).to_be_visible()
