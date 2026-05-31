"""Mobile gating of the durable data-folder feature.

The private data folder is deliberately NOT offered on phones / tablets:
Android's directory picker only reaches a Downloads subfolder the OS can
clear at will (so it can't keep the feature's durability promise) and iOS
has no picker at all. On mobile the app is OPFS-only, and the manual
backup download is the durability path. See docs/feature_platform_matrix.md
§ The mobile contract.

These tests pin the page-side gate (app.js: isMobileDevice /
folderStorageOffered) under a mobile UA:

  * folderStorageOffered() is false, even though the picker API is present
    (Chromium-under-iOS/Android-UA in Playwright) — proving the gate is a
    policy choice, not an API-absence accident.
  * The folder badge resolves to the 'unsupported' state with the
    phone-specific copy; the "Choose folder…" button stays hidden; the
    top-of-app folder-push banner never appears.
  * CRITICAL regression guard: the "Download my private data" button stays
    VISIBLE. It's the only durability path on mobile, and its un-hide was
    previously coupled to folder support — gating folder off must not take
    the backup button with it.

Note on the harness: Playwright emulates iOS/Android via UA + viewport but
the engine is Chromium, which ships showDirectoryPicker. That's why we can
assert pickerApiPresent is true while folderStorageOffered() is false — the
exact distinction the gate encodes.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import _STANDALONE_DISPLAY_INIT, make_worker_data


# Standalone shim (so the app boots straight to the directory) plus the
# showSaveFilePicker delete the other mobile interaction tests use, so a
# stray native save dialog can't hang anything.
_GATE_INIT = _STANDALONE_DISPLAY_INIT + """
(function () {
  try { delete window.showSaveFilePicker; } catch (e) {
    try { window.showSaveFilePicker = undefined; } catch (e2) {}
  }
})();
"""

# Pixel 5 = Android UA, iPhone 13 = iOS UA. Both must gate identically.
_MOBILE_DEVICES = ("Pixel 5", "iPhone 13")


def _seeded_settings_page(playwright, browser, device, base_url):
    """Open a mobile-emulated page, seed a group, land on #/settings.
    Returns (context, page); caller closes the context."""
    context = browser.new_context(**dict(playwright.devices[device]))
    page = context.new_page()
    page.add_init_script(_GATE_INIT)
    helper = make_worker_data(page, base_url)
    if helper.wait() != "worker":
        context.close()
        pytest.skip("worker provider unavailable in this environment")
    helper.wipe_relationships()
    helper.create_group("folder gate test")
    page.evaluate("() => { location.hash = '#/settings'; }")
    # The download button is the load-bearing element on mobile; wait for
    # the settings page to have rendered the folder section.
    page.locator("#settings-download-userdata").wait_for(state="visible", timeout=10000)
    return context, page


@pytest.mark.parametrize("device", _MOBILE_DEVICES)
def test_folder_storage_not_offered_but_api_present(playwright, browser, base_url_fixture, device):
    """The feature is gated off as policy, not because the API is missing."""
    context, page = _seeded_settings_page(playwright, browser, device, base_url_fixture)
    try:
        offered = page.evaluate("() => window.__folderController.folderStorageOffered()")
        assert offered is False, f"{device}: folder storage should not be offered on mobile"
        state = page.evaluate("() => window.__folderController.getState()")
        # getState() returns a Promise; evaluate awaits thenables automatically.
        assert state["supported"] is False, f"{device}: state.supported should be false on mobile"
        assert state["pickerApiPresent"] is True, (
            f"{device}: Chromium-under-mobile-UA exposes showDirectoryPicker; the gate "
            "is a policy choice, so pickerApiPresent must stay truthful"
        )
    finally:
        context.close()


@pytest.mark.parametrize("device", _MOBILE_DEVICES)
def test_folder_ui_hidden_with_phone_copy(playwright, browser, base_url_fixture, device):
    """Choose-folder button hidden, folder-push banner absent, badge shows
    the phone-specific message."""
    context, page = _seeded_settings_page(playwright, browser, device, base_url_fixture)
    try:
        expect(page.locator("#settings-folder-choose")).to_be_hidden()
        expect(page.locator("#folder-push-banner")).to_be_hidden()
        badge = page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge).to_contain_text("On phones", timeout=10000)
    finally:
        context.close()


@pytest.mark.parametrize("device", _MOBILE_DEVICES)
def test_download_button_stays_visible_on_mobile(playwright, browser, base_url_fixture, device):
    """Regression guard: gating folder off mobile must NOT hide the backup
    button — it's the only durability path on a phone."""
    context, page = _seeded_settings_page(playwright, browser, device, base_url_fixture)
    try:
        expect(page.locator("#settings-download-userdata")).to_be_visible()
    finally:
        context.close()
