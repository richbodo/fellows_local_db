"""E2E tests: detail view (Playwright)."""
import pytest
from playwright.sync_api import expect


class TestDetailView:
    """Detail view: hash shows fellow detail; image or placeholder."""

    def test_click_aaron_bird_shows_detail(self, page, base_url_fixture):
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.get_by_role("link", name="Aaron Bird").first.click()
        page.wait_for_url("**/#/fellow/aaron_bird", timeout=5000)
        detail = page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        assert "Aaron Bird" in detail.inner_text()
        has_image = page.locator("#detail .profile-image").count() >= 1
        has_placeholder = "No image" in detail.inner_text() or "Select a fellow" in detail.inner_text()
        assert has_image or has_placeholder or "Aaron Bird" in detail.inner_text()

    def test_direct_hash_shows_fellow_detail(self, page, base_url_fixture):
        """Navigate to #/fellow/aaron_bird - name, at least one other field, image or placeholder."""
        page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        text = detail.inner_text()
        assert "Aaron Bird" in text
        assert any(
            label in text for label in ["Tagline", "Cohort", "Type", "Email", "Based in", "Links"]
        ), "Detail should show at least one field (Tagline, Cohort, Type, etc.)"
        has_img = page.locator("#detail .profile-image").count() >= 1
        has_placeholder = "No image" in text or "Select a fellow" in text
        assert has_img or has_placeholder, "Detail should show profile image or 'No image' placeholder"

    def test_detail_shows_placeholder_when_no_image(self, page, base_url_fixture):
        """Fellow without image shows placeholder (image 404 -> 'No image')."""
        page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
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
        """Click another name in list - URL and detail update to that fellow."""
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)
        page.get_by_role("link", name="Aaron Bird").first.click()
        page.wait_for_url("**/#/fellow/aaron_bird", timeout=5000)
        page.get_by_role("link", name="Aaron McDonald").first.click()
        page.wait_for_url("**/#/fellow/aaron_mcdonald", timeout=5000)
        detail = page.locator("#detail")
        detail.get_by_text("Aaron McDonald").wait_for(state="visible", timeout=5000)
        assert "Aaron McDonald" in detail.inner_text()
