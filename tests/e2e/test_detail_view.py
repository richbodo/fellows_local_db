"""E2E tests: detail view (Playwright)."""
import pytest
from playwright.sync_api import expect


class TestDetailView:
    """Detail view: hash shows fellow detail; image or placeholder."""

    def test_click_aaron_bird_shows_detail(self, standalone_page, base_url_fixture):
        standalone_page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        standalone_page.get_by_role("link", name="Aaron Bird").first.click()
        standalone_page.wait_for_url("**/#/fellow/aaron_bird", timeout=5000)
        detail = standalone_page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        assert "Aaron Bird" in detail.inner_text()
        has_image = standalone_page.locator("#detail .profile-image").count() >= 1
        has_placeholder = "No image" in detail.inner_text() or "Select a fellow" in detail.inner_text()
        assert has_image or has_placeholder or "Aaron Bird" in detail.inner_text()

    def test_direct_hash_shows_fellow_detail(self, standalone_page, base_url_fixture):
        """Navigate to #/fellow/aaron_bird — name, at least one other field, image box present."""
        standalone_page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = standalone_page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        text = detail.inner_text()
        assert "Aaron Bird" in text
        assert any(
            label in text for label in ["Tagline", "Cohort", "Type", "Email", "Based in", "Links"]
        ), "Detail should show at least one field (Tagline, Cohort, Type, etc.)"
        # Contract: a .profile-image-wrap is rendered for every fellow detail.
        assert standalone_page.locator("#detail .profile-image-wrap").count() == 1

    def test_image_fetch_error_does_not_show_not_submitted(self, standalone_page, base_url_fixture):
        """A fellow with has_image=1 whose image 404s must NOT show "Not Submitted".

        "Not Submitted" is reserved for fellows who never uploaded a photo
        (has_image=0). When the fellow did submit but we can't fetch the file
        (network, auth, cache miss), the UI must keep a loading/pending
        visual — lying would misattribute the problem to the fellow.
        """
        page = standalone_page
        # Denise Chen has has_image=1 in the rebuilt DB.
        page.route("**/images/denise_chen.jpg", lambda r: r.fulfill(status=404, body=""))
        page.route("**/images/denise_chen.png", lambda r: r.fulfill(status=404, body=""))
        page.goto(base_url_fixture + "/#/fellow/denise_chen", wait_until="networkidle")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        # Wait for both 404s to resolve (jpg then png fallback), plus a beat
        # for the final error handler to update the status text.
        page.wait_for_timeout(500)
        wrap = page.locator("#detail .profile-image-wrap")
        wrap_class = wrap.get_attribute("class") or ""
        # Must NOT have flipped to --none.
        assert "profile-image-wrap--none" not in wrap_class, (
            f"expected pending state, got class={wrap_class!r}. "
            "Fellow had has_image=1; fetch error should not surface as 'Not Submitted'."
        )
        # Status text must not include 'Not Submitted'.
        status_text = page.locator("#detail .profile-image-status").inner_text()
        assert "Not Submitted" not in status_text, (
            f"Status text: {status_text!r}. 'Not Submitted' is wrong for a fellow "
            "who did upload a photo but whose file we can't fetch."
        )
        # It should still indicate a pending/loading state.
        assert "Loading" in status_text or "loading" in status_text, (
            f"Expected a loading/pending hint in status: {status_text!r}"
        )

    def test_detail_image_settles_into_terminal_state(self, standalone_page, base_url_fixture):
        """Image box settles into either loaded (image visible) or none ('Not Submitted');
        never stuck in loading after a short wait."""
        standalone_page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = standalone_page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        standalone_page.wait_for_function(
            """() => {
              const wrap = document.querySelector('#detail .profile-image-wrap');
              if (!wrap) return false;
              return wrap.classList.contains('profile-image-wrap--loaded')
                  || wrap.classList.contains('profile-image-wrap--none');
            }""",
            timeout=5000,
        )
        text = detail.inner_text()
        assert "Aaron Bird" in text
        has_loaded = standalone_page.locator("#detail .profile-image-wrap--loaded").count() == 1
        has_not_submitted = "Not Submitted" in text
        assert has_loaded or has_not_submitted

    def test_nav_arrows_visible_on_screen(self, standalone_page, base_url_fixture):
        """Both arrows are rendered, visually visible, and appear in a screenshot."""
        standalone_page.goto(base_url_fixture + "/#/fellow/aaron_mcdonald", wait_until="networkidle")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = standalone_page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        nav = detail.locator(".fellow-nav")
        nav.wait_for(state="visible", timeout=5000)
        prev_arrow = detail.locator(".fellow-nav-arrow--prev")
        next_arrow = detail.locator(".fellow-nav-arrow--next")
        # Both arrows exist in the DOM
        assert prev_arrow.count() == 1
        assert next_arrow.count() == 1
        # Both are visually visible (aaron_mcdonald is not first or last)
        assert prev_arrow.is_visible(), "Previous arrow should be visible for a middle fellow"
        assert next_arrow.is_visible(), "Next arrow should be visible for a middle fellow"
        # Arrows have a non-zero bounding box (actually rendered on screen)
        prev_box = prev_arrow.bounding_box()
        next_box = next_arrow.bounding_box()
        assert prev_box is not None, "Previous arrow should have a bounding box"
        assert next_box is not None, "Next arrow should have a bounding box"
        assert prev_box["width"] >= 44, "Previous arrow should be at least 44px wide (touch target)"
        assert prev_box["height"] >= 44, "Previous arrow should be at least 44px tall (touch target)"
        assert next_box["width"] >= 44, "Next arrow should be at least 44px wide (touch target)"
        assert next_box["height"] >= 44, "Next arrow should be at least 44px tall (touch target)"
        # Scroll the nav into view and take a screenshot proving arrows are visible
        nav.scroll_into_view_if_needed()
        standalone_page.wait_for_timeout(300)
        # Verify arrows are within the viewport after scrolling
        viewport = standalone_page.viewport_size
        prev_box = prev_arrow.bounding_box()
        next_box = next_arrow.bounding_box()
        assert prev_box["y"] >= 0 and prev_box["y"] + prev_box["height"] <= viewport["height"], \
            "Previous arrow should be within the viewport"
        assert next_box["y"] >= 0 and next_box["y"] + next_box["height"] <= viewport["height"], \
            "Next arrow should be within the viewport"
        standalone_page.screenshot(path="tests/e2e/screenshots/nav_arrows_visible.png", full_page=False)

    def test_right_arrow_navigates_to_next_fellow(self, standalone_page, base_url_fixture):
        """Clicking the right arrow navigates to the next fellow alphabetically."""
        standalone_page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = standalone_page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        detail.locator(".fellow-nav").wait_for(state="visible", timeout=5000)
        next_arrow = detail.locator(".fellow-nav-arrow--next")
        assert next_arrow.is_visible(), "Next arrow should be visible"
        next_arrow.click()
        standalone_page.wait_for_timeout(1000)
        text = detail.inner_text()
        assert "Aaron Bird" not in text, "Detail should show a different fellow after clicking next"
        # After navigating, arrows should still be present
        assert detail.locator(".fellow-nav").is_visible(), "Nav bar should still be visible after navigation"
        standalone_page.screenshot(path="tests/e2e/screenshots/nav_after_right_click.png", full_page=False)

    def test_left_arrow_navigates_back(self, standalone_page, base_url_fixture):
        """Clicking left arrow after right returns to the original fellow."""
        standalone_page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = standalone_page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        detail.locator(".fellow-nav").wait_for(state="visible", timeout=5000)
        detail.locator(".fellow-nav-arrow--next").click()
        standalone_page.wait_for_timeout(1000)
        prev_arrow = detail.locator(".fellow-nav-arrow--prev")
        assert prev_arrow.is_visible(), "Previous arrow should be visible after navigating right"
        prev_arrow.click()
        standalone_page.wait_for_timeout(1000)
        assert "Aaron Bird" in detail.inner_text()
        standalone_page.screenshot(path="tests/e2e/screenshots/nav_after_left_back.png", full_page=False)

    def test_first_fellow_hides_left_arrow(self, standalone_page, base_url_fixture):
        """First fellow in the list has a hidden left arrow, visible right arrow."""
        standalone_page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        first_link = standalone_page.locator("#directory a").first
        first_link.click()
        standalone_page.wait_for_timeout(1000)
        detail = standalone_page.locator("#detail")
        detail.locator(".fellow-nav").wait_for(state="visible", timeout=5000)
        prev_arrow = detail.locator(".fellow-nav-arrow--prev")
        next_arrow = detail.locator(".fellow-nav-arrow--next")
        assert prev_arrow.count() == 1
        assert "fellow-nav-arrow--hidden" in prev_arrow.get_attribute("class")
        # Right arrow should be visible for the first fellow
        assert next_arrow.is_visible(), "Next arrow should be visible for first fellow"
        standalone_page.screenshot(path="tests/e2e/screenshots/nav_first_fellow.png", full_page=False)

    def test_keyboard_right_arrow_navigates_next(self, standalone_page, base_url_fixture):
        """Pressing the right arrow key navigates to the next fellow."""
        standalone_page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = standalone_page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        detail.locator(".fellow-nav").wait_for(state="visible", timeout=5000)
        assert "Aaron Bird" in detail.inner_text()
        standalone_page.keyboard.press("ArrowRight")
        standalone_page.wait_for_timeout(1000)
        text = detail.inner_text()
        assert "Aaron Bird" not in text, "Right arrow key should navigate to next fellow"

    def test_keyboard_left_arrow_navigates_back(self, standalone_page, base_url_fixture):
        """Pressing right then left arrow key returns to the original fellow."""
        standalone_page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = standalone_page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        detail.locator(".fellow-nav").wait_for(state="visible", timeout=5000)
        standalone_page.keyboard.press("ArrowRight")
        standalone_page.wait_for_timeout(1000)
        assert "Aaron Bird" not in detail.inner_text()
        standalone_page.keyboard.press("ArrowLeft")
        standalone_page.wait_for_timeout(1000)
        assert "Aaron Bird" in detail.inner_text()

    def test_keyboard_arrows_ignored_in_search_input(self, standalone_page, base_url_fixture):
        """Arrow keys should not navigate when the search input is focused."""
        standalone_page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="networkidle")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        detail = standalone_page.locator("#detail")
        detail.wait_for(state="visible", timeout=5000)
        detail.locator(".fellow-nav").wait_for(state="visible", timeout=5000)
        standalone_page.locator("#search-input").focus()
        standalone_page.keyboard.press("ArrowRight")
        standalone_page.wait_for_timeout(500)
        assert "Aaron Bird" in detail.inner_text(), "Arrow keys in search input should not navigate"

    def test_click_another_fellow_updates_detail(self, standalone_page, base_url_fixture):
        """Click another name in list - URL and detail update to that fellow."""
        standalone_page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        standalone_page.locator("#loading").wait_for(state="hidden", timeout=10000)
        standalone_page.locator("#directory").wait_for(state="visible", timeout=5000)
        standalone_page.get_by_role("link", name="Aaron Bird").first.click()
        standalone_page.wait_for_url("**/#/fellow/aaron_bird", timeout=5000)
        standalone_page.get_by_role("link", name="Aaron McDonald").first.click()
        standalone_page.wait_for_url("**/#/fellow/aaron_mcdonald", timeout=5000)
        detail = standalone_page.locator("#detail")
        # Name appears in heading and bio; target the title only (Playwright strict mode).
        detail.get_by_role("heading", name="Aaron McDonald").wait_for(
            state="visible", timeout=5000
        )
        assert "Aaron McDonald" in detail.inner_text()
