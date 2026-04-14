"""E2E tests: directory page (Playwright)."""
import pytest
from playwright.sync_api import expect


class TestDirectoryPage:
    """Homepage loads and shows directory list."""

    def test_homepage_loads_and_shows_directory(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        directory = page.locator("#directory")
        directory.wait_for(state="visible", timeout=5000)
        assert directory.is_visible()
        links = page.locator("#directory a[href^='#/fellow/']")
        assert links.count() >= 1, "Expected at least 1 fellow link"

    def test_directory_contains_aaron_bird_link(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)
        aaron = page.get_by_role("link", name="Aaron Bird").first
        expect(aaron).to_be_visible()
        expect(aaron).to_have_attribute("href", "#/fellow/aaron_bird")

    def test_no_images_on_directory(self, standalone_page, base_url_fixture):
        """Directory view must not request profile images (only names/links)."""
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)
        imgs_in_directory = page.locator("#directory img")
        assert imgs_in_directory.count() == 0
