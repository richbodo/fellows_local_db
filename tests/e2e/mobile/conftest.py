"""Mobile e2e fixtures: parametrized device matrix.

Runs each test against three viewport profiles:

  * Pixel 5      — Playwright's stock Android Chrome descriptor (393x851 @ DPR 2.75).
  * iPhone 13    — Playwright's stock iOS Safari descriptor (390x844 @ DPR 3).
                   Note: Playwright drives Chromium under iOS-shaped UA + viewport.
                   That catches layout bugs but NOT real WebKit/Safari engine bugs.
  * narrow-360   — custom worst-case width (360x720 @ DPR 2). The screen the
                   user reported overlap on was a similar-width Android.

Phase 4 (real-device + BrowserStack) covers the engine-specific gap.
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


# The app gates the directory behind PWA standalone mode for non-installed
# browsers. Mobile screenshots want the directory, not the install landing.
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
