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

    def test_bars_aligned_across_sections_at_desktop(
        self, context, base_url_fixture
    ):
        """User feedback (post-#132): the conventional bar-chart shape
        wants every bar to start at the same x. Pre-fix the label
        column auto-sized per-section, so the Region section's bars
        started further right than Type's. The fixed-label-column rule
        should pin every single-column section to the same starting x.

        We exclude the multicol section (Field Completeness) because
        its rows live inside CSS columns whose offset depends on which
        column they're in — alignment within each multicol-column is
        what matters there, and is covered by visual review."""
        page = _make_standalone_page(context)
        try:
            page.set_viewport_size({"width": 1400, "height": 900})
            _boot_then_open_about(page, base_url_fixture)

            # Sample the leftmost x of the bar track in the first row of
            # each non-multicol section. They must all match to within
            # 1px (subpixel rounding).
            xs = page.evaluate(
                """
                () => {
                  const out = [];
                  const sections = document.querySelectorAll(
                    '.stats-grid .stats-section:not(.stats-section--multicol)'
                  );
                  for (const s of sections) {
                    const track = s.querySelector(
                      '.stats-bar-row:first-child .stats-bar-track'
                    );
                    if (track) {
                      out.push({
                        title: s.querySelector('.stats-section-title').textContent,
                        x: track.getBoundingClientRect().left,
                      });
                    }
                  }
                  return out;
                }
                """
            )
            assert len(xs) >= 3, f"expected ≥3 single-col sections; got {xs}"
            base_x = xs[0]["x"]
            for entry in xs[1:]:
                assert abs(entry["x"] - base_x) < 1.5, (
                    f"bars should align across sections; "
                    f"{entry['title']!r} starts at {entry['x']:.1f}, "
                    f"baseline {xs[0]['title']!r} at {base_x:.1f}"
                )
        finally:
            page.close()

    def test_count_renders_inside_label_text_block(
        self, context, base_url_fixture
    ):
        """User feedback: count moves to sit next to the label so it's
        readable on mobile when the bar overflows the viewport. The
        count must live inside .stats-bar-text (alongside the label),
        NOT after the bar track."""
        page = _make_standalone_page(context)
        try:
            _boot_then_open_about(page, base_url_fixture)

            row = page.locator(".stats-grid .stats-bar-row").first
            # Count is inside the text block.
            count_in_text = row.locator(".stats-bar-text > .stats-bar-count")
            expect(count_in_text).to_have_count(1)
            # No stray count outside the text block (e.g. after the track).
            stray = row.locator(":scope > .stats-bar-count")
            assert stray.count() == 0, (
                "count should not be a direct child of .stats-bar-row; "
                "it must nest inside .stats-bar-text"
            )

            # Count text matches the resolved value (without parens —
            # those come from CSS ::before/::after).
            count_text = count_in_text.inner_text()
            assert count_text.strip().isdigit(), (
                f"count should be a bare number (parens come from CSS); "
                f"got {count_text!r}"
            )
        finally:
            page.close()

    def test_mobile_keeps_full_label_visible(self, context, base_url_fixture):
        """User feedback: on mobile we drop bar alignment in favor of
        full label readability. At ≤700px viewport, labels must NOT be
        ellipsized — the user wants 'International Entrepreneur (288)'
        in full even if the bar overflows the viewport.

        We assert by computing the rendered label width and comparing
        against scrollWidth: if scrollWidth > clientWidth, the label is
        being clipped."""
        page = _make_standalone_page(context)
        try:
            page.set_viewport_size({"width": 360, "height": 800})
            _boot_then_open_about(page, base_url_fixture)

            # Pick the longest label across all sections — likely
            # "East & Central Asia (includes China)" in Region — and
            # assert it's not clipped at 360px viewport.
            clipped = page.evaluate(
                """
                () => {
                  const labels = document.querySelectorAll(
                    '.stats-grid .stats-bar-label'
                  );
                  const out = [];
                  for (const el of labels) {
                    if (el.scrollWidth > el.clientWidth + 1) {
                      out.push({
                        text: el.textContent,
                        scroll: el.scrollWidth,
                        client: el.clientWidth,
                      });
                    }
                  }
                  return out;
                }
                """
            )
            assert clipped == [], (
                f"labels should not be ellipsized at 360px mobile viewport; "
                f"got {len(clipped)} clipped: {clipped[:3]}"
            )
        finally:
            page.close()
