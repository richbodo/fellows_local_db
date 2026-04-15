"""E2E: browser tab shows install landing only (Phase 1 PWA)."""
import pytest
from playwright.sync_api import expect


class TestInstallLanding:
    """Without standalone display mode, directory must not load."""

    def test_browser_tab_shows_install_not_directory(self, page, base_url_fixture):
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        landing = page.locator("#install-landing")
        expect(landing).to_be_visible()
        expect(page.locator("#site-header")).to_be_hidden()
        expect(page.locator("#app-wrap")).to_be_hidden()
        expect(page.get_by_role("button", name="Install app")).to_be_visible()
