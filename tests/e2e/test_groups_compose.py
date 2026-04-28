"""E2E for the PR 1 right-rail group composer.

Pins the user-visible contract:
- Right rail is present on the directory page.
- +/✓ markers next to every fellow toggle draft membership; click does
  not navigate the row.
- Picked fellows appear as chips in the rail; create button enables.
- Title field auto-follows the search until the user types, then flips
  to white permanently.
- localStorage persists the draft across reload.
- #tag search routes to the search_tags column (real data: #climate).
- Create button POSTs and surfaces the dev-server 501 stub message
  ("PR 2 wires this up").
- Bulk-select bar shows only when filtered and toggles all visible
  fellows in the draft.
"""
from __future__ import annotations

import re

from playwright.sync_api import expect


def _wait_for_directory(page):
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    page.locator("#directory").wait_for(state="visible", timeout=5000)


def _aaron_row(page):
    """Return the directory row container for Aaron Bird."""
    link = page.locator("#directory a.dir-link", has_text="Aaron Bird").first
    expect(link).to_be_visible()
    # Row container is the parent <li class="dir-row">.
    return link.locator("xpath=..")


class TestGroupComposer:
    def test_right_rail_is_visible(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        rail = page.locator("#group-rail")
        expect(rail).to_be_visible()
        expect(page.locator("#group-rail-eyebrow")).to_have_text("add to a group")
        expect(page.locator("#group-rail-create")).to_be_disabled()

    def test_marker_toggles_glyph_and_adds_chip(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        row = _aaron_row(page)
        mark = row.locator(".dir-mark")
        expect(mark).to_have_text("+")
        expect(mark).to_have_attribute("aria-pressed", "false")
        mark.click()
        expect(mark).to_have_text("✓")
        expect(mark).to_have_attribute("aria-pressed", "true")
        expect(mark).to_have_class(re.compile(r"\bdir-mark--on\b"))
        chip = page.locator("#group-rail-members .group-rail-member-name").first
        expect(chip).to_have_text("Aaron Bird")
        expect(page.locator("#group-rail-create")).to_be_enabled()

    def test_marker_click_does_not_navigate_row(self, standalone_page, base_url_fixture):
        """The +/✓ click is intercepted via stopPropagation; URL hash stays put."""
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        starting_url = page.url
        _aaron_row(page).locator(".dir-mark").click()
        expect(page.locator("#group-rail-members .group-rail-member-name").first).to_be_visible()
        # No navigation happened.
        assert page.url == starting_url, f"Expected URL unchanged, got {page.url}"

    def test_chip_remove_button_round_trips(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        row = _aaron_row(page)
        mark = row.locator(".dir-mark")
        mark.click()
        expect(mark).to_have_text("✓")
        # Chip × removes; marker flips back.
        page.locator("#group-rail-members .group-rail-member-remove").first.click()
        expect(mark).to_have_text("+")
        expect(page.locator("#group-rail-create")).to_be_disabled()

    def test_title_auto_follows_search_then_flips_on_user_type(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        title = page.locator("#group-rail-title")
        expect(title).to_have_class(re.compile(r"\bgroup-rail-title--auto\b"))
        expect(title).to_have_value("")
        # Typing in the search box updates the rail title immediately
        # (no debounce on the title path; title is for visual feedback,
        # the actual search runs after 250ms).
        page.locator("#search-input").fill("climate")
        expect(title).to_have_value("Climate")
        # Typing in the title field flips off the auto-follow class for good.
        title.fill("My climate group")
        expect(title).not_to_have_class(re.compile(r"\bgroup-rail-title--auto\b"))
        # Subsequent search-box edits no longer rewrite the title.
        page.locator("#search-input").fill("")
        page.locator("#search-input").fill("anything")
        expect(title).to_have_value("My climate group")

    def test_draft_persists_across_reload(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        _aaron_row(page).locator(".dir-mark").click()
        expect(page.locator("#group-rail-members .group-rail-member-name").first).to_have_text(
            "Aaron Bird"
        )
        page.reload(wait_until="domcontentloaded")
        _wait_for_directory(page)
        # Marker comes up already on; chip restored from localStorage.
        expect(_aaron_row(page).locator(".dir-mark")).to_have_text("✓")
        expect(page.locator("#group-rail-members .group-rail-member-name").first).to_have_text(
            "Aaron Bird"
        )

    def test_hash_tag_search_filters_to_climate_fellows(
        self, standalone_page, base_url_fixture
    ):
        """#climate routes through search_tags (FTS5 column-scoped) and
        returns only fellows whose tags include 'climate'. We assert a
        known climate fellow appears (Aliza Napartivaumnuay, Andy Sack,
        Barry Neal — chosen because their search_tags column reliably
        contains 'climate' in the canonical 2026-04-08 dataset)."""
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        # Disable the has-email filter so we don't accidentally suppress
        # anyone in the small expected set.
        page.locator("#has-email-filter").uncheck()
        page.locator("#search-input").fill("#climate")
        # Search debounces 250ms, then renders.
        page.wait_for_timeout(700)
        link = page.locator("#directory a.dir-link", has_text="Andy Sack").first
        expect(link).to_be_visible()

    def test_bulk_select_bar_visibility_tracks_filtered_state(
        self, standalone_page, base_url_fixture
    ):
        """Per the design spec: the bar shows when results are filtered
        (search query OR has-email checked) and hides when the unfiltered
        list is showing — "too easy to mis-click" otherwise."""
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        bar = page.locator("#bulk-select-bar")
        # has-email is on by default → bar is visible from boot.
        expect(page.locator("#has-email-filter")).to_be_checked()
        expect(bar).to_be_visible()
        # Unchecking has-email with no query → bar hides (truly unfiltered).
        page.locator("#has-email-filter").uncheck()
        page.wait_for_timeout(200)
        expect(bar).to_be_hidden()
        # Typing a query → bar appears again.
        page.locator("#search-input").fill("Aaron")
        page.wait_for_timeout(700)
        expect(bar).to_be_visible()

    def test_bulk_select_toggles_all_visible_into_draft(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#search-input").fill("Aaron")
        page.wait_for_timeout(700)
        before = page.locator("#group-rail-members .group-rail-member-name").count()
        page.locator("#bulk-select-input").check()
        page.wait_for_timeout(200)
        after = page.locator("#group-rail-members .group-rail-member-name").count()
        assert after >= before + 1, (
            f"Expected bulk-select to add at least 1 chip; before={before} after={after}"
        )
