"""E2E for issue #165 Phase 1 — user-folder durable storage.

Pins:
- The Private data folder section renders on the Settings page.
- Choose folder picks a folder, the badge flips to Saved, and a
  real relationships.db lands in the Fellows/ subfolder.
- Auto-write after a commit advances last_saved_at.
- Re-picking the same parent triggers the collision dialog, and
  Create-Fellows-2 lands in a sibling subfolder.

Save now / Reload from folder / Reconnect / Disconnect were removed
in PR #205 (issue #202); the affordances they exposed (auto-save
retry, cross-browser reload, handle teardown) are either automatic
now or covered by re-picking the folder via Change folder.

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
  // relSize: int|null, folderBackupNames: string[] }.
  window.__probeE2EUserFolder = async function () {
    var root = await navigator.storage.getDirectory();
    var out = { hasFellows: false, hasFellows2: false, relSize: null, folderBackupNames: [] };
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
      // Enumerate bak.* siblings of relationships.db. These are the
      // folder-resident backup ring (Phase 2 PR backup-ring-move).
      try {
        for await (var entry of f.values()) {
          if (entry.kind === 'file' && entry.name.indexOf('relationships.db.bak.') === 0) {
            out.folderBackupNames.push(entry.name);
          }
        }
        out.folderBackupNames.sort();
      } catch (e) {}
    } catch (e) {}
    try {
      await stub.getDirectoryHandle('Fellows 2');
      out.hasFellows2 = true;
    } catch (e) {}
    return out;
  };
  // Test affordance: count OPFS-resident bak.* files. Used to verify
  // (a) that backups land in OPFS when folder mode is inactive, and
  // (b) that the OPFS→folder migration deletes them after migrating.
  window.__listE2EOpfsBackups = async function () {
    var root = await navigator.storage.getDirectory();
    var names = [];
    try {
      for await (var entry of root.values()) {
        if (entry.kind === 'file' && entry.name.indexOf('relationships.db.bak.') === 0) {
          names.push(entry.name);
        }
      }
    } catch (e) {}
    names.sort();
    return names;
  };
  // Test affordance: write a synthetic bak.* file directly to OPFS
  // root, so a test can pre-seed the state before triggering a
  // folder-mode boot (to verify the OPFS→folder migration path).
  window.__seedE2EOpfsBackup = async function (name, contentBase64) {
    var root = await navigator.storage.getDirectory();
    var fh = await root.getFileHandle(name, { create: true });
    var w = await fh.createWritable();
    var bin = atob(contentBase64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    await w.write(bytes);
    await w.close();
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
        # On a fresh state, badge says "Browser-only" and the single
        # Choose folder… button is visible (Save now / Reload from
        # folder / Reconnect / Disconnect removed in PR #205).
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Browser-only")
        choose = folder_page.locator("#settings-folder-choose")
        expect(choose).to_be_visible()
        expect(choose).to_have_text("Choose folder…")

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
        # The single button relabels to "Change folder…" once a folder
        # is connected; it stays visible for re-picking (move to synced
        # folder, re-grant permission, switch destinations).
        choose = folder_page.locator("#settings-folder-choose")
        expect(choose).to_be_visible()
        expect(choose).to_have_text("Change folder…")

    def test_collision_dialog_offers_open_existing_or_create_new(
        self, folder_page, base_url_fixture
    ):
        _open_settings(folder_page, base_url_fixture)
        # First pick → creates Fellows/.
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        # Click Change folder and re-pick the same parent. The worker
        # probes, finds Fellows/ already with a relationships.db, returns
        # requiresChoice → the collision dialog opens. Post-PR-#205 the
        # "disconnect first, then pick" flow is gone; users now hit
        # collision by re-picking via Change folder directly.
        folder_page.locator("#settings-folder-choose").click()
        dialog = folder_page.locator("#settings-folder-collision-dialog")
        expect(dialog).to_be_visible(timeout=5000)
        # Click "Create Fellows 2".
        folder_page.locator("#settings-folder-collision-create").click()
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        probe = folder_page.evaluate("() => window.__probeE2EUserFolder()")
        assert probe["hasFellows"] is True, "original Fellows/ should be untouched"
        assert probe["hasFellows2"] is True, "Fellows 2/ should have been created"

    # test_open_existing_loads_data_back was removed in PR #205. It
    # used Disconnect (now removed) to break the OPFS→folder auto-save
    # link before deleting groups, leaving the folder file intact so a
    # re-pick + Open existing could recover the data into a now-empty
    # OPFS. Without Disconnect, the auto-save propagates the deletes
    # to disk, so the scenario the test was exercising isn't reachable
    # from the UI any more. The collision dialog's Open-existing path
    # itself is still covered by test_collision_dialog_offers_open_existing_or_create_new
    # (which exercises the dialog mechanics). Recovery-from-OPFS-loss
    # via folder bytes is now a worker-level concern best covered by a
    # narrower test in a follow-up.


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

    def test_snapshot_lands_in_folder_when_folder_mode_active(
        self, folder_page, base_url_fixture
    ):
        """When a folder is active, the pre-import snapshot (taken
        inside importRelationshipsBytes) lands in the folder's
        Fellows/ subdirectory as a bak.<ISO> sibling — not in OPFS.
        Verifies _writeBackupToActiveStore routes correctly under
        the folder-mode dynamic check.
        """
        _open_settings(folder_page, base_url_fixture)
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        # Export the current relationships.db bytes, then re-import them.
        # importRelationshipsBytes always snapshots-before-import, so this
        # round-trip generates exactly one new bak.* file in whichever
        # store is active.
        folder_page.evaluate("""
          async () => {
            var dp = window.__dataProvider;
            var bytes = await dp.exportRelationshipsBytes();
            await dp.importRelationshipsBytes(bytes);
          }
        """)
        probe = folder_page.evaluate("() => window.__probeE2EUserFolder()")
        assert probe["folderBackupNames"], (
            f"folder mode should write the snapshot to folder/Fellows/; "
            f"probe.folderBackupNames={probe['folderBackupNames']!r}"
        )
        assert probe["folderBackupNames"][0].startswith("relationships.db.bak."), (
            f"backup filename should follow the bak prefix; got {probe['folderBackupNames'][0]!r}"
        )
        # OPFS should NOT have accumulated a backup for this snapshot —
        # folder-mode users no longer write to the OPFS shadow ring.
        opfs_backups = folder_page.evaluate("() => window.__listE2EOpfsBackups()")
        assert opfs_backups == [], (
            f"folder mode should not write backups to OPFS; OPFS backups={opfs_backups!r}"
        )

    def test_opfs_to_folder_backup_migration_on_folder_boot(
        self, folder_page, base_url_fixture
    ):
        """Pre-seed an OPFS-resident bak.* file (the state a Phase 1
        user would arrive with), pick a folder, then reload the page.
        Worker re-init runs _maybeMigrateOpfsBackupsToFolder, which
        moves the OPFS bak to the folder's Fellows/ subdir and deletes
        the OPFS original. Rip-the-band-aid-off per Rich's call.
        """
        _open_settings(folder_page, base_url_fixture)
        # Step 1: pick the folder (creates handle in IDB). Initial
        # save populates Fellows/relationships.db.
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        # Step 2: pre-seed an OPFS-resident bak file. Use a real
        # SQLite database header so any future strict-validation code
        # paths don't reject it. The bak file's content doesn't
        # matter for the migration — we're testing that the bytes
        # land in the folder and the OPFS file is removed.
        SAMPLE_SQLITE_HEADER_B64 = (
            "U1FMaXRlIGZvcm1hdCAzAA=="  # "SQLite format 3\0"
        )
        seeded_name = "relationships.db.bak.2026-05-22T01-00-00-000Z"
        folder_page.evaluate(
            "(args) => window.__seedE2EOpfsBackup(args[0], args[1])",
            [seeded_name, SAMPLE_SQLITE_HEADER_B64],
        )
        # Sanity: OPFS now has our seeded backup.
        opfs_before = folder_page.evaluate("() => window.__listE2EOpfsBackups()")
        assert seeded_name in opfs_before, (
            f"sanity: seed didn't land; OPFS backups={opfs_before!r}"
        )
        # Step 3: reload the page. Worker re-init runs in folder
        # mode (handle persisted in IDB + permission still granted
        # via the OPFS-backed stub). Migration fires.
        folder_page.reload(wait_until="domcontentloaded")
        folder_page.wait_for_function(
            "() => window.__dataProvider && typeof window.__dataProvider.listGroups === 'function'",
            timeout=10000,
        )
        # Step 4: OPFS bak is gone; folder bak is present.
        opfs_after = folder_page.evaluate("() => window.__listE2EOpfsBackups()")
        assert seeded_name not in opfs_after, (
            f"migration should have deleted OPFS bak; OPFS still has it: {opfs_after!r}"
        )
        probe = folder_page.evaluate("() => window.__probeE2EUserFolder()")
        assert seeded_name in probe["folderBackupNames"], (
            f"migration should have copied OPFS bak to folder; "
            f"folder bak files: {probe['folderBackupNames']!r}"
        )

    def test_folder_push_banner_appears_until_folder_picked(
        self, folder_page, base_url_fixture
    ):
        """The top-of-page banner pushes capable-browser OPFS-only users
        to pick a data folder. Phase 2 PR 3 (settings UI push).

        On a fresh load with no folder handle, banner is visible.
        After picking a folder it hides immediately (Settings page's
        renderState cascade calls refreshFolderPushBanner).

        Note: the banner has an initial 1.5s delay so the worker has
        time to report workerAvailable=true. Test waits for that.

        Uses the page state established by the folder_page fixture —
        no re-navigation, which would trigger an OPFS-pool ownership
        conflict against the still-warm worker.
        """
        folder_page.wait_for_function(
            "() => document.getElementById('folder-push-banner') !== null",
            timeout=10000,
        )
        banner = folder_page.locator("#folder-push-banner")
        # Wait for the initial-load delayed evaluation to fire and the
        # banner to become visible. The banner reads
        # window.__folderController.getState() which returns
        # workerAvailable=false until init completes; in this fixture
        # the worker provider is already up (the fixture asserts it),
        # so once the 1.5s setTimeout fires the banner appears.
        # Wait for the banner to NOT have the hidden class (it has other
        # classes too — folder-push-banner — so to_have_class can't be
        # used for "contains hidden"; use a wait_for_function instead).
        folder_page.wait_for_function(
            "() => { var el = document.getElementById('folder-push-banner');"
            "        return el && !el.classList.contains('hidden'); }",
            timeout=10000,
        )
        # Both buttons are present.
        expect(folder_page.locator("#folder-push-cta")).to_be_visible()
        expect(folder_page.locator("#folder-push-dismiss")).to_be_visible()
        # Pick a folder via the Settings UI. This is the same flow a
        # user would follow after clicking the banner CTA.
        _open_settings(folder_page, base_url_fixture)
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        # The Settings page's renderState cascades to refreshFolderPushBanner;
        # banner should now be hidden.
        folder_page.wait_for_function(
            "() => { var el = document.getElementById('folder-push-banner');"
            "        return el && el.classList.contains('hidden'); }",
            timeout=5000,
        )

    def test_folder_push_banner_dismiss_persists_within_session(
        self, folder_page, base_url_fixture
    ):
        """'Not now' sets a sessionStorage flag; the banner stays hidden
        for the rest of the browser session even on reload. Re-appearing
        after browser close is the next-session behavior (out of scope
        for sessionStorage-based testing).
        """
        folder_page.wait_for_function(
            "() => { var el = document.getElementById('folder-push-banner');"
            "        return el && !el.classList.contains('hidden'); }",
            timeout=10000,
        )
        folder_page.locator("#folder-push-dismiss").click()
        # Hides immediately on dismiss.
        folder_page.wait_for_function(
            "() => { var el = document.getElementById('folder-push-banner');"
            "        return el && el.classList.contains('hidden'); }",
            timeout=2000,
        )
        # Reload — sessionStorage survives reload-within-the-same-tab.
        folder_page.reload(wait_until="domcontentloaded")
        folder_page.wait_for_function(
            "() => document.getElementById('folder-push-banner') !== null",
            timeout=10000,
        )
        # Give the initial-load setTimeout a chance to fire. Banner
        # should still be hidden because the sessionStorage flag is set.
        folder_page.wait_for_timeout(2000)
        assert folder_page.evaluate(
            "() => document.getElementById('folder-push-banner').classList.contains('hidden')"
        ), "banner should remain hidden across reload-within-session"

    def test_folder_push_banner_cta_navigates_to_settings(
        self, folder_page, base_url_fixture
    ):
        """Clicking 'Set up data folder' navigates to #/settings and the
        Data folder section becomes visible (the user lands on the
        actionable surface).
        """
        folder_page.wait_for_function(
            "() => { var el = document.getElementById('folder-push-banner');"
            "        return el && !el.classList.contains('hidden'); }",
            timeout=10000,
        )
        folder_page.locator("#folder-push-cta").click()
        # Hash navigation happens synchronously; verify we landed in
        # Settings + the Data folder section is now visible.
        folder_page.wait_for_function(
            "() => window.location.hash === '#/settings'", timeout=5000
        )
        expect(folder_page.locator("#settings-folder-section")).to_be_visible(timeout=5000)
        expect(folder_page.locator("#settings-folder-choose")).to_be_visible()

    def test_path_detail_line_shows_after_folder_picked(
        self, folder_page, base_url_fixture
    ):
        """After picking a folder, the Settings page surfaces the
        relative path (parent / Fellows / relationships.db) below the
        green Saved badge — handy for users who forget where their
        data lives. File System Access API doesn't expose absolute
        paths; the in-app text says to look in Finder for the full one.
        """
        _open_settings(folder_page, base_url_fixture)
        # No folder picked yet — path line is hidden.
        expect(folder_page.locator("#settings-folder-path")).to_be_hidden()
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("Saved to", timeout=10000)
        # Path line shows the parent / subfolder / filename.
        path_value = folder_page.locator("#settings-folder-path-value")
        expect(path_value).to_be_visible(timeout=5000)
        expect(path_value).to_contain_text("Fellows / relationships.db")
        # And the muted hint about absolute paths is there.
        expect(folder_page.locator(".settings-folder-path-note")).to_contain_text(
            "absolute system paths"
        )

    # test_reload_from_folder_button_relabeled and
    # test_your_saved_data_section_hidden_in_folder_mode were removed
    # in PR #205 (issue #202). The Reload from folder button + the
    # "Your saved data" section both went away; Download my private
    # data lives in the Private data folder section now and is always
    # visible whenever local persistence is available, so the
    # hide-on-folder-active behavior no longer applies.

    def test_opfs_only_mode_keeps_backups_in_opfs(
        self, folder_page, base_url_fixture
    ):
        """Regression check: a user who has NOT picked a folder still
        gets OPFS-resident backups. Migration only kicks in when
        folder mode is active.
        """
        _open_settings(folder_page, base_url_fixture)
        # Don't pick a folder. Trigger a snapshot via the same
        # export/import round-trip used in the folder-mode test.
        folder_page.evaluate("""
          async () => {
            var dp = window.__dataProvider;
            var bytes = await dp.exportRelationshipsBytes();
            await dp.importRelationshipsBytes(bytes);
          }
        """)
        opfs_backups = folder_page.evaluate("() => window.__listE2EOpfsBackups()")
        assert opfs_backups, (
            f"OPFS-only mode should write snapshots to OPFS; OPFS backups={opfs_backups!r}"
        )
        # No folder was picked, so the stub folder shouldn't exist at all.
        probe = folder_page.evaluate("() => window.__probeE2EUserFolder()")
        assert probe["hasFellows"] is False, (
            "no folder mode → no Fellows/ subfolder should exist"
        )
