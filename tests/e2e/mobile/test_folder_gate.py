"""Mobile gating of private data — phones are browse-only.

The private data capability gate (plans/private_data_capability_gate.md)
makes phones browse-only: groups, notes, tags, settings, and the durable
data-folder all have NO phone UI, because a PWA can't reliably preserve
private data off Chromium/FSA and a phone never attaches a verified folder.
Settings on a phone is reduced to app-info + tools.

These tests pin two things:

  * The folder controller's policy is intact: folderStorageOffered() is
    false on a phone even though Chromium-under-mobile-UA still exposes
    showDirectoryPicker (the gate is a policy choice, not an API-absence
    accident).
  * Phone Settings does NOT render the folder section or the
    "Download my private data" button.

NOTE (supersedes the prior mobile contract): an earlier step (PR #234)
kept a manual-backup download visible on phones as "the durability path."
The capability-gate rebuild removes group creation on phones entirely, so
there is no phone-authored private data to back up and the download is
gone. A user who created OPFS groups on a phone *before* this rebuild
keeps that data in OPFS but has no phone UI to reach or export it — see the
PR description.

Note on the harness: Playwright emulates iOS/Android via UA + viewport but
the engine is Chromium, which ships showDirectoryPicker. That's why
pickerApiPresent can be true while folderStorageOffered() is false — the
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


def _mobile_settings_page(playwright, browser, device, base_url):
    """Open a mobile-emulated page, land on #/settings (the reduced phone
    view). Returns (context, page); caller closes the context."""
    context = browser.new_context(**dict(playwright.devices[device]))
    page = context.new_page()
    page.add_init_script(_GATE_INIT)
    helper = make_worker_data(page, base_url)
    if helper.wait() != "worker":
        context.close()
        pytest.skip("worker provider unavailable in this environment")
    helper.wipe_relationships()
    page.evaluate("() => { location.hash = '#/settings'; }")
    # The reduced phone Settings renders app-info stat lines.
    page.locator(".settings-statlines").wait_for(state="visible", timeout=10000)
    return context, page


@pytest.mark.parametrize("device", _MOBILE_DEVICES)
def test_folder_storage_not_offered_but_api_present(playwright, browser, base_url_fixture, device):
    """The feature is gated off as policy, not because the API is missing."""
    context, page = _mobile_settings_page(playwright, browser, device, base_url_fixture)
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
def test_folder_section_and_download_absent_on_phone(playwright, browser, base_url_fixture, device):
    """Phone Settings is browse-only: no folder section, no choose-folder
    button, no folder-push banner, and no "Download my private data"
    button (there is no phone-authored private data to download)."""
    context, page = _mobile_settings_page(playwright, browser, device, base_url_fixture)
    try:
        assert page.locator("#settings-folder-section").count() == 0, (
            f"{device}: folder section should not render in phone Settings"
        )
        assert page.locator("#settings-folder-choose").count() == 0, (
            f"{device}: choose-folder button should not render on a phone"
        )
        assert page.locator("#settings-download-userdata").count() == 0, (
            f"{device}: download button should not render on a phone (browse-only)"
        )
        expect(page.locator("#folder-push-banner")).to_be_hidden()
    finally:
        context.close()
