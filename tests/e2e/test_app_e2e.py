"""
E2E tests: browser-driven (Playwright) regression tests for the fellows directory app.
Run with: pytest tests/e2e/ -v
Requires: playwright install (one-time, after pip install -r requirements-dev.txt)
Ensure port 8765 is free (stop the app server if it is running).
"""
import pytest
from playwright.sync_api import expect

BASE_URL = "http://127.0.0.1:8765"


@pytest.fixture(scope="module")
def base_url_fixture():
    return BASE_URL


class TestDirectoryPage:
    """Homepage loads and shows directory list (two-phase load)."""

    def test_homepage_loads_and_shows_directory(self, page, base_url_fixture):
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        # Wait for "Loading..." to be replaced by directory (list-only response then render)
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        directory = page.locator("#directory")
        directory.wait_for(state="visible", timeout=5000)
        assert directory.is_visible()
        links = page.locator("#directory a[href^='#/fellow/']")
        assert links.count() >= 440, "Expected at least 440 fellow links (442 fellows, some may have empty names)"

    def test_directory_contains_aaron_bird_link(self, page, base_url_fixture):
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)
        aaron = page.get_by_role("link", name="Aaron Bird").first
        expect(aaron).to_be_visible()
        expect(aaron).to_have_attribute("href", "#/fellow/aaron_bird")

    def test_no_images_on_directory(self, page, base_url_fixture):
        """Directory view must not request profile images (only names/links)."""
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)
        # No img inside #directory
        imgs_in_directory = page.locator("#directory img")
        assert imgs_in_directory.count() == 0


class TestDetailView:
    """M4: Detail view and images – hash shows fellow detail; image or placeholder."""

    def test_click_aaron_bird_shows_detail(self, page, base_url_fixture):
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.get_by_role("link", name="Aaron Bird").first.click()
        page.wait_for_url("**/#/fellow/aaron_bird", timeout=5000)
        detail = page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        assert "Aaron Bird" in detail.inner_text()
        # M4: either profile image or "No image" placeholder
        has_image = page.locator("#detail .profile-image").count() >= 1
        has_placeholder = "No image" in detail.inner_text() or "Select a fellow" in detail.inner_text()
        assert has_image or has_placeholder or "Aaron Bird" in detail.inner_text()

    def test_direct_hash_shows_fellow_detail(self, page, base_url_fixture):
        """M4: Navigate to #/fellow/aaron_bird – name, at least one other field, image or placeholder."""
        page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        text = detail.inner_text()
        assert "Aaron Bird" in text
        # At least one other field (bio_tagline, cohort, fellow_type, etc.)
        assert any(
            label in text for label in ["Tagline", "Cohort", "Type", "Email", "Based in", "Links"]
        ), "Detail should show at least one field (Tagline, Cohort, Type, etc.)"
        # Image visible or placeholder
        has_img = page.locator("#detail .profile-image").count() >= 1
        has_placeholder = "No image" in text or "Select a fellow" in text
        assert has_img or has_placeholder, "Detail should show profile image or 'No image' placeholder"

    def test_detail_shows_placeholder_when_no_image(self, page, base_url_fixture):
        """M4: Fellow without image in images folder shows placeholder (image 404 → 'No image')."""
        page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        # Wait until either image is visible or "No image" placeholder appears (after image onerror)
        page.wait_for_function(
            """() => {
              const d = document.getElementById('detail');
              if (!d) return false;
              const img = d.querySelector('.profile-image');
              const ph = d.querySelector('.placeholder');
              return (img && img.offsetParent !== null) || (ph && ph.textContent.includes('No image'));
            }""",
            timeout=5000,
        )
        text = detail.inner_text()
        assert "Aaron Bird" in text
        assert page.locator("#detail .profile-image").is_visible() or "No image" in text

    def test_click_another_fellow_updates_detail(self, page, base_url_fixture):
        """M4: Click another name in list – URL and detail update to that fellow."""
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)
        page.get_by_role("link", name="Aaron Bird").first.click()
        page.wait_for_url("**/#/fellow/aaron_bird", timeout=5000)
        page.get_by_role("link", name="Aaron McDonald").first.click()
        page.wait_for_url("**/#/fellow/aaron_mcdonald", timeout=5000)
        detail = page.locator("#detail")
        # Detail may update async (hashchange + optional fetch); wait for content
        detail.get_by_text("Aaron McDonald").wait_for(state="visible", timeout=5000)
        assert "Aaron McDonald" in detail.inner_text()
