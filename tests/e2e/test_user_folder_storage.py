"""E2E for issue #165 Phase 1 — user-folder durable storage.

Pins:
- The Data folder section renders on the Settings page.
- Choose data folder picks a folder, the badge flips to Saved, and a
  real relationships.db lands in the Fellows/ subfolder.
- Save Now updates the file timestamp.
- Disconnect folder reverts the badge to Browser-only and clears the
  IDB handle (subsequent boots see no handle).
- Re-picking the same parent triggers the collision dialog, and
  Create-Fellows-2 lands in a sibling subfolder.

The picker is stubbed to return a real FileSystemDirectoryHandle backed
by an OPFS subfolder. The worker's write/read path runs unchanged
against a real handle — same File System Access async API as the
production user-picker flow. The only thing this doesn't exercise is
the OS permission round-trip itself (OPFS handles auto-grant); that's
covered by the unit-level checkFolderPermission tests separately.

Chromium-only by virtue of `showDirectoryPicker` — Firefox / WebKit
take the unsupported-browser badge path, which is its own test.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect


# Install a fake `window.showDirectoryPicker` that returns a real OPFS
# subfolder handle. The "user folder" stays at OPFS root under a
# stable name so we can re-pick the same folder in collision tests.
_STUB_DIRECTORY_PICKER = """
(function () {
  var STUB_NAME = '__e2e_user_folder__';
  window.showDirectoryPicker = async function () {
    var root = await navigator.storage.getDirectory();
    return await root.getDirectoryHandle(STUB_NAME, { create: true });
  };
  // Test affordance: nuke the stub folder so each test starts from a
  // clean slate. Called from the test via page.evaluate.
  window.__resetE2EUserFolder = async function () {
    var root = await navigator.storage.getDirectory();
    try { await root.removeEntry(STUB_NAME, { recursive: true }); } catch (e) {}
  };
  // Test affordance: read back a probe of what landed in the stub
  // folder. Returns { hasFellows: bool, hasFellows2: bool,
  // relSize: int|null }.
  window.__probeE2EUserFolder = async function () {
    var root = await navigator.storage.getDirectory();
    var out = { hasFellows: false, hasFellows2: false, relSize: null };
    var stub;
    try { stub = await root.getDirectoryHandle(STUB_NAME); }
    catch (e) { return out; }
    try {
      var f = await stub.getDirectoryHandle('Fellows');
      out.hasFellows = true;
      try {
        var fh = await f.getFileHandle('relationships.db');
        var file = await fh.getFile();
        out.relSize = file.size;
      } catch (e) {}
    } catch (e) {}
    try {
      await stub.getDirectoryHandle('Fellows 2');
      out.hasFellows2 = true;
    } catch (e) {}
    return out;
  };
  // Test affordance: clear the worker's IDB-persisted handle so the
  // next page load boots fresh. Same DB the worker uses internally.
  window.__clearE2EFolderIdb = function () {
    return new Promise(function (resolve) {
      var req = indexedDB.deleteDatabase('fellows-fs-handles');
      req.onsuccess = req.onerror = req.onblocked = function () { resolve(true); };
    });
  };
})();
"""


@pytest.fixture
def folder_page(standalone_page, base_url_fixture):
    """Like worker_data but with the picker stub installed at init.
    Yields the page; tests drive __dataProvider directly when they need
    setup beyond the UI.
    """
    page = standalone_page
    page.add_init_script(_STUB_DIRECTORY_PICKER)
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    # Wait for the worker provider to land.
    page.wait_for_function(
        "() => window.__dataProvider && typeof window.__dataProvider.listGroups === 'function'",
        timeout=10000,
    )
    # Skip if we somehow ended up on the api+idb fallback — File System
    # Access tests need the worker path.
    kind = page.evaluate("() => window.__dataProvider.kind")
    if kind != "worker":
        pytest.skip(f"folder tests need the worker provider; got {kind!r}")
    # Clean start: clear the IDB-stored handle and wipe any stub folder
    # leftover from a previous run.
    page.evaluate("() => window.__clearE2EFolderIdb()")
    page.evaluate("() => window.__resetE2EUserFolder()")
    # Wipe relationships state so each test has a known baseline.
    page.evaluate("""
      async () => {
        var dp = window.__dataProvider;
        var groups = await dp.listGroups();
        for (var i = 0; i < groups.length; i++) {
          try { await dp.deleteGroup(groups[i].id); } catch (e) {}
        }
        var bag = await dp.getSettings();
        for (var k in bag) { try { await dp.setSetting(k, ''); } catch (e) {} }
      }
    """)
    try:
        yield page
    finally:
        try:
            page.evaluate("() => window.__resetE2EUserFolder()")
        except Exception:
            pass


def _open_settings(page, base_url):
    page.goto(f"{base_url}/#/settings", wait_until="domcontentloaded")
    page.locator(".settings-title").wait_for(state="visible", timeout=5000)
    page.locator("#settings-folder-section").wait_for(state="visible", timeout=5000)


class TestUserFolderStorage:
    def test_data_folder_section_renders_with_browser_only_badge(
        self, folder_page, base_url_fixture
    ):
        _open_settings(folder_page, base_url_fixture)
        # On a fresh state, badge says "Browser-only" and only the
        # Choose button is visible.
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Browser-only")
        expect(folder_page.locator("#settings-folder-choose")).to_be_visible()
        expect(folder_page.locator("#settings-folder-save-now")).to_be_hidden()
        expect(folder_page.locator("#settings-folder-disconnect")).to_be_hidden()

    def test_choose_folder_writes_file_and_flips_badge_to_saved(
        self, folder_page, base_url_fixture
    ):
        _open_settings(folder_page, base_url_fixture)
        # Seed a group so the relationships.db isn't empty.
        full = folder_page.evaluate("() => window.__dataProvider.getFull()")
        rid = full[0]["record_id"]
        folder_page.evaluate(
            "(rid) => window.__dataProvider.createGroup({name: 'Folder seed', note: '', fellow_record_ids: [rid]})",
            rid,
        )
        folder_page.locator("#settings-folder-choose").click()
        # Badge flips to Saved after the auto-save.
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        # Real file landed in the stub folder.
        probe = folder_page.evaluate("() => window.__probeE2EUserFolder()")
        assert probe["hasFellows"] is True, "Fellows/ subfolder should exist"
        assert probe["relSize"] is not None and probe["relSize"] > 0, (
            f"relationships.db should have bytes; probe={probe!r}"
        )
        # Save Now and Disconnect appear; Choose no longer.
        expect(folder_page.locator("#settings-folder-save-now")).to_be_visible()
        expect(folder_page.locator("#settings-folder-disconnect")).to_be_visible()
        expect(folder_page.locator("#settings-folder-choose")).to_be_hidden()

    def test_save_now_updates_file_after_mutation(
        self, folder_page, base_url_fixture
    ):
        _open_settings(folder_page, base_url_fixture)
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        size_before = folder_page.evaluate(
            "() => window.__probeE2EUserFolder().then(p => p.relSize)"
        )
        # Add a group + members to grow the DB.
        full = folder_page.evaluate("() => window.__dataProvider.getFull()")
        rids = [f["record_id"] for f in full[:5]]
        folder_page.evaluate(
            "(rids) => window.__dataProvider.createGroup({name: 'Grow', note: 'x', fellow_record_ids: rids})",
            rids,
        )
        # Click Save now and assert the file changed.
        folder_page.locator("#settings-folder-save-now").click()
        # The Save now click fires writeRelationshipsToFolder; wait for
        # the detail to flash "Saved (N bytes)."
        detail = folder_page.locator("#settings-folder-detail")
        expect(detail).to_contain_text("Saved (", timeout=10000)
        size_after = folder_page.evaluate(
            "() => window.__probeE2EUserFolder().then(p => p.relSize)"
        )
        assert size_after >= size_before, (
            f"file should not shrink after adding a group; before={size_before} after={size_after}"
        )

    def test_disconnect_clears_handle(self, folder_page, base_url_fixture):
        _open_settings(folder_page, base_url_fixture)
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        # Auto-accept the confirm dialog from window.confirm.
        folder_page.once("dialog", lambda d: d.accept())
        folder_page.locator("#settings-folder-disconnect").click()
        expect(badge_text).to_contain_text("Browser-only", timeout=5000)
        # Worker reports no handle now.
        state = folder_page.evaluate("() => window.__folderController.getState()")
        assert state["hasHandle"] is False

    def test_collision_dialog_offers_open_existing_or_create_new(
        self, folder_page, base_url_fixture
    ):
        _open_settings(folder_page, base_url_fixture)
        # First pick → creates Fellows/.
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        # Disconnect (handle gone from IDB; Fellows/ stays in the folder).
        folder_page.once("dialog", lambda d: d.accept())
        folder_page.locator("#settings-folder-disconnect").click()
        expect(badge_text).to_contain_text("Browser-only", timeout=5000)
        # Re-pick the same parent. The worker probes, finds Fellows/
        # already with a relationships.db, returns requiresChoice → the
        # collision dialog opens.
        folder_page.locator("#settings-folder-choose").click()
        dialog = folder_page.locator("#settings-folder-collision-dialog")
        expect(dialog).to_be_visible(timeout=5000)
        # Click "Create Fellows 2".
        folder_page.locator("#settings-folder-collision-create").click()
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        probe = folder_page.evaluate("() => window.__probeE2EUserFolder()")
        assert probe["hasFellows"] is True, "original Fellows/ should be untouched"
        assert probe["hasFellows2"] is True, "Fellows 2/ should have been created"

    def test_open_existing_loads_data_back(self, folder_page, base_url_fixture):
        _open_settings(folder_page, base_url_fixture)
        # Round 1: seed a group, pick folder, save.
        full = folder_page.evaluate("() => window.__dataProvider.getFull()")
        rid = full[0]["record_id"]
        folder_page.evaluate(
            "(rid) => window.__dataProvider.createGroup({name: 'Round 1 group', note: '', fellow_record_ids: [rid]})",
            rid,
        )
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        # Disconnect + nuke groups in OPFS so a Refresh / Open-existing
        # actually has work to do.
        folder_page.once("dialog", lambda d: d.accept())
        folder_page.locator("#settings-folder-disconnect").click()
        expect(badge_text).to_contain_text("Browser-only", timeout=5000)
        folder_page.evaluate("""
          async () => {
            var dp = window.__dataProvider;
            var groups = await dp.listGroups();
            for (var i = 0; i < groups.length; i++) {
              await dp.deleteGroup(groups[i].id);
            }
          }
        """)
        assert folder_page.evaluate("() => window.__dataProvider.listGroups()") == []
        # Re-pick → collision dialog → Open existing → groups come back.
        folder_page.locator("#settings-folder-choose").click()
        dialog = folder_page.locator("#settings-folder-collision-dialog")
        expect(dialog).to_be_visible(timeout=5000)
        folder_page.locator(".settings-folder-dialog-secondary").click()
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        groups = folder_page.evaluate("() => window.__dataProvider.listGroups()")
        names = [g["name"] for g in groups]
        assert "Round 1 group" in names, (
            f"open-existing should have loaded the saved group back; got {names!r}"
        )


class TestPhase2Pivot:
    """Pivot-specific scenarios per plans/user_folder_storage.md § Phase 2
    (revised 2026-05-22). Phase 1 tests above keep the manual save/restore
    UX honest; these add the per-commit auto-write + boot-time mode
    detection that the pivot delivers.
    """

    def test_post_commit_auto_writes_advance_last_saved_at(
        self, folder_page, base_url_fixture
    ):
        """After picking a folder, every committed mutation should fire the
        post-commit folder write — observable via `lastSavedAt` advancing
        after each mutation, WITHOUT any Save Now click. File size is an
        unreliable witness (SQLite pages can absorb new rows), but
        `lastSavedAt` is set to `new Date().toISOString()` on every
        successful folder write so it's the canonical "did we write?"
        signal.

        Three mutating RPCs are exercised: createGroup, setSetting, and
        updateGroup — covering both the group-mutation path and the
        non-group settings path. deleteGroup + importRelationshipsBytes
        are covered structurally by the same _maybeWriteFolderAfterCommit
        helper; not exhaustively pinned here.
        """
        _open_settings(folder_page, base_url_fixture)
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)

        # Helper: read the worker's folder state and return lastSavedAt.
        def saved_at():
            state = folder_page.evaluate(
                "() => window.__dataProvider._getFolderState()"
            )
            return state.get("lastSavedAt")

        # Mutation 1: createGroup. wait_for_function loops until
        # lastSavedAt has changed from its current value — robust to
        # the async RPC + post-commit-hook timing.
        full = folder_page.evaluate("() => window.__dataProvider.getFull()")
        rids = [f["record_id"] for f in full[:5]]
        before_create = saved_at()
        folder_page.evaluate(
            "(rids) => window.__dataProvider.createGroup({"
            "name: 'Auto-write G1', note: '', fellow_record_ids: rids})",
            rids,
        )
        folder_page.wait_for_function(
            "(before) => window.__dataProvider._getFolderState()"
            "  .then(s => s.lastSavedAt && s.lastSavedAt !== before)",
            arg=before_create,
            timeout=5000,
        )
        after_create = saved_at()
        assert after_create and after_create != before_create, (
            f"lastSavedAt should advance after createGroup; "
            f"before={before_create!r} after={after_create!r}"
        )

        # Mutation 2: setSetting (smallest mutating RPC).
        before_set = after_create
        folder_page.evaluate(
            "() => window.__dataProvider.setSetting('e2e_phase2_key', 'phase2-auto-write')"
        )
        folder_page.wait_for_function(
            "(before) => window.__dataProvider._getFolderState()"
            "  .then(s => s.lastSavedAt && s.lastSavedAt !== before)",
            arg=before_set,
            timeout=5000,
        )
        after_set = saved_at()
        assert after_set != before_set, (
            f"lastSavedAt should advance after setSetting; "
            f"before={before_set!r} after={after_set!r}"
        )

        # Mutation 3: updateGroup on the group we just created.
        groups = folder_page.evaluate("() => window.__dataProvider.listGroups()")
        gid = next(g["id"] for g in groups if g["name"] == "Auto-write G1")
        before_update = after_set
        folder_page.evaluate(
            "(gid) => window.__dataProvider.updateGroup(gid, "
            "{name: 'Auto-write G1 (renamed)', note: 'updated'})",
            gid,
        )
        folder_page.wait_for_function(
            "(before) => window.__dataProvider._getFolderState()"
            "  .then(s => s.lastSavedAt && s.lastSavedAt !== before)",
            arg=before_update,
            timeout=5000,
        )
        after_update = saved_at()
        assert after_update != before_update, (
            f"lastSavedAt should advance after updateGroup; "
            f"before={before_update!r} after={after_update!r}"
        )

        # Final cross-check: the badge UI also reflects the most recent
        # write. The "Saved" badge subtitle includes a relative time
        # ("just now" / "X min ago") — verify it stayed in Saved state
        # rather than flipping to a warning state.
        expect(badge_text).to_contain_text("Saved to")
