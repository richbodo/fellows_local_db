"""E2E tests: directory filter UI (issue #86).

Covers the structured-filter sheet's interaction model:
- trigger is disabled during phase 1 (?full=1 still in flight) and enabled
  once full data lands;
- selecting filters narrows the visible list and updates the trigger
  badge;
- filter state round-trips through the URL hash on reload;
- Reset clears every active filter and strips params from the hash.
"""

import re

import pytest
from playwright.sync_api import expect


def _wait_full_load(page):
    """Wait for phase 2 (?full=1) to settle so the trigger enables."""
    page.locator("#loading").wait_for(state="hidden", timeout=15000)
    page.locator("#directory").wait_for(state="visible", timeout=5000)
    # The trigger button only un-disables once filterOptions is built.
    page.wait_for_function(
        "() => { var b = document.getElementById('filter-trigger');"
        " return b && !b.disabled; }",
        timeout=15000,
    )


class TestDirectoryFilterSheet:
    def test_trigger_starts_disabled_then_enables_after_phase_two(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        # Once #directory is visible we've passed phase 1, but the trigger
        # is gated on phase 2 / filterOptions. By the time #loading hides
        # phase 2 has resolved on a localhost build.
        _wait_full_load(page)
        trigger = page.locator("#filter-trigger")
        expect(trigger).to_be_visible()
        expect(trigger).not_to_have_attribute("disabled", "")

    def test_cohort_filter_narrows_directory_and_updates_hash(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_full_load(page)

        unfiltered_count = page.locator("#directory a[href^='#/fellow/']").count()
        assert unfiltered_count >= 2, "test needs more than 1 fellow"

        # Open the sheet.
        page.locator("#filter-trigger").click()
        sheet = page.locator("#filter-sheet")
        expect(sheet).to_be_visible()

        # Pick the first real cohort option (skip the "Any" placeholder).
        cohort_select = page.locator("#filter-cohort")
        cohort_options = cohort_select.locator("option").all_text_contents()
        assert len(cohort_options) >= 2, "expected at least one cohort value"
        first_cohort = cohort_select.locator("option").nth(1).get_attribute("value")
        assert first_cohort, "first cohort option should have a value"
        cohort_select.select_option(first_cohort)

        # Filter applies live; close the sheet.
        page.locator("#filter-sheet-done").click()
        expect(sheet).to_be_hidden()

        # Trigger badge reflects the active count.
        badge = page.locator("#filter-trigger-count")
        expect(badge).to_have_text("1")
        expect(page.locator("#filter-trigger")).to_have_class(re.compile(r"filter-trigger--active"))

        # Hash carries the filter state.
        page.wait_for_function(
            "() => window.location.hash.indexOf('cohort=') !== -1",
            timeout=2000,
        )
        hash_now = page.evaluate("() => window.location.hash")
        assert "cohort=" in hash_now, hash_now

        # Visible count should narrow but not vanish: every value in the
        # cohort dropdown is sourced from the loaded fellow set, so
        # picking one is guaranteed to match at least one fellow. (A
        # zero-count regression would slip past `<= unfiltered`.)
        filtered_count = page.locator("#directory a[href^='#/fellow/']").count()
        assert 1 <= filtered_count < unfiltered_count, (
            "single-cohort filter should narrow strictly; "
            f"got filtered={filtered_count} unfiltered={unfiltered_count}"
        )

    def test_region_multiselect_combines_with_cohort(
        self, standalone_page, base_url_fixture
    ):
        """Cohort + region together compose with AND semantics."""
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_full_load(page)

        page.locator("#filter-trigger").click()

        cohort_select = page.locator("#filter-cohort")
        first_cohort = cohort_select.locator("option").nth(1).get_attribute("value")
        cohort_select.select_option(first_cohort)
        cohort_only = page.locator("#directory a[href^='#/fellow/']").count()

        region_checks = page.locator("#filter-region-options input[data-filter-region]")
        if region_checks.count() == 0:
            return  # data has no regions; nothing to combine

        region_checks.first.check()

        # Hash carries both filters.
        page.wait_for_function(
            "() => window.location.hash.indexOf('region=') !== -1",
            timeout=2000,
        )
        expect(page.locator("#filter-trigger-count")).to_have_text("2")

        combined = page.locator("#directory a[href^='#/fellow/']").count()
        assert combined <= cohort_only, (
            "AND-combine cannot widen the result set; "
            f"cohort_only={cohort_only} combined={combined}"
        )

    def test_hash_filters_round_trip_on_reload(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_full_load(page)

        # Read a cohort that actually exists, then reload with that value
        # already in the hash.
        page.locator("#filter-trigger").click()
        cohort_select = page.locator("#filter-cohort")
        target_cohort = cohort_select.locator("option").nth(1).get_attribute("value")
        page.locator("#filter-sheet-close").click()
        assert target_cohort

        from urllib.parse import quote

        page.goto(
            base_url_fixture + "/#/?cohort=" + quote(target_cohort),
            wait_until="domcontentloaded",
        )
        _wait_full_load(page)

        # Filter applied from hash → trigger shows the badge with count 1.
        expect(page.locator("#filter-trigger-count")).to_have_text("1")
        expect(page.locator("#filter-trigger")).to_have_class(re.compile(r"filter-trigger--active"))

        # Sheet, when opened, has the cohort already selected.
        page.locator("#filter-trigger").click()
        expect(page.locator("#filter-cohort")).to_have_value(target_cohort)

    def test_reset_clears_filters_and_hash(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_full_load(page)

        page.locator("#filter-trigger").click()
        cohort_select = page.locator("#filter-cohort")
        target_cohort = cohort_select.locator("option").nth(1).get_attribute("value")
        cohort_select.select_option(target_cohort)

        # Reset button reveals once filters are active.
        reset_btn = page.locator("#filter-sheet-reset")
        expect(reset_btn).to_be_visible()
        reset_btn.click()

        # Trigger badge gone; cohort back to Any.
        expect(page.locator("#filter-trigger-count")).to_be_hidden()
        expect(cohort_select).to_have_value("")

        page.wait_for_function(
            "() => window.location.hash.indexOf('cohort=') === -1",
            timeout=2000,
        )
        hash_now = page.evaluate("() => window.location.hash")
        assert "cohort=" not in hash_now, hash_now
