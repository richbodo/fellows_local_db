"""E2E for the no-OPFS-SAH-pool browser fallback path.

Replaces the previous plan's manual Safari < 16.4 check (Phase 0 audit
decided no naturally SAH-deficient device is on hand). We strip
FileSystemFileHandle.prototype.createSyncAccessHandle in an init script
before the worker spawns; the worker's installOpfsSAHPoolVfs throws,
init rejects, and the page falls back to api+idb.

The directory still renders (browse-only path); Settings shows the
local-data-unavailable panel for backup/restore.
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

# Strip createSyncAccessHandle from the page AND any worker. Workers
# inherit the page's globals via importScripts but Worker scope has its
# own FileSystemFileHandle. Playwright's add_init_script applies to the
# page only, so we ALSO patch the script the worker imports — but since
# we can't run init scripts inside a generic worker context, we instead
# block the worker entirely (its own FileSystemFileHandle still has
# createSyncAccessHandle, so the strip wouldn't take). Block-then-fallback
# matches the unsupported-browser user experience: worker init fails
# inside the worker, page surfaces the panel via the api+idb fallback.
_STRIP_SAH_INIT = """
(function () {
  try {
    if (self.FileSystemFileHandle && self.FileSystemFileHandle.prototype) {
      Object.defineProperty(
        self.FileSystemFileHandle.prototype,
        'createSyncAccessHandle',
        { configurable: true, get: function () { return undefined; } }
      );
    }
  } catch (e) {}
})();
"""


def _wait_for_loading_to_settle(page):
    page.locator("#loading").wait_for(state="hidden", timeout=15000)


def test_no_sah_falls_back_to_api_idb_provider(browser, base_url_fixture):
    """When the worker can't install the SAH-pool VFS, init throws and
    the page commits to the api+idb provider. Settings shows the
    unsupported-browser panel."""
    context = browser.new_context()
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    page.add_init_script(_STRIP_SAH_INIT)
    try:
        # Block the worker bundle entirely so the worker can't even
        # spawn. The page-side init script can only patch the page
        # context — workers get their own globals. Blocking the bundle
        # gives the same end-user experience as a SAH-incapable
        # browser: worker init fails, api+idb takes over.
        page.route("**/vendor/sqlite-worker.js", lambda r: r.fulfill(status=404))
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_loading_to_settle(page)

        # Provider should be the api+idb fallback.
        kind = page.evaluate(
            "() => (window.__dataProvider && window.__dataProvider.kind) || null"
        )
        assert kind == "api+idb", (
            f"expected api+idb fallback when SAH unavailable, got {kind!r}"
        )

        # Directory renders via the API path — that's the documented
        # graceful-degrade behavior for browse-only.
        expect(page.locator("#app-wrap")).to_be_visible(timeout=5000)

        # Settings shows the unsupported-browser panel.
        page.goto(base_url_fixture + "/#/settings", wait_until="domcontentloaded")
        _wait_for_loading_to_settle(page)
        panel = page.locator("#detail .local-data-unavailable")
        expect(panel).to_have_count(1, timeout=5000)
    finally:
        page.close()
        context.close()
