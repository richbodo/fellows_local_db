"""E2E tests: About-page "Check for updates" button + server-drift banner.

Exercises the two-row update status block on About. A single button
drives both the app-shell check (existing checkForServerUpdate, which
raises the SW reload banner on `git_sha` drift) and the directory-data
check (compareFellowsDbSha). Each row populates its own status text and
optional action button independently.

plans/opt_in_directory_data_updates.md.
"""
import json

import pytest
from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


BUILD_META_PATH = "**/build-meta.json"


def _route_build_meta(context, git_sha, fellows_db_sha=None, built_at="2026-04-20T00:00:00Z"):
    # NB: use context.route (not page.route) — page.route only fires for the
    # first matching request in our Playwright version; the boot fetch and the
    # button-click fetch both need to be mocked.
    payload = {"git_sha": git_sha, "built_at": built_at}
    if fellows_db_sha is not None:
        payload["fellows_db_sha"] = fellows_db_sha
    body = json.dumps(payload)

    def _fulfill(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=body,
            headers={"Cache-Control": "no-cache"},
        )

    context.route(BUILD_META_PATH, _fulfill)


def _make_standalone_page(context):
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    return page


def _wait_for_boot_settled(page, timeout_ms: int = 15000) -> None:
    """Wait for the directory boot path to complete both ``route()``
    calls — once after ``getList`` and once after ``getFull``. Without
    this, the ``getFull``-triggered ``route()`` can re-render
    ``renderAboutPage`` mid-test, overwriting ``paintAppRow``'s output
    with the initial markup (build labels, no status suffix) and
    making this suite intermittently fail.

    The 300 ms ``wait_for_timeout`` the suite used to rely on caught
    the first re-render but not the second.
    """
    page.wait_for_function(
        "() => window.__bootMarks && window.__bootMarks.get_full_done != null",
        timeout=timeout_ms,
    )


class TestAboutUpdateCheck:
    """About-page "Check for updates" flow."""

    def test_up_to_date_shows_reassuring_status(self, context, base_url_fixture):
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            _wait_for_boot_settled(page)

            btn = page.locator("#about-check-updates")
            expect(btn).to_be_visible()
            btn.click()
            # App row shows "up to date" when git_sha matches.
            app_status = page.locator("#about-app-status")
            expect(app_status).to_contain_text("up to date", timeout=5000)
            expect(page.locator("#sw-update-banner")).to_be_hidden()
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()

    def test_server_drift_surfaces_banner_and_status(self, context, base_url_fixture):
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            _wait_for_boot_settled(page)

            # A newer build is now live — re-arm the mock with a different sha.
            context.unroute(BUILD_META_PATH)
            _route_build_meta(context, git_sha="xyz999")

            page.locator("#about-check-updates").click()
            app_status = page.locator("#about-app-status")
            expect(app_status).to_contain_text("App update available", timeout=5000)
            # The Reload affordance lives in the action cell.
            expect(page.locator("#about-app-update-btn")).to_be_visible()
            expect(page.locator("#sw-update-banner")).to_be_visible()
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()

    def test_fetch_error_shows_unreachable_status(self, context, base_url_fixture):
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            _wait_for_boot_settled(page)

            # Simulate server outage on the manual check.
            context.unroute(BUILD_META_PATH)
            context.route(
                BUILD_META_PATH,
                lambda r: r.fulfill(status=503, body="service unavailable"),
            )

            page.locator("#about-check-updates").click()
            app_status = page.locator("#about-app-status")
            expect(app_status).to_contain_text("Couldn", timeout=5000)
            expect(page.locator("#sw-update-banner")).to_be_hidden()
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()

    def test_users_manual_link_on_about_page(self, context, base_url_fixture):
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            _wait_for_boot_settled(page)
            link = page.get_by_role("link", name="Help from the user manual")
            expect(link).to_be_visible()
            expect(link).to_have_attribute(
                "href",
                "https://github.com/richbodo/fellows_local_db/blob/main/docs/users_manual.md",
            )
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()


class TestAboutDirectoryRefreshForMcpb:
    """The MCPB "Re-install Fellows directory extension" affordance
    lives in the About-page Directory data action cell (PR #204 moved
    it out of the MCPB Settings section). It surfaces only when the
    user has set up MCPB AND the bundled fellows.db sha is older than
    the server's current sha. Two visible scenarios:

      1. ``res.status === 'update-available'`` — local fellows.db is
         also behind server. Both buttons render side by side:
         "Update directory data" + "Re-install Fellows directory
         extension".
      2. ``res.status === 'up-to-date'`` but MCPB is still behind —
         local fellows.db has been refreshed already, MCPB extension
         in Claude Desktop has not. Only the MCPB refresh button
         renders, with explanatory status text.
    """

    def test_mcpb_button_hidden_when_no_mcpb_setup(self, context, base_url_fixture):
        """No localStorage record → no MCPB refresh button, even when
        directory data is out of date."""
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123", fellows_db_sha="server-sha-A")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            _wait_for_boot_settled(page)
            page.evaluate("localStorage.removeItem('fellows_mcpb_setup')")
            page.locator("#about-check-updates").click()
            # Allow either status to settle; button must NOT appear.
            page.wait_for_function(
                """() => {
                  const s = document.getElementById('about-data-status');
                  return s && s.textContent && !/Checking/.test(s.textContent);
                }""",
                timeout=5000,
            )
            assert page.locator("#about-data-mcpb-refresh-btn").count() == 0
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()

    def test_mcpb_button_appears_when_mcpb_sha_stale_vs_server(self, context, base_url_fixture):
        """MCPB set up with a stale fellows.db sha + server reports a
        different sha → the refresh button appears in the action cell."""
        page = _make_standalone_page(context)
        try:
            # MCPB recorded a setup with sha "stale-mcpb" — server now
            # returns "fresh-server". Status is 'up-to-date' or 'error'
            # depending on what compareFellowsDbSha returns from the
            # local worker; what matters for this test is that the MCPB
            # button surfaces regardless of the local-vs-server status.
            _route_build_meta(context, git_sha="abc123", fellows_db_sha="fresh-server")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            _wait_for_boot_settled(page)
            page.evaluate(
                """() => {
                  localStorage.setItem('fellows_mcpb_setup', JSON.stringify({
                    setupAt: new Date().toISOString(),
                    refreshedAt: new Date().toISOString(),
                    fellowsDbSha: 'stale-mcpb'
                  }));
                }"""
            )
            page.locator("#about-check-updates").click()
            # Button shows up once Check-for-updates completes.
            page.wait_for_selector("#about-data-mcpb-refresh-btn", timeout=5000)
            btn = page.locator("#about-data-mcpb-refresh-btn")
            expect(btn).to_be_visible()
            expect(btn).to_contain_text("Re-install Fellows directory extension")
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()

    def test_mcpb_button_hidden_when_mcpb_in_sync_with_server(self, context, base_url_fixture):
        """MCPB recorded the same fellows.db sha that the server now
        reports → no refresh needed → button stays hidden."""
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123", fellows_db_sha="same-sha")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            _wait_for_boot_settled(page)
            page.evaluate(
                """() => {
                  localStorage.setItem('fellows_mcpb_setup', JSON.stringify({
                    setupAt: new Date().toISOString(),
                    refreshedAt: new Date().toISOString(),
                    fellowsDbSha: 'same-sha'
                  }));
                }"""
            )
            page.locator("#about-check-updates").click()
            page.wait_for_function(
                """() => {
                  const s = document.getElementById('about-data-status');
                  return s && s.textContent && !/Checking/.test(s.textContent);
                }""",
                timeout=5000,
            )
            assert page.locator("#about-data-mcpb-refresh-btn").count() == 0
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()
