"""E2E: focus mode hides the directory list and composer rail on
About / Settings at every viewport width.

Issue #121: at desktop widths (>1024px) the About and Settings pages
rendered with the directory list on the left and the composer rail on
the right, squeezing the page content into an unreadable middle column.
The mobile-redesign focus-mode rule existed only inside @media
(max-width: 1024px); the desktop side had no equivalent for these two
routes.

The fix is intentionally narrow: only About and Settings get focus mode
at desktop. Fellow detail and group pages keep the rails visible
because their workflow includes scanning the directory list while
reading (covered by test_click_another_fellow_updates_detail in
tests/e2e/test_detail_view.py).

These tests pin the route-class → focus-mode mapping at desktop widths.
The default Playwright viewport (1280x720) is already desktop. The
mobile-redesign tests in tests/e2e/mobile/ cover the narrow side.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect


class TestDesktopFocusMode:
    """At desktop widths, only the directory route (and edit mode) shows
    #directory and #group-rail. About / Settings / Fellow detail / Group
    pages are full-width.
    """

    def test_directory_route_keeps_directory_and_rail_visible(
        self, page, base_url_fixture
    ):
        """Sanity: the default route is the one place focus mode does NOT
        apply. Without this assertion we can't tell whether a "rails are
        hidden everywhere" test is actually catching a regression that
        broke the directory page itself.
        """
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)

        # The directory is the default route — #directory must render.
        expect(page.locator("#directory")).to_be_visible()
        # The rail (composer) is also visible on the directory route.
        expect(page.locator("#group-rail")).to_be_visible()
        # Body class confirms route classification.
        body_classes = page.evaluate("document.body.className")
        assert "route-directory" in body_classes, body_classes

    @pytest.mark.parametrize(
        "hash_route,expected_class",
        [
            ("#/about", "route-about"),
            ("#/settings", "route-settings"),
        ],
    )
    def test_about_and_settings_hide_directory_and_rail(
        self, page, base_url_fixture, hash_route, expected_class
    ):
        """The user-reported regression in #121: at desktop widths, About
        and Settings rendered the directory list + composer rail in side
        columns, squeezing the central page content. Both must be hidden
        on these routes regardless of viewport width.
        """
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)

        # Navigate via hash; route() picks up the class.
        page.evaluate(f"location.hash = '{hash_route}'")
        # Wait for the body class to flip.
        page.wait_for_function(
            f"() => document.body.classList.contains('{expected_class}')",
            timeout=3000,
        )

        # The load-bearing assertion: #directory and #group-rail must
        # be display: none. Playwright's to_be_hidden is the right
        # idiom for "rendered absent or display:none".
        expect(page.locator("#directory")).to_be_hidden()
        expect(page.locator("#group-rail")).to_be_hidden()
