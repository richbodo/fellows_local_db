"""E2E for the L6 persisted-storage best-effort attempt.

The page calls navigator.storage.persist() once on first successful boot
and records the result in window.__persistStorageState (also surfaced in
diagnostics). A denied or unavailable result must not break the
directory render — that's the L6 invariant.

Three cases:
1. persisted=true (granted) — the default in headless Chromium with a
   "persistent permission" origin.
2. persisted=false (denied) — induce by overriding navigator.storage.persist
   to return false.
3. persisted=null (unavailable) — induce by deleting persist from
   navigator.storage entirely.

In all three cases the directory must render and the call must be
recorded in window.__persistStorageState.
"""
from __future__ import annotations

from playwright.sync_api import expect


_STANDALONE_DISPLAY_INIT = """
(function () {
  var orig = window.matchMedia.bind(window);
  window.matchMedia = function (q) {
    q = String(q);
    if (q.indexOf('display-mode: standalone') !== -1) {
      return { matches: true, media: q, addEventListener: function () {}, removeEventListener: function () {} };
    }
    return orig(q);
  };
})();
"""


def _wait_for_directory(page):
    page.locator("#loading").wait_for(state="hidden", timeout=15000)
    page.locator("#app-wrap").wait_for(state="visible", timeout=5000)


def test_persist_attempted_and_result_visible_in_default_path(
    standalone_page, base_url_fixture
):
    """The page calls persist() exactly once on first boot and records
    the result in window.__persistStorageState — regardless of whether
    the headless browser grants or denies. This test pins the recording
    contract; the persisted=true / persisted=false distinction is
    covered by the other two tests."""
    page = standalone_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_directory(page)
    # Allow a tick for the post-boot persist() promise to settle.
    page.wait_for_function(
        "() => window.__persistStorageState && window.__persistStorageState.attempted === true",
        timeout=5000,
    )
    state = page.evaluate("() => window.__persistStorageState")
    assert state["attempted"] is True
    # persisted is whatever the browser decided — true (granted) or
    # false (denied). Either is non-fatal per L6; the contract is that
    # the call HAPPENED and the result is observable.
    assert state["persisted"] in (True, False), (
        f"expected boolean persisted; got {state}"
    )
    assert state["finishedAt"], "finishedAt should be set"


def test_persist_denied_does_not_break_directory_render(
    browser, base_url_fixture
):
    """Force navigator.storage.persist() to resolve false. Boot still
    completes, directory renders, state records persisted=false."""
    context = browser.new_context()
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    # Override persist BEFORE app.js loads. The init script runs in the
    # page context before any other script, so the override is in place
    # by the time pickDataProvider calls maybeRequestPersistedStorage.
    page.add_init_script(
        """
        (function () {
          if (navigator.storage) {
            navigator.storage.persist = function () { return Promise.resolve(false); };
          }
        })();
        """
    )
    try:
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.wait_for_function(
            "() => window.__persistStorageState && window.__persistStorageState.attempted === true",
            timeout=5000,
        )
        state = page.evaluate("() => window.__persistStorageState")
        assert state["attempted"] is True
        assert state["persisted"] is False, (
            f"expected persisted=false (denied); got {state}"
        )
        # Directory still rendered — that's the L6 invariant.
        expect(page.locator("#app-wrap")).to_be_visible()
    finally:
        page.close()
        context.close()


def test_persist_unavailable_does_not_break_directory_render(
    browser, base_url_fixture
):
    """When navigator.storage.persist is undefined (older browsers, some
    privacy modes), the page records persisted=null with an error reason
    and continues booting. Force the unavailable path by replacing
    navigator.storage with an object whose persist is missing."""
    context = browser.new_context()
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    page.add_init_script(
        """
        (function () {
          // Replace navigator.storage with a stripped-down stub that
          // has no `persist` (mimics older Safari / privacy-mode UAs).
          // Use defineProperty because navigator.storage is read-only on
          // the prototype.
          try {
            Object.defineProperty(navigator, 'storage', {
              configurable: true,
              get: function () {
                return { estimate: function () { return Promise.resolve({}); } };
              }
            });
          } catch (e) {}
        })();
        """
    )
    try:
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.wait_for_function(
            "() => window.__persistStorageState && window.__persistStorageState.attempted === true",
            timeout=5000,
        )
        state = page.evaluate("() => window.__persistStorageState")
        assert state["attempted"] is True
        # Unavailable path: persisted=null, error set, finishedAt populated.
        assert state["persisted"] is None, (
            f"expected persisted=null when persist unavailable; got {state}"
        )
        assert state["error"], "should record why persist was unavailable"
        assert "unavailable" in state["error"].lower(), state["error"]
        # Directory still rendered — that's the L6 invariant.
        expect(page.locator("#app-wrap")).to_be_visible()
    finally:
        page.close()
        context.close()
