"""E2E for the folder-writable empirical probe (EPIC PR4).

`probeFolderWritable` is the unlock gate: pick a folder → write a sentinel →
read it back → verify the bytes → persist. The read-back check is what proves
a *durable* local folder (vs a cloud-only / virtual placeholder that accepts
writes but doesn't return them). On any failure it throws a stable reason code
(picker_cancelled / subfolder_create_failed / write_failed / readback_mismatch
/ permission_not_persisted) that the page links to docs/folder_troubleshooting.md.

Coverage note: the folder-BEHAVIOUR reason codes (readback_mismatch,
write_failed, subfolder_create_failed) can't be simulated here — the picked
handle crosses to the worker via structured clone (page-side proxies don't
survive), and the OPFS-backed stub folder is reliable. Those are covered by
code inspection + manual QA on a real cloud/online-only folder. This file
pins the happy path (verify + persist) and reason-code propagation
(picker_cancelled), which exercise the RPC + error envelope.
"""
from __future__ import annotations

from playwright.sync_api import expect

from tests.e2e.conftest import _FOLDER_PICKER_STUB_MIN


def _boot(page, base_url):
    page.add_init_script(_FOLDER_PICKER_STUB_MIN)
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )


def test_probe_happy_path_verifies_and_persists(standalone_page, base_url_fixture):
    page = standalone_page
    _boot(page, base_url_fixture)
    page.evaluate("() => window.__dataProvider._clearFolderHandle()")
    page.evaluate("() => window.__resetE2EUserFolderMin && window.__resetE2EUserFolderMin()")
    result = page.evaluate(
        """async () => {
            const handle = await window.showDirectoryPicker();
            return await window.__dataProvider._probeFolderWritable({ handle });
        }"""
    )
    assert result["ok"] is True, result
    assert result.get("sentinelVerified") is True, result
    assert result.get("permissionPersisted") is True, result
    # Handle persisted → folder state reports it (the unlock precondition).
    state = page.evaluate("() => window.__folderController.getState()")
    assert state["hasHandle"] is True, state
    assert state["permission"] == "granted", state


def test_probe_picker_cancelled_surfaces_reason_code(standalone_page, base_url_fixture):
    page = standalone_page
    _boot(page, base_url_fixture)
    err = page.evaluate(
        """async () => {
            try {
                await window.__dataProvider._probeFolderWritable({ handle: null });
                return { threw: false };
            } catch (e) {
                return { threw: true, code: e.code, message: String(e.message || e) };
            }
        }"""
    )
    assert err["threw"] is True, err
    assert err["code"] == "picker_cancelled", err
    # Nothing persisted on a failed probe — stays browse-only.
    state = page.evaluate("() => window.__folderController.getState()")
    assert state["hasHandle"] is False, state


def test_settings_pick_unlocks_private_data_without_reload(standalone_page, base_url_fixture):
    """The PR4b unlock UI: picking a folder in Settings runs the empirical
    probe and flips the private-data gate IMMEDIATELY (no reload) — group
    surfaces become available in the same session."""
    page = standalone_page
    _boot(page, base_url_fixture)
    page.evaluate("() => window.__dataProvider._clearFolderHandle()")
    page.evaluate("() => window.__resetE2EUserFolderMin && window.__resetE2EUserFolderMin()")
    # Start locked (desktop, no folder).
    page.goto(base_url_fixture + "/#/settings", wait_until="domcontentloaded")
    page.locator("#settings-folder-choose").wait_for(state="visible", timeout=5000)
    page.wait_for_function(
        "() => document.body.classList.contains('no-private-data')", timeout=5000
    )
    # Pick a folder → probe runs → write → gate flips, NO reload.
    page.locator("#settings-folder-choose").click()
    page.wait_for_function(
        "async () => { try { var s = await window.__folderController.getState();"
        " return !!s.hasHandle; } catch (e) { return false; } }",
        timeout=10000,
    )
    page.wait_for_function(
        "() => document.body && !document.body.classList.contains('no-private-data')",
        timeout=8000,
    )
    assert page.evaluate("() => window.__privateDataTier") == "private-folder"


def test_lock_my_private_data_returns_to_browse_only(standalone_page, base_url_fixture):
    """The 'Lock my private data' control disconnects the folder and flips the
    gate back to browse-only live (no reload). The folder file is untouched —
    re-picking unlocks again."""
    page = standalone_page
    _boot(page, base_url_fixture)
    page.evaluate("() => window.__dataProvider._clearFolderHandle()")
    page.evaluate("() => window.__resetE2EUserFolderMin && window.__resetE2EUserFolderMin()")
    # Unlock first.
    page.goto(base_url_fixture + "/#/settings", wait_until="domcontentloaded")
    page.locator("#settings-folder-choose").wait_for(state="visible", timeout=5000)
    page.locator("#settings-folder-choose").click()
    page.wait_for_function(
        "() => !document.body.classList.contains('no-private-data')", timeout=10000
    )
    # The lock control appears only when a folder is connected.
    lock = page.locator("#settings-folder-lock")
    expect(lock).to_be_visible()
    # Accept the confirm() prompt, then lock.
    page.once("dialog", lambda d: d.accept())
    lock.click()
    # Gate flips back to browse-only, live.
    page.wait_for_function(
        "() => document.body.classList.contains('no-private-data')", timeout=8000
    )
    state = page.evaluate("() => window.__folderController.getState()")
    assert state["hasHandle"] is False, state
    assert page.evaluate("() => window.__privateDataTier") == "browse-only-desktop"
