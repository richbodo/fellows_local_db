"""E2E: the About-page Fellowship Statistics layout.

Issue #132: the SVG-based stats charts shrank in both dimensions when
the column was narrow (viewBox aspect-ratio scaling), and the inner
2-column grid halved the available width on every viewport. The
replacement renders semantic HTML bars at full pane width, with
Field Completeness opting into a 2-column wrap above 1100px.

These tests pin the new structure: four sections render as
.stats-section nodes, each row is a .stats-bar-row with a fill width
proportional to count/maxCount, and the multicol rule is active at
desktop width but inactive below 1100px.
"""
from __future__ import annotations

from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


def _make_standalone_page(context):
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    return page


def _boot_then_open_about(page, base_url):
    """Boot to the directory FIRST, wait for boot to settle, THEN open
    About via hash. This avoids a race where boot's two route() calls
    (after getList, then again after getFull) each wipe and re-render
    the about grid asynchronously — so the test can land on a partially
    rendered grid mid-refresh.
    """
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    page.wait_for_function(
        "() => window.__bootMarks && window.__bootMarks.get_full_done != null",
        timeout=15000,
    )
    page.evaluate("location.hash = '#/about'")
    _wait_for_stats(page)


def _wait_for_stats(page):
    """Stats render async after dataProvider.getStats() resolves AND
    the total count line shows the resolved value. Waiting for the
    total text + a stable bar-row count across 4 sections gives a
    deterministic anchor — the .stats-section selector firing alone
    is racy mid-render."""
    page.wait_for_function(
        """
        () => {
          const total = document.getElementById('stats-total');
          if (!total || !/Total Fellows:\\s*\\d+/.test(total.textContent || '')) {
            return false;
          }
          const sections = document.querySelectorAll(
            '.stats-grid .stats-section'
          );
          if (sections.length !== 4) return false;
          for (const s of sections) {
            if (s.querySelectorAll('.stats-bar-row').length === 0) {
              return false;
            }
          }
          return true;
        }
        """,
        timeout=15000,
    )


class TestAboutStatsLayout:
    def test_four_sections_render_as_html_not_svg(self, context, base_url_fixture):
        """All four sections (Type, Cohort, Region, Field Completeness)
        render as .stats-section nodes containing .stats-bar-row entries.
        The old SVG renderer is gone: there should be no .stats-chart in
        the DOM."""
        page = _make_standalone_page(context)
        try:
            _boot_then_open_about(page, base_url_fixture)

            sections = page.locator(".stats-grid .stats-section")
            expect(sections).to_have_count(4)

            # Title text confirms which section is which.
            titles = sections.locator(".stats-section-title").all_inner_texts()
            assert titles == [
                "Fellows by Type",
                "Fellows by Cohort",
                "Fellows by Region",
                "Field Completeness",
            ], f"unexpected section order or titles: {titles}"

            # Every section has at least one bar row.
            for i in range(4):
                rows = sections.nth(i).locator(".stats-bar-row")
                assert rows.count() >= 1, (
                    f"section {titles[i]} has zero bar rows"
                )

            # The SVG renderer is fully retired.
            assert page.locator(".stats-chart").count() == 0
            assert page.locator(".stats-grid svg").count() == 0
        finally:
            page.close()

    def test_bar_widths_match_count_proportions(self, context, base_url_fixture):
        """The inline style.width on each .stats-bar-fill is set to
        (count / maxCount) * 100. Read the data the page rendered against
        and verify the widths line up — within 0.15% to absorb the
        toFixed(1) rounding."""
        page = _make_standalone_page(context)
        try:
            _boot_then_open_about(page, base_url_fixture)

            # Pull (label, count, rendered_pct) tuples for the first section.
            # The first section is "Fellows by Type" — small, predictable.
            rows = page.locator(
                ".stats-grid .stats-section:first-child .stats-bar-row"
            )
            n = rows.count()
            assert n >= 1

            labels = []
            counts = []
            rendered_widths = []
            for i in range(n):
                row = rows.nth(i)
                labels.append(row.locator(".stats-bar-label").inner_text())
                counts.append(int(row.locator(".stats-bar-count").inner_text()))
                style = row.locator(".stats-bar-fill").get_attribute("style") or ""
                # Parse "width: NN.N%"
                assert "width:" in style, f"row {i} fill missing width style: {style!r}"
                w = float(style.split("width:")[1].split("%")[0].strip())
                rendered_widths.append(w)

            # First row sets the scale (it's the largest by count, since the
            # API returns sections sorted DESC by count).
            max_count = counts[0]
            assert max_count > 0, f"first row should have nonzero count: {counts}"
            for i in range(n):
                expected_pct = (counts[i] / max_count) * 100
                assert abs(rendered_widths[i] - expected_pct) < 0.15, (
                    f"row {i} ({labels[i]}, count={counts[i]}): rendered "
                    f"{rendered_widths[i]}% vs expected {expected_pct}%"
                )
        finally:
            page.close()

    def test_field_completeness_multicol_at_desktop_width(
        self, context, base_url_fixture
    ):
        """Field Completeness opts into 2-column wrap above 1100px via the
        .stats-section--multicol class. At ≥1100px the inner ol applies
        column-count: 2; at narrower widths it stays single-column."""
        page = _make_standalone_page(context)
        try:
            page.set_viewport_size({"width": 1400, "height": 900})
            _boot_then_open_about(page, base_url_fixture)

            fc = page.locator(".stats-section--multicol")
            expect(fc).to_have_count(1)
            expect(fc.locator(".stats-section-title")).to_have_text(
                "Field Completeness"
            )

            # At desktop width, the bars list inherits 2-column layout from
            # the @media (min-width: 1100px) rule.
            col_count_desktop = fc.locator(".stats-bars").evaluate(
                "el => getComputedStyle(el).columnCount"
            )
            assert col_count_desktop == "2", (
                f"expected column-count:2 at 1400px viewport; got {col_count_desktop!r}"
            )
        finally:
            page.close()

    def test_field_completeness_single_column_below_breakpoint(
        self, context, base_url_fixture
    ):
        """Below 1100px the multicol rule does not apply — narrow viewports
        are read top-to-bottom in a single column."""
        page = _make_standalone_page(context)
        try:
            page.set_viewport_size({"width": 900, "height": 900})
            _boot_then_open_about(page, base_url_fixture)

            fc = page.locator(".stats-section--multicol")
            col_count_narrow = fc.locator(".stats-bars").evaluate(
                "el => getComputedStyle(el).columnCount"
            )
            # CSS default for an element with no column-count is 'auto'.
            assert col_count_narrow != "2", (
                f"multicol should NOT apply at 900px viewport; got "
                f"column-count={col_count_narrow!r}"
            )
        finally:
            page.close()
