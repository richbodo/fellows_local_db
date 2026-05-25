"""Mobile e2e fixtures: parametrized device matrix.

Runs each test against three viewport profiles:

  * Pixel 5      — Playwright's stock Android Chrome descriptor (393x851 @ DPR 2.75).
  * iPhone 13    — Playwright's stock iOS Safari descriptor (390x844 @ DPR 3).
                   Note: Playwright drives Chromium under iOS-shaped UA + viewport.
                   That catches layout bugs but NOT real WebKit/Safari engine bugs.
  * narrow-360   — custom worst-case width (360x720 @ DPR 2). The screen the
                   user reported overlap on was a similar-width Android.

Phase 4 (real-device + BrowserStack) covers the engine-specific gap.

Two fixtures here:

  * mobile_page          — read-only / snapshot-only. PWA standalone is faked
                           so the directory renders; no other shims. Used by
                           the screenshot smoke tests.
  * mobile_interaction_page — full-shim mobile page for interaction testing.
                           Adds the showSaveFilePicker delete that the desktop
                           conftest does (avoids download-dialog hangs) so the
                           same e2e patterns desktop tests use work at mobile
                           viewport.

The interaction fixture pairs with mobile_worker_data (below) to drive
window.__dataProvider RPCs for test setup (groups, settings), mirroring the
desktop worker_data pattern.
"""
from __future__ import annotations

import pytest

# Built-in Playwright device descriptors we use as-is. See
# https://playwright.dev/python/docs/emulation#devices
_BUILTIN_DEVICES = ("Pixel 5", "iPhone 13")

# Custom narrow-360 profile, mimicking a small Android (Galaxy A-series, etc.).
_NARROW_360 = {
    "viewport": {"width": 360, "height": 720},
    "device_scale_factor": 2.0,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (Linux; Android 11; Pixel 4) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
    ),
}


# Standalone shim only — matches what mobile_page has always done. The
# snapshot suite is read-only and doesn't need the showSaveFilePicker
# delete (no downloads). Interaction tests use the richer shim below.
_STANDALONE_DISPLAY_INIT = """
(function () {
  var orig = window.matchMedia.bind(window);
  window.matchMedia = function (q) {
    q = String(q);
    if (q.indexOf('display-mode: standalone') !== -1) {
      return {
        matches: true,
        media: q,
        addEventListener: function () {},
        removeEventListener: function () {}
      };
    }
    return orig(q);
  };
})();
"""

# Interaction-fixture shim: same standalone fake PLUS the showSaveFilePicker
# delete from the desktop conftest. The picker fires a native OS save
# dialog that Playwright's page.expect_download doesn't see, hanging any
# test that exports / downloads. Removing it forces the anchor-download
# fallback, which Playwright catches reliably.
_INTERACTION_INIT = """
(function () {
  var orig = window.matchMedia.bind(window);
  window.matchMedia = function (q) {
    q = String(q);
    if (q.indexOf('display-mode: standalone') !== -1) {
      return {
        matches: true,
        media: q,
        addEventListener: function () {},
        removeEventListener: function () {}
      };
    }
    return orig(q);
  };
  try { delete window.showSaveFilePicker; } catch (e) {
    try { window.showSaveFilePicker = undefined; } catch (e2) {}
  }
})();
"""


def _device_kwargs(playwright, name: str) -> dict:
    if name == "narrow-360":
        return dict(_NARROW_360)
    return dict(playwright.devices[name])


@pytest.fixture(params=list(_BUILTIN_DEVICES) + ["narrow-360"])
def device_name(request) -> str:
    """Parametrize tests across the mobile device matrix."""
    return request.param


@pytest.fixture
def mobile_page(playwright, browser, device_name):
    """Mobile-emulated Playwright page with PWA standalone shim installed."""
    context = browser.new_context(**_device_kwargs(playwright, device_name))
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    try:
        yield page
    finally:
        context.close()


@pytest.fixture
def mobile_interaction_page(playwright, browser, device_name):
    """Mobile page configured for full interaction testing.

    Same device matrix as mobile_page but the init script also removes
    window.showSaveFilePicker so tests that trigger downloads (settings
    backup, group export) don't hang on the native save dialog.
    """
    context = browser.new_context(**_device_kwargs(playwright, device_name))
    page = context.new_page()
    page.add_init_script(_INTERACTION_INIT)
    try:
        yield page
    finally:
        context.close()


@pytest.fixture
def mobile_worker_data(mobile_interaction_page, base_url_fixture):
    """WorkerDataHelper bound to the mobile-emulated page.

    Mirrors the desktop worker_data fixture: navigate to /, wait for
    window.__dataProvider, wipe relationships state on entry + exit so
    tests are order-independent. Use this fixture for tests that need
    groups / settings pre-seeded (or need to assert post-state).
    """
    from tests.e2e.conftest import make_worker_data
    helper = make_worker_data(mobile_interaction_page, base_url_fixture)
    helper.wipe_relationships()
    try:
        yield helper
    finally:
        try:
            helper.wipe_relationships()
        except Exception:
            pass
