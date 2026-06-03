"""Mobile download routing: Android saves to Downloads, iOS uses the share sheet.

Regression guard for the Android "Couldn't load object" bug. `downloadBlob`
(app/static/app.js) used to route *every* mobile download through
`navigator.share()` whenever `navigator.canShare` accepted the file. On
Android the share sheet hands a `.db` (application/octet-stream) to Google
Drive, which can't render it — the user's data never lands locally. The fix
restricts the share-sheet branch to iOS (where `<a download>` is unreliable)
and lets Android fall through to the `<a download>` anchor, which saves
straight to the Downloads folder.

The phone download surface changed with the capability-gate rebuild (PR6):
the standalone "Download my private data" button is gone (phones are
browse-only). The remaining phone-reachable download is the backup offered
by Settings → Tools → Reset everything, which goes through the SAME
`downloadBlob` path — so the OS-routing guard rides on that flow here:

  * Android UA  → anchor download fires (`ehf-fellows-private-data-*.db`),
    share NOT called.
  * iOS UA      → `navigator.share` IS called, no anchor download.

`window.confirm` is stubbed to false so the destructive reset does NOT
proceed after the backup download fires (the download happens first; we
only care about its routing). Both UAs get a stubbed `navigator.canShare`
that returns true (matching real Android), so the test exercises the
OS-discrimination branch rather than relying on Chromium's headless
canShare being absent.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import _STANDALONE_DISPLAY_INIT, make_worker_data


# Standalone display shim (so the app boots to the directory) + the
# showSaveFilePicker delete (the desktop branch must not fire under a
# mobile UA, but deleting it is belt-and-suspenders) + a canShare that
# accepts everything + a navigator.share spy that records calls and
# resolves (so the iOS path completes without a real OS share sheet).
_SHARE_SPY_INIT = _STANDALONE_DISPLAY_INIT + """
(function () {
  try { delete window.showSaveFilePicker; } catch (e) {
    try { window.showSaveFilePicker = undefined; } catch (e2) {}
  }
  window.__shareCalls = 0;
  try {
    Object.defineProperty(navigator, 'canShare', {
      configurable: true, writable: true, value: function () { return true; }
    });
    Object.defineProperty(navigator, 'share', {
      configurable: true, writable: true,
      value: function () { window.__shareCalls += 1; return Promise.resolve(); }
    });
  } catch (e) { /* leave native impls in place */ }
})();
"""


def _reset_backup_prompt_page(playwright, browser, device, base_url):
    """Open a mobile-emulated page for `device`, seed a group, land on the
    reduced #/settings, and open the Reset-everything backup prompt (the
    phone-reachable download). Returns (context, page) — caller closes the
    context. window.confirm is stubbed false so the reset itself never
    proceeds past the backup download."""
    context = browser.new_context(**dict(playwright.devices[device]))
    page = context.new_page()
    page.add_init_script(_SHARE_SPY_INIT)
    helper = make_worker_data(page, base_url)
    if helper.wait() != "worker":
        context.close()
        pytest.skip("worker provider unavailable in this environment")
    helper.wipe_relationships()
    helper.create_group("download routing test")
    # Halt the destructive flow after the backup download fires.
    page.evaluate("() => { window.confirm = function () { return false; }; }")
    page.evaluate("() => { location.hash = '#/settings'; }")
    reset_btn = page.locator("#settings-phone-reset")
    reset_btn.wait_for(state="visible", timeout=10000)
    reset_btn.click()
    page.locator("#reset-backup-prompt").wait_for(state="visible", timeout=3000)
    return context, page


def test_android_backup_saves_to_downloads_without_share(playwright, browser, base_url_fixture):
    """Android: the .db backup downloads via the anchor; share is never called."""
    context, page = _reset_backup_prompt_page(playwright, browser, "Pixel 5", base_url_fixture)
    try:
        with page.expect_download(timeout=20000) as dl_info:
            page.locator("#reset-backup-download").click()
        download = dl_info.value
        assert download.suggested_filename.startswith("ehf-fellows-private-data-")
        assert download.suggested_filename.endswith(".db")
        # The whole point: the Android share-sheet → Drive dead-end is gone.
        assert page.evaluate("() => window.__shareCalls") == 0
    finally:
        context.close()


def test_ios_backup_uses_share_sheet(playwright, browser, base_url_fixture):
    """iOS: the share sheet is used (anchor download is unreliable there)."""
    context, page = _reset_backup_prompt_page(playwright, browser, "iPhone 13", base_url_fixture)
    try:
        page.locator("#reset-backup-download").click()
        # navigator.share is invoked on the iOS branch; no anchor download.
        page.wait_for_function("() => window.__shareCalls >= 1", timeout=10000)
        assert page.evaluate("() => window.__shareCalls") >= 1
    finally:
        context.close()
