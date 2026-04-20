"""E2E tests: About-page "Check for updates" button + server-drift banner.

Exercises the Phase-2 update check: a boot snapshot of ``/build-meta.json``
is compared against the latest value each time the user clicks the button
(and, in production, once an hour). When the server git_sha has changed,
the shared ``#sw-update-banner`` is surfaced so the user can reload.
"""
import json

import pytest
from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


BUILD_META_PATH = "**/build-meta.json"


def _route_build_meta(context, git_sha, built_at="2026-04-20T00:00:00Z"):
    # NB: use context.route (not page.route) — page.route only fires for the
    # first matching request in our Playwright version; the boot fetch and the
    # button-click fetch both need to be mocked.
    body = json.dumps({"git_sha": git_sha, "built_at": built_at})

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


class TestAboutUpdateCheck:
    """About-page "Check for updates" flow."""

    def test_up_to_date_shows_reassuring_status(self, context, base_url_fixture):
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            # Let the boot fetch land and populate bootBuildMeta.
            page.wait_for_timeout(300)

            btn = page.locator("#about-check-updates")
            expect(btn).to_be_visible()
            btn.click()
            status = page.locator("#about-update-status")
            expect(status).to_contain_text("latest version", timeout=5000)
            expect(page.locator("#sw-update-banner")).to_be_hidden()
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()

    def test_server_drift_surfaces_banner_and_status(self, context, base_url_fixture):
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            page.wait_for_timeout(300)

            # A newer build is now live — re-arm the mock with a different sha.
            context.unroute(BUILD_META_PATH)
            _route_build_meta(context, git_sha="xyz999")

            page.locator("#about-check-updates").click()
            status = page.locator("#about-update-status")
            expect(status).to_contain_text("New version available", timeout=5000)
            expect(page.locator("#sw-update-banner")).to_be_visible()
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()

    def test_fetch_error_shows_unreachable_status(self, context, base_url_fixture):
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            page.wait_for_timeout(300)

            # Simulate server outage on the manual check.
            context.unroute(BUILD_META_PATH)
            context.route(
                BUILD_META_PATH,
                lambda r: r.fulfill(status=503, body="service unavailable"),
            )

            page.locator("#about-check-updates").click()
            status = page.locator("#about-update-status")
            expect(status).to_contain_text("Unable to reach", timeout=5000)
            expect(page.locator("#sw-update-banner")).to_be_hidden()
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()

    def test_users_manual_link_on_about_page(self, context, base_url_fixture):
        page = _make_standalone_page(context)
        try:
            _route_build_meta(context, git_sha="abc123")
            page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
            link = page.get_by_role("link", name="User Guide")
            expect(link).to_be_visible()
            expect(link).to_have_attribute(
                "href",
                "https://github.com/richbodo/fellows_local_db/blob/main/docs/users_manual.md",
            )
        finally:
            context.unroute(BUILD_META_PATH)
            page.close()
