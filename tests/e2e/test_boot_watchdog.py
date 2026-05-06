"""E2E: boot watchdog surfaces a recovery panel when boot stalls.

The watchdog catches the gap between worker init success and getList
success — the blind spot we hit on 2026-05-06 when use-in-tab booted
into an indefinite "Loading…" with no actionable feedback. With the
watchdog, a stalled boot flips to a panel that names the last
completed phase and offers Reload / Clear App Cache / Send report.

The ?wd=<ms> URL override shortens BOOT_WATCHDOG_MS so these tests
finish in well under a second.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect


class TestBootWatchdog:
    def test_watchdog_fires_and_shows_recovery_panel_when_boot_hangs(
        self, page, base_url_fixture
    ):
        """Block the two endpoints bootDirectoryAsApp ultimately needs:
        - /fellows.db (worker cold-start fetch via _ensureFellowsDb)
        - /api/fellows (api+idb fallback when worker unavailable)

        With both blocked, the boot chain stalls. The shortened
        watchdog fires and the panel appears.
        """

        def _hang(route):
            # Returning without calling continue/fulfill/abort holds
            # the request pending. The watchdog fires well before any
            # network timeout.
            pass

        page.route("**/api/fellows*", _hang)
        page.route("**/fellows.db", _hang)

        page.goto(base_url_fixture + "/?wd=300", wait_until="domcontentloaded")

        # The recovery panel should become visible inside #loading-panel
        # within a couple of seconds (300 ms timer + ~hundred ms render).
        page.wait_for_selector("#boot-stuck-panel:not(.hidden)", timeout=5000)
        expect(page.locator("#boot-stuck-panel")).to_be_visible()

        # The watchdog state machine should have transitioned to fired,
        # not cleared. (cleared would mean get_list_done resolved despite
        # our route block — would indicate a routing miss.)
        state = page.evaluate("(window.__bootWatchdog || {}).state")
        assert state == "fired", (
            f"watchdog should have fired with both critical fetches blocked; got: {state}"
        )

        # Last-mark text should be populated. We don't assert a specific
        # mark name because the exact phase that completes before the
        # block depends on whether the worker init won the race against
        # the watchdog — both 'script_start' and 'pick_provider_start'
        # are valid here. The load-bearing assertion is that the user
        # gets *some* phase name, not 'unknown'.
        last_mark = page.locator("#boot-stuck-last-mark").inner_text()
        assert last_mark, "last-mark element should not be empty"
        assert last_mark != "unknown"

        # The three recovery affordances must be present and clickable.
        expect(page.locator("#boot-stuck-reload-button")).to_be_visible()
        expect(page.locator("#boot-stuck-clear-cache-button")).to_be_visible()
        expect(page.locator("#bug-report-button-boot-stuck")).to_be_visible()

    def test_watchdog_does_not_fire_on_normal_boot(self, page, base_url_fixture):
        """Negative case: a healthy boot should leave the watchdog in
        'cleared' state and never reveal the recovery panel. Catches
        the regression where the watchdog fires too eagerly (e.g. the
        clear path fails to wire up).
        """
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)

        expect(page.locator("#app-wrap")).to_be_visible()
        expect(page.locator("#boot-stuck-panel")).to_be_hidden()

        state = page.evaluate("(window.__bootWatchdog || {}).state")
        assert state == "cleared", (
            f"watchdog should have cleared on a healthy boot; got: {state}"
        )

    def test_reload_button_in_recovery_panel_reloads_the_page(
        self, page, base_url_fixture
    ):
        """The Reload button must actually trigger a page navigation.
        Wired via window.location.reload() in initBootStuckPanelButtons.
        """

        def _hang(route):
            pass

        page.route("**/api/fellows*", _hang)
        page.route("**/fellows.db", _hang)

        page.goto(base_url_fixture + "/?wd=300", wait_until="domcontentloaded")
        page.wait_for_selector("#boot-stuck-panel:not(.hidden)", timeout=5000)

        # Drop the route blocks so the reload can succeed and we can
        # observe the new page settled.
        page.unroute("**/api/fellows*")
        page.unroute("**/fellows.db")

        with page.expect_navigation(timeout=10000):
            page.click("#boot-stuck-reload-button")

        # After reload the panel should be hidden again. Boot doesn't
        # need to fully complete for this assertion — the panel state
        # is per-page-load, so a fresh navigation alone is the proof.
        expect(page.locator("#boot-stuck-panel")).to_be_hidden()
