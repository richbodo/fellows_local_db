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
  //
  // Recursive removeEntry can fail when a child handle hasn't been
  // fully released yet by the just-terminated worker — the original
  // implementation swallowed that error and let Fellows/relationships.db
  // linger into the next test, which would then hit the collision
  // dialog instead of the clean-pick happy path. We now walk the tree
  // explicitly (so removeEntry doesn't have to recurse over partially-
  // released handles) and retry the outer remove a few times.
  window.__resetE2EUserFolder = async function () {
    var root = await navigator.storage.getDirectory();
    async function purge(dir) {
      for await (var entry of dir.values()) {
        if (entry.kind === 'directory') {
          try { await purge(entry); } catch (e) {}
          try { await dir.removeEntry(entry.name, { recursive: true }); } catch (e) {}
        } else {
          try { await dir.removeEntry(entry.name); } catch (e) {}
        }
      }
    }
    try {
      var stub = await root.getDirectoryHandle(STUB_NAME);
      await purge(stub);
    } catch (e) {
      // Stub didn't exist — nothing to purge.
    }
    for (var attempt = 0; attempt < 3; attempt++) {
      try {
        await root.removeEntry(STUB_NAME, { recursive: true });
        return;
      } catch (e) {
        if (attempt === 2) return;
        await new Promise(function (r) { setTimeout(r, 50); });
      }
    }
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
  // Test affordance: hold the folder-write Web Lock indefinitely from
  // the page side. The worker calls navigator.locks.request(...) with
  // ifAvailable:true around _writeBytesToFolder; same agent-cluster,
  // same lock namespace, so holding from page JS makes that request
  // see the lock as held and fail fast with folder_locked_by_another_tab.
  // The unresolved promise inside the request keeps the lock alive
  // until __releaseFolderLock() is called (or the page closes — Web
  // Locks auto-release on agent termination).
  // Lock name MUST match FOLDER_WRITE_LOCK_NAME in vendor/sqlite-worker.js.
  var _holdRelease = null;
  window.__holdFolderLockForever = function () {
    return new Promise(function (outerResolve, outerReject) {
      try {
        navigator.locks.request(
          'fellows-relationships-folder-write',
          { mode: 'exclusive' },
          function (lock) {
            return new Promise(function (release) {
              _holdRelease = release;
              outerResolve({ held: true });
            });
          }
        ).catch(outerReject);
      } catch (e) { outerReject(e); }
    });
  };
  window.__releaseFolderLock = function () {
    if (_holdRelease) { _holdRelease(); _holdRelease = null; return true; }
    return false;
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
    # Clean start: detach the worker's in-memory folder record AND
    # delete the IDB-stored handle. Using _clearFolderHandle (rather
    # than just __clearE2EFolderIdb) matters here: the worker keeps
    # parentHandle/subfolderName in module-scope state, hydrated from
    # IDB on init. If we only delete the IDB row, the next mutating
    # RPC's post-commit hook still sees the stale in-memory handle
    # and re-creates Fellows/relationships.db inside the just-purged
    # stub folder — re-arming the collision dialog for whatever
    # picks a folder next.
    page.evaluate("() => window.__dataProvider._clearFolderHandle()")
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
        # On a fresh state the badge says private data isn't connected (the
        # capability-gate framing — was "Browser-only" before the gate) and
        # the single Choose folder… button is visible.
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        expect(badge_text).to_contain_text("isn’t connected")
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


class TestPhase2WriteLock:
    """Web Locks guard around folder writes per plans/user_folder_storage.md
    § Phase 2 — Multi-tab guard. Covers the two acceptance criteria for
    failure-mode honesty (mutation that can't reach disk surfaces as
    write-failed; retry recovers; tab close with pending failure does
    not corrupt the on-disk state) and the cross-tab lock-serialization
    story that becomes load-bearing when the multi-tab takeover plan
    ships.

    Mechanism: hold the 'fellows-relationships-folder-write' lock from
    page JS via __holdFolderLockForever(). Page + worker share the same
    agent-cluster lock namespace, so the worker's
    navigator.locks.request(..., ifAvailable: true) sees null and
    _writeBytesToFolder throws folder_locked_by_another_tab. The
    per-commit hook catches the throw, populates folderRecord.lastError,
    and does NOT re-throw — the OPFS commit succeeded, the user just
    has to make another change once the lock is free.
    """

    def _pick_folder_and_seed_group_a(self, folder_page, base_url):
        """Common setup: pick folder, create group A, wait until folder
        contains group A. Returns (group_a_id, baseline_saved_at,
        baseline_rel_size).

        Robust to the full-suite case where the OPFS-stub folder's
        Fellows/ subfolder lingers from a prior test (the recursive
        removeEntry in __resetE2EUserFolder swallows errors silently
        if a SAH on a nested file hasn't been released yet by the
        prior page's terminating worker). If that happens the picker
        sees existing data and the collision dialog opens — we
        proceed via 'Open existing data', same baseline outcome.
        """
        _open_settings(folder_page, base_url)
        folder_page.locator("#settings-folder-choose").click()
        badge_text = folder_page.locator("#settings-folder-badge .settings-folder-badge-text")
        # Either the badge flips to Saved within a beat (clean folder),
        # or the collision dialog opens (folder had prior content).
        dialog = folder_page.locator("#settings-folder-collision-dialog")
        try:
            # 5s rather than 2s: under full-suite load the worker's
            # setHandle('auto') probe (which surfaces requiresChoice
            # and triggers the dialog) can run later than the snappy
            # isolated case. A too-short wait drops into the except
            # branch, leaving the modal undismissed for the 15s
            # "Saved to" wait below.
            dialog.wait_for(state="visible", timeout=5000)
            # Open existing — adopt the prior content; we'll overwrite
            # it with our test mutations anyway, and the badge flips
            # to Saved as soon as the open completes.
            folder_page.locator(
                "#settings-folder-collision-dialog button[value=open-existing]"
            ).click()
        except Exception:
            # No dialog — clean pick path; nothing to do.
            pass
        expect(badge_text).to_contain_text("Saved to", timeout=15000)
        full = folder_page.evaluate("() => window.__dataProvider.getFull()")
        rids = [f["record_id"] for f in full[:3]]
        before = folder_page.evaluate(
            "() => window.__dataProvider._getFolderState().then(s => s.lastSavedAt)"
        )
        folder_page.evaluate(
            "(rids) => window.__dataProvider.createGroup({"
            "name: 'Lock test A', note: '', fellow_record_ids: rids})",
            rids,
        )
        folder_page.wait_for_function(
            "(before) => window.__dataProvider._getFolderState()"
            "  .then(s => s.lastSavedAt && s.lastSavedAt !== before)",
            arg=before,
            timeout=5000,
        )
        groups = folder_page.evaluate("() => window.__dataProvider.listGroups()")
        gid = next(g["id"] for g in groups if g["name"] == "Lock test A")
        state = folder_page.evaluate(
            "() => window.__dataProvider._getFolderState()"
        )
        probe = folder_page.evaluate("() => window.__probeE2EUserFolder()")
        return gid, state["lastSavedAt"], probe["relSize"]

    def test_lock_held_during_write_surfaces_failure_then_recovers(
        self, folder_page, base_url_fixture
    ):
        """Phase 2 AC #2 — mutation that can't reach disk surfaces as
        write-failed, retry via fresh mutation recovers.

        Hold the folder-write lock from page JS. Create group B → the
        worker's post-commit folder write sees the lock as held and
        throws folder_locked_by_another_tab; folderRecord.lastError is
        populated; lastSavedAt does NOT advance; folder file is
        unchanged on disk. In-memory DB still has both A and B
        (the OPFS commit succeeded).

        Release the lock. The next mutating RPC (setSetting here)
        re-attempts the folder write; this time the lock is free,
        the write succeeds with all the in-memory state including B,
        lastError clears and lastSavedAt advances.

        Also pins the user-facing Settings badge: "Last save failed"
        + the "Another window…" detail line while blocked, and back to
        "Saved to …" after recovery — the surface the pre-ship checklist
        used to verify by hand.
        """
        gid_a, baseline_saved_at, baseline_rel_size = (
            self._pick_folder_and_seed_group_a(folder_page, base_url_fixture)
        )
        # Hold the lock from the page side. Same agent cluster as the
        # worker, so the worker's ifAvailable:true request will see null.
        folder_page.evaluate("() => window.__holdFolderLockForever()")
        # Create group B. The OPFS commit succeeds (mutation lands in
        # the live DB), but the post-commit folder write fails fast on
        # the lock contention. The RPC itself does NOT throw (the
        # per-commit hook swallows the folder-write failure and just
        # populates lastError) — surface is via the badge state.
        full = folder_page.evaluate("() => window.__dataProvider.getFull()")
        rids_b = [f["record_id"] for f in full[3:6]]
        folder_page.evaluate(
            "(rids) => window.__dataProvider.createGroup({"
            "name: 'Lock test B', note: '', fellow_record_ids: rids})",
            rids_b,
        )
        # Poll until the lastError shows up — the post-commit hook is
        # async relative to the createGroup return.
        folder_page.wait_for_function(
            "() => window.__dataProvider._getFolderState()"
            "  .then(s => s.lastError && s.lastError.reason)",
            timeout=5000,
        )
        state_after_b = folder_page.evaluate(
            "() => window.__dataProvider._getFolderState()"
        )
        assert state_after_b["lastError"] is not None, (
            f"lastError should be populated after a lock-blocked write; "
            f"state={state_after_b!r}"
        )
        assert "Another window" in state_after_b["lastError"]["reason"], (
            f"lock-held lastError should carry the actionable copy; "
            f"got {state_after_b['lastError']['reason']!r}"
        )
        # The blocked write surfaces in the Settings folder badge — the
        # user-facing signal the pre-ship checklist used to verify by hand.
        # Re-render the settings route IN-PAGE (hash bounce, NOT a reload:
        # a reload would re-boot the worker and drop the in-memory
        # lastError) so renderFolderSection repaints from the failed state.
        folder_page.evaluate("() => { location.hash = '#/'; }")
        folder_page.evaluate("() => { location.hash = '#/settings'; }")
        folder_page.locator("#settings-folder-section").wait_for(
            state="visible", timeout=5000
        )
        badge_text = folder_page.locator(
            "#settings-folder-badge .settings-folder-badge-text"
        )
        expect(badge_text).to_contain_text("Last save failed", timeout=5000)
        expect(
            folder_page.locator("#settings-folder-detail")
        ).to_contain_text("Another window")
        # lastSavedAt did NOT advance — folder is still at A only.
        assert state_after_b["lastSavedAt"] == baseline_saved_at, (
            f"lastSavedAt should NOT advance when the write was blocked; "
            f"baseline={baseline_saved_at!r} after_b={state_after_b['lastSavedAt']!r}"
        )
        # In-memory DB still has both groups — OPFS commit succeeded.
        groups_in_mem = folder_page.evaluate("() => window.__dataProvider.listGroups()")
        names = sorted(g["name"] for g in groups_in_mem)
        assert names == ["Lock test A", "Lock test B"], (
            f"in-memory should have both A and B; got {names!r}"
        )
        # Folder file size unchanged — B is not on disk.
        probe_after_b = folder_page.evaluate("() => window.__probeE2EUserFolder()")
        assert probe_after_b["relSize"] == baseline_rel_size, (
            f"folder relSize should be unchanged when write was blocked; "
            f"baseline={baseline_rel_size!r} after_b={probe_after_b['relSize']!r}"
        )
        # Release the lock; next mutation retries the write.
        released = folder_page.evaluate("() => window.__releaseFolderLock()")
        assert released is True, "lock should have been held to be released"
        # Trigger retry via a fresh mutating RPC. setSetting is the
        # cheapest one; the post-commit hook fires the same way.
        folder_page.evaluate(
            "() => window.__dataProvider.setSetting('e2e_lock_retry', 'recovered')"
        )
        folder_page.wait_for_function(
            "(before) => window.__dataProvider._getFolderState()"
            "  .then(s => s.lastSavedAt && s.lastSavedAt !== before "
            "             && (s.lastError === null || s.lastError === undefined))",
            arg=baseline_saved_at,
            timeout=5000,
        )
        state_after_retry = folder_page.evaluate(
            "() => window.__dataProvider._getFolderState()"
        )
        assert state_after_retry["lastError"] in (None,), (
            f"lastError should clear on successful retry; got {state_after_retry['lastError']!r}"
        )
        assert state_after_retry["lastSavedAt"] != baseline_saved_at, (
            f"lastSavedAt should advance on retry; "
            f"baseline={baseline_saved_at!r} after_retry={state_after_retry['lastSavedAt']!r}"
        )
        # Badge UI recovers to Saved after the successful retry (the other
        # half of the pre-ship badge check). Same in-page re-render trick.
        folder_page.evaluate("() => { location.hash = '#/'; }")
        folder_page.evaluate("() => { location.hash = '#/settings'; }")
        folder_page.locator("#settings-folder-section").wait_for(
            state="visible", timeout=5000
        )
        expect(
            folder_page.locator(
                "#settings-folder-badge .settings-folder-badge-text"
            )
        ).to_contain_text("Saved to", timeout=5000)

    def test_write_failed_surfaces_top_of_app_banner_then_clears(
        self, folder_page, base_url_fixture
    ):
        """#221 — a failed folder write must surface as the top-of-app
        banner, not only the Settings pill. A user mid-edit who never opens
        Settings would otherwise never learn their last change wasn't saved.
        The banner auto-clears when the next write succeeds.

        Same lock-contention mechanism as the badge test above: hold the
        folder-write lock from page JS so the worker's post-commit write
        fails fast; a mutation flips the banner to its error variant;
        releasing the lock + mutating again clears it.
        """
        self._pick_folder_and_seed_group_a(folder_page, base_url_fixture)
        banner = folder_page.locator("#folder-push-banner")
        # Baseline: folder picked + last write saved → banner hidden (not
        # write-failed, and the set-up-folder nag doesn't apply once a
        # folder exists).
        folder_page.wait_for_function(
            "() => { var el = document.getElementById('folder-push-banner');"
            "        return el && el.classList.contains('hidden'); }",
            timeout=5000,
        )
        # Block the next folder write, then mutate.
        folder_page.evaluate("() => window.__holdFolderLockForever()")
        full = folder_page.evaluate("() => window.__dataProvider.getFull()")
        rids_b = [f["record_id"] for f in full[3:6]]
        folder_page.evaluate(
            "(rids) => window.__dataProvider.createGroup({"
            "name: 'Banner test B', note: '', fellow_record_ids: rids})",
            rids_b,
        )
        # createGroup's afterFolderMutation hook re-evaluates the banner; it
        # flips to the urgent error variant once the (awaited) post-commit
        # write has recorded lastError.
        folder_page.wait_for_function(
            "() => { var el = document.getElementById('folder-push-banner');"
            "        return el && !el.classList.contains('hidden')"
            "               && el.classList.contains('folder-push-banner--error'); }",
            timeout=5000,
        )
        expect(banner).to_be_visible()
        expect(banner.locator(".folder-push-banner-lead")).to_contain_text(
            "Your latest change"
        )
        expect(banner.locator(".folder-push-banner-detail")).to_contain_text(
            "Another window"
        )
        expect(folder_page.locator("#folder-push-cta")).to_have_text("Open Settings")
        # The unsaved-data warning must not be dismissable.
        assert folder_page.evaluate(
            "() => document.getElementById('folder-push-dismiss').hidden"
        ), "dismiss button must be hidden in the write-failed banner"
        # Recover: release the lock + a fresh group mutation re-attempts the
        # write. (A group mutation, not setSetting — setSetting isn't wrapped
        # with the post-mutation banner refresh; see the worker data provider.)
        assert folder_page.evaluate("() => window.__releaseFolderLock()") is True
        folder_page.evaluate(
            "() => window.__dataProvider.createGroup({"
            "name: 'Banner recovery C', note: '', fellow_record_ids: []})"
        )
        # Banner auto-clears once the write succeeds (badge leaves
        # write-failed → falls through to the hidden branch).
        folder_page.wait_for_function(
            "() => { var el = document.getElementById('folder-push-banner');"
            "        return el && el.classList.contains('hidden'); }",
            timeout=5000,
        )

    def test_tab_close_with_pending_write_failure_preserves_folder_state(
        self, folder_page, base_url_fixture, context
    ):
        """Phase 2 AC #3 — honest mutation loss on tab close.

        Set up folder with group A. Hold the write lock from page JS.
        Create group B → write fails (mem has A+B, folder has A only).
        Close the page (Web Locks auto-release on agent termination,
        but the in-memory mutation B is gone too — that's the honest
        loss the badge warned the user about). Reopen in the same
        browser context (IDB-stored handle persists). Worker boots
        in folder mode, hydrates relationships.db from the folder
        bytes (still A-only). Assert: listGroups returns only A;
        folder file is bytewise unchanged from baseline.
        """
        gid_a, baseline_saved_at, baseline_rel_size = (
            self._pick_folder_and_seed_group_a(folder_page, base_url_fixture)
        )
        folder_page.evaluate("() => window.__holdFolderLockForever()")
        # Create group B; write fails. We don't bother waiting for the
        # lastError here — the close will fire the failure path either
        # way and the next-boot assertion is what matters.
        full = folder_page.evaluate("() => window.__dataProvider.getFull()")
        rids_b = [f["record_id"] for f in full[3:6]]
        folder_page.evaluate(
            "(rids) => window.__dataProvider.createGroup({"
            "name: 'Lock test B (will be lost)', note: '', fellow_record_ids: rids})",
            rids_b,
        )
        # Sanity: in-memory has A+B before close.
        groups_pre_close = folder_page.evaluate(
            "() => window.__dataProvider.listGroups()"
        )
        names_pre_close = sorted(g["name"] for g in groups_pre_close)
        assert "Lock test B (will be lost)" in names_pre_close, (
            f"sanity: in-mem should have B before close; got {names_pre_close!r}"
        )
        # Sanity: folder file still A-only.
        probe_pre_close = folder_page.evaluate("() => window.__probeE2EUserFolder()")
        assert probe_pre_close["relSize"] == baseline_rel_size, (
            f"sanity: folder should be unchanged before close; "
            f"baseline={baseline_rel_size!r} pre_close={probe_pre_close['relSize']!r}"
        )
        # Close the page WITHOUT releasing the lock. Web Locks
        # auto-release on agent termination; the lock dies with the
        # page. The in-memory worker dies too — B is honestly lost.
        url = folder_page.url
        folder_page.close()
        # Reopen in the same browser context — IDB persists, so the
        # folder handle is still there.
        new_page = context.new_page()
        new_page.add_init_script(_STUB_DIRECTORY_PICKER)
        try:
            new_page.goto(url, wait_until="domcontentloaded")
            new_page.wait_for_function(
                "() => window.__dataProvider && typeof window.__dataProvider.listGroups === 'function'",
                timeout=10000,
            )
            # Folder-mode boot: hydrate OPFS buffer from folder bytes.
            # The folder still has A-only, so in-memory should reflect
            # only A (B was honestly lost).
            groups_post_reboot = new_page.evaluate(
                "() => window.__dataProvider.listGroups()"
            )
            names_post = sorted(g["name"] for g in groups_post_reboot)
            assert names_post == ["Lock test A"], (
                f"after honest loss, only A should remain; got {names_post!r}"
            )
            # Folder file is unchanged from the baseline (no silent
            # overwrite of A by stale B).
            probe_post = new_page.evaluate("() => window.__probeE2EUserFolder()")
            assert probe_post["relSize"] == baseline_rel_size, (
                f"folder bytes should be unchanged across the failed-write+close cycle; "
                f"baseline={baseline_rel_size!r} post={probe_post['relSize']!r}"
            )
        finally:
            try:
                new_page.evaluate("() => window.__resetE2EUserFolder()")
            except Exception:
                pass
            new_page.close()

    def test_lock_held_by_second_page_blocks_first_page_write(
        self, folder_page, base_url_fixture, context
    ):
        """Cross-page lock serialization. A second page in the same
        browser context holds the folder-write lock from its page JS;
        the first page's worker mutation fails fast with the same
        write-failed badge state as the same-page case. Once the
        second page releases (or closes), the first page's next
        mutation recovers.

        Verifies the Web Locks namespace is shared across same-origin
        agents in the same context — which is the cross-tab story the
        multi-tab takeover plan eventually leans on. Until then, the
        OPFS SAH-pool exclusivity prevents two workers from both
        opening relationships.db, so the cross-tab story is exercised
        with page-side lock holders rather than two competing workers.
        """
        gid_a, baseline_saved_at, baseline_rel_size = (
            self._pick_folder_and_seed_group_a(folder_page, base_url_fixture)
        )
        # Open a second page in the same context. Its worker will fail
        # to acquire the OPFS pool (existing single-writer behavior),
        # but its page-side JS can still run the lock-hold helper —
        # which is all this test needs.
        url = folder_page.url
        second_page = context.new_page()
        second_page.add_init_script(_STUB_DIRECTORY_PICKER)
        try:
            second_page.goto(url, wait_until="domcontentloaded")
            # Don't wait for __dataProvider — the second tab's worker
            # boot is expected to hit ownership conflict. We just need
            # the page-side helpers from the init script.
            second_page.wait_for_function(
                "() => typeof window.__holdFolderLockForever === 'function'",
                timeout=10000,
            )
            second_page.evaluate("() => window.__holdFolderLockForever()")
            # First page attempts a mutation; write fails on the lock.
            full = folder_page.evaluate("() => window.__dataProvider.getFull()")
            rids_b = [f["record_id"] for f in full[3:6]]
            folder_page.evaluate(
                "(rids) => window.__dataProvider.createGroup({"
                "name: 'Cross-tab lock test B', note: '', fellow_record_ids: rids})",
                rids_b,
            )
            folder_page.wait_for_function(
                "() => window.__dataProvider._getFolderState()"
                "  .then(s => s.lastError && s.lastError.reason)",
                timeout=5000,
            )
            state_blocked = folder_page.evaluate(
                "() => window.__dataProvider._getFolderState()"
            )
            assert "Another window" in state_blocked["lastError"]["reason"], (
                f"cross-tab block should carry the actionable copy; "
                f"got {state_blocked['lastError']['reason']!r}"
            )
            assert state_blocked["lastSavedAt"] == baseline_saved_at, (
                f"lastSavedAt should NOT advance when blocked by second tab"
            )
            # Release from the second page. First page's next mutation
            # recovers — same retry path as the same-page test.
            second_page.evaluate("() => window.__releaseFolderLock()")
            folder_page.evaluate(
                "() => window.__dataProvider.setSetting('e2e_cross_tab_retry', 'recovered')"
            )
            folder_page.wait_for_function(
                "(before) => window.__dataProvider._getFolderState()"
                "  .then(s => s.lastSavedAt && s.lastSavedAt !== before "
                "             && (s.lastError === null || s.lastError === undefined))",
                arg=baseline_saved_at,
                timeout=5000,
            )
        finally:
            try:
                second_page.evaluate("() => window.__releaseFolderLock()")
            except Exception:
                pass
            second_page.close()
