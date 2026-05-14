"""E2E: bulk-select bar must reset when the search produces 0 results.

Reported symptom: on mobile, with the has-email filter on, search input
"Rich" rendered the body as "No fellows match that search." while the
bulk-select bar above it still said "select all 2 results" — the bar
kept stale text from an earlier render that had matches.

Root cause: renderSearchResults' empty-branch `return` skips the
trailing updateBulkBar() call (app/static/app.js:9090-9098). The bar
stays visible with whatever text it had after the previous non-empty
search. The fix is to update the bulk bar on every render, including
the empty branch (so it hides itself when displayedList is empty).
"""
import pytest
from playwright.sync_api import expect


class TestBulkBarStaleOnEmptySearch:
    """renderSearchResults must call updateBulkBar in every code path."""

    def test_bulk_bar_hides_after_query_changes_to_zero_results(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)

        bulk_bar = page.locator("#bulk-select-bar")
        bulk_text = page.locator("#bulk-select-text")
        list_el = page.locator("#directory-list")

        # First query: "Aaron" hits Aaron Bird + Aaron McDonald via FTS5.
        # That populates displayedList with two fellows, so updateBulkBar
        # makes the bar visible with "select all 2 results".
        page.locator("#search-input").fill("Aaron")
        page.wait_for_timeout(500)  # debounce 250 ms + chain settle
        expect(list_el).to_contain_text("Aaron Bird")
        expect(bulk_bar).to_be_visible()
        expect(bulk_text).to_contain_text("2 results")

        # Second query: nonsense token with no FTS5 hits. renderSearchResults
        # enters the empty branch, sets displayedList = [], renders
        # "No fellows match that search." — and must also hide the bulk bar.
        page.locator("#search-input").fill("zzzzzzzz_no_match")
        page.wait_for_timeout(500)
        expect(list_el).to_contain_text("No fellows match that search")
        # Pre-fix: bar still visible with stale "2 results" text.
        # Post-fix: bar hidden because displayedList.length === 0.
        expect(bulk_bar).to_be_hidden()
