"""Layout audits at mobile viewports.

Structural checks that catch a class of "can't use this on a phone"
bugs without relying on pixel comparison or interaction. Each test
runs across the device matrix (Pixel 5 / iPhone 13 / narrow-360) and
each static route in turn.

These tests are designed to fail loudly when the mobile layout has
known-bad geometry — that's the point of the discovery PR (#179
follow-up). Failures here become the bug surface to fix; once green,
the tests act as regression guards.

Three audits:

  1. No horizontal overflow (the page doesn't scroll sideways).
  2. Touch targets meet the iOS HIG 44x44 minimum.
  3. No fixed / sticky element anchored at the bottom consumes more
     than 40% of the viewport height.

Plus one route-specific test for the directory route's content area
visibility (catches the "names rail squeezed to a sliver by the
bottom bar" bug reported in the issue thread).
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect


# Static routes covered by the audits. Group-scoped routes need
# mobile_worker_data setup and are exercised in test_mobile_interactions.py.
STATIC_ROUTES = [
    ("#/", "directory"),
    ("#/about", "about"),
    ("#/settings", "settings"),
    ("#/groups", "groups-index"),
    ("#/fellow/aaron_bird", "fellow-detail"),
]


def _wait_for_app_boot(page, timeout: int = 10000) -> None:
    """Wait for the loader to vanish + a brief settle for late layout shifts."""
    page.locator("#loading").wait_for(state="hidden", timeout=timeout)
    page.wait_for_timeout(400)


@pytest.mark.parametrize("hash_route,label", STATIC_ROUTES)
def test_no_horizontal_overflow(
    mobile_page, device_name, base_url_fixture, hash_route, label
):
    """Page must not scroll sideways at mobile viewports.

    `document.documentElement.scrollWidth > clientWidth` means content
    overflows the viewport horizontally — content runs off the right edge
    and the user can swipe sideways to find it. That's a layout bug
    that bites on every mobile width. +1px tolerance absorbs rounding.
    """
    page = mobile_page
    page.goto(base_url_fixture + "/" + hash_route, wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    metrics = page.evaluate(
        """
        () => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          innerWidth: window.innerWidth,
        })
        """
    )
    assert metrics["scrollWidth"] <= metrics["clientWidth"] + 1, (
        f"horizontal overflow on {label} at {device_name}: "
        f"scrollWidth={metrics['scrollWidth']}, clientWidth={metrics['clientWidth']}, "
        f"innerWidth={metrics['innerWidth']}"
    )


@pytest.mark.parametrize("hash_route,label", STATIC_ROUTES)
def test_touch_targets_meet_minimum_size(
    mobile_page, device_name, base_url_fixture, hash_route, label
):
    """Standalone interactive controls must be at least 44x44 (iOS HIG).

    Walks the DOM for buttons, form controls, and classed action
    links; asserts each visible one meets the bounding-box minimum.
    Failure message is the full list of sub-44 elements as JSON — so
    the test output itself is the fix list.

    Skipped:
      - Hidden elements (display/visibility/opacity, .hidden class,
        aria-hidden=true, zero size).
      - Bare <a> elements inside text-flow containers (<p>, <li>,
        <summary>, <th>, <td> within <table>) — the iOS HIG 44x44
        floor explicitly applies to standalone controls, not inline
        text links within prose. A link in a body paragraph gets
        enough vertical hit area from line-height and surrounding
        whitespace.
      - <a> without href (decorative).
    """
    page = mobile_page
    page.goto(base_url_fixture + "/" + hash_route, wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    findings = page.evaluate(
        r"""
        () => {
          const TEXT_FLOW_PARENTS = new Set([
            'P', 'LI', 'SUMMARY', 'TH', 'TD',
          ]);
          const sel = [
            'button',
            'a[href]',
            '[role=button]',
            'input[type=button]',
            'input[type=submit]',
            'input[type=checkbox]',
            'input[type=radio]',
            'summary',
          ].join(', ');
          const small = [];
          document.querySelectorAll(sel).forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return;
            const styles = getComputedStyle(el);
            if (styles.display === 'none' || styles.visibility === 'hidden') return;
            if (parseFloat(styles.opacity) === 0) return;
            if (el.getAttribute('aria-hidden') === 'true') return;
            if (el.classList.contains('hidden')) return;
            // Bare <a> inside text-flow containers — not a standalone
            // control per HIG. Walk up to the nearest block-level
            // ancestor; if it's a text-flow tag and this <a> has no
            // class of its own, skip.
            if (el.tagName === 'A' && !el.className) {
              let p = el.parentElement;
              while (p && p !== document.body) {
                if (TEXT_FLOW_PARENTS.has(p.tagName)) {
                  return;  // skipped: inline text link
                }
                const pcs = getComputedStyle(p);
                if (pcs.display.indexOf('block') === 0
                    || pcs.display.indexOf('flex') === 0
                    || pcs.display.indexOf('grid') === 0) {
                  break;  // hit a non-text-flow block-level ancestor
                }
                p = p.parentElement;
              }
            }
            if (r.width < 44 || r.height < 44) {
              small.push({
                tag: el.tagName,
                id: el.id || null,
                cls: el.className || null,
                text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
                w: Math.round(r.width),
                h: Math.round(r.height),
              });
            }
          });
          return small;
        }
        """
    )
    assert findings == [], (
        f"sub-44 touch targets on {label} at {device_name} "
        f"({len(findings)} elements):\n" + json.dumps(findings, indent=2)
    )


@pytest.mark.parametrize("hash_route,label", STATIC_ROUTES)
def test_no_fixed_element_dominates_viewport(
    mobile_page, device_name, base_url_fixture, hash_route, label
):
    """No fixed/sticky element anchored at the bottom should take more
    than 40% of the viewport height.

    Geometric signature of the "bottom bar takes half the screen" bug:
    fixed or sticky positioning, height > 40% of vh, bottom edge past
    50% of vh. Catches sheets that are permanently up when they
    shouldn't be (composer rail with broken translate, kebab sheet
    stuck open, group-detail action bar misconfigured).
    """
    page = mobile_page
    page.goto(base_url_fixture + "/" + hash_route, wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    findings = page.evaluate(
        """
        () => {
          const vh = window.innerHeight;
          const oversized = [];
          document.querySelectorAll('*').forEach(el => {
            const styles = getComputedStyle(el);
            if (styles.position !== 'fixed' && styles.position !== 'sticky') return;
            if (styles.display === 'none' || styles.visibility === 'hidden') return;
            if (parseFloat(styles.opacity) === 0) return;
            if (el.classList.contains('hidden')) return;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            if (r.bottom <= 0 || r.top >= vh) return;
            const heightPct = r.height / vh;
            const bottomPct = r.bottom / vh;
            if (heightPct > 0.4 && bottomPct > 0.5) {
              oversized.push({
                tag: el.tagName,
                id: el.id || null,
                cls: el.className || null,
                position: styles.position,
                h: Math.round(r.height),
                heightPctOfVh: Math.round(heightPct * 100),
                top: Math.round(r.top),
                bottom: Math.round(r.bottom),
              });
            }
          });
          return oversized;
        }
        """
    )
    assert findings == [], (
        f"oversized bottom-anchored element on {label} at {device_name}:\n"
        + json.dumps(findings, indent=2)
    )


def test_scroll_container_shell_keeps_appbar_fixed(
    mobile_page, device_name, base_url_fixture
):
    """The is-phone scroll-container shell (PR6/mobile-PR1): the page
    itself does not scroll — the directory list is the only scroller, and
    the appbar stays pinned to the top while the list scrolls underneath.

    This is the headline "frozen list" fix. Before the shell, the whole
    document scrolled and the appbar/search header scrolled away with it.
    The structural contract:

      1. body.is-phone is set (UA-driven layout gate) and the page body
         does not overflow vertically (overflow:hidden, fixed height).
      2. #directory has its own vertical scroll with overflowing content.
      3. Scrolling #directory does NOT move the document (documentElement
         scrollTop stays 0) and the appbar stays at viewport top.
    """
    page = mobile_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)

    assert page.evaluate("() => document.body.classList.contains('is-phone')"), (
        f"body.is-phone not set at {device_name} — the scroll shell is keyed on it"
    )

    before = page.evaluate(
        """
        () => {
          const d = document.getElementById('directory');
          const bar = document.querySelector('.appbar');
          return {
            bodyOverflowY: getComputedStyle(document.body).overflowY,
            dirOverflowY: getComputedStyle(d).overflowY,
            dirScrollable: d.scrollHeight - d.clientHeight,
            docScrollable: document.documentElement.scrollHeight
                           - document.documentElement.clientHeight,
            appbarTop: bar ? Math.round(bar.getBoundingClientRect().top) : null,
          };
        }
        """
    )
    assert before["bodyOverflowY"] == "hidden", (
        f"body should not scroll at {device_name}; overflowY={before['bodyOverflowY']}"
    )
    assert before["dirOverflowY"] in ("auto", "scroll"), (
        f"#directory should be the scroller at {device_name}; "
        f"overflowY={before['dirOverflowY']}"
    )
    assert before["dirScrollable"] > 0, (
        f"#directory has no overflowing content to scroll at {device_name} "
        f"(scrollHeight-clientHeight={before['dirScrollable']})"
    )
    assert before["appbarTop"] == 0, (
        f"appbar not pinned to top at {device_name}; top={before['appbarTop']}"
    )

    after = page.evaluate(
        """
        () => {
          const d = document.getElementById('directory');
          const bar = document.querySelector('.appbar');
          d.scrollTop = 300;
          return {
            dirScrollTop: d.scrollTop,
            docScrollTop: document.documentElement.scrollTop,
            appbarTop: bar ? Math.round(bar.getBoundingClientRect().top) : null,
          };
        }
        """
    )
    assert after["dirScrollTop"] > 0, (
        f"#directory did not scroll at {device_name}"
    )
    assert after["docScrollTop"] == 0, (
        f"the document scrolled instead of the list at {device_name}; "
        f"documentElement.scrollTop={after['docScrollTop']}"
    )
    assert after["appbarTop"] == 0, (
        f"appbar moved when the list scrolled at {device_name}; "
        f"top={after['appbarTop']} (should stay 0)"
    )


def test_directory_route_has_visible_content(
    mobile_page, device_name, base_url_fixture
):
    """Directory route at mobile must show a usable list of fellows.

    Targets the reported bug: on mobile the directory page is broken —
    "only the left column with the names in the center" is visible, and
    "about half the screen is just the gray bar." That collapses to
    three structural claims this test checks:

      1. #directory is visible and renders > 0 fellow rows.
      2. #directory occupies at least 40% of the viewport height.
      3. The directory list's top is above 50% of the viewport (it
         isn't pushed off-screen by other chrome).

    Failure on any clause means the directory route's mobile layout is
    structurally broken.
    """
    page = mobile_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    expect(page.locator("#directory")).to_be_visible()
    rows = page.locator("#directory li.dir-row")
    row_count = rows.count()
    assert row_count > 0, (
        f"directory has no rendered fellow rows at {device_name}"
    )
    metrics = page.evaluate(
        """
        () => {
          const d = document.getElementById('directory');
          const r = d.getBoundingClientRect();
          return {
            height: Math.round(r.height),
            top: Math.round(r.top),
            bottom: Math.round(r.bottom),
            vh: window.innerHeight,
            heightPctOfVh: Math.round(r.height / window.innerHeight * 100),
            topPctOfVh: Math.round(r.top / window.innerHeight * 100),
          };
        }
        """
    )
    assert metrics["heightPctOfVh"] >= 40, (
        f"directory list squeezed at {device_name}: "
        f"{metrics['heightPctOfVh']}% of viewport "
        f"({metrics['height']}px of {metrics['vh']}px). "
        f"top={metrics['top']}, bottom={metrics['bottom']}"
    )
    assert metrics["topPctOfVh"] <= 50, (
        f"directory list pushed off-screen at {device_name}: "
        f"top is {metrics['topPctOfVh']}% down the viewport "
        f"({metrics['top']}px of {metrics['vh']}px)"
    )
