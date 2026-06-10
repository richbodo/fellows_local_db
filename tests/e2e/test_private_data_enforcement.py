"""Private-data capability gate — DATA-LAYER enforcement.

The gate's durability guarantee is "off-folder there is no durable private
store" (plans/private_data_capability_gate.md). PR3 hid the UI surfaces; this
PR (plans/private_data_enforcement.md) makes the guarantee TRUE below the UI:
the dataProvider refuses mutating relationships.db RPCs in browse-only mode, so
a DevTools console call or a stray code path can't write durable private data.
Reads (and the legacy migration peek) still work; the two trivial prefs stay in
localStorage.

These are the NEGATIVE-invariant tests the attestation's CST rows need
(CST-PWA-PRIVATE-SNAPSHOT / -STORAGE-EVICTABLE). The happy path (mutations work
WITH a folder) is covered by tests/e2e/test_worker_rpc.py via worker_data_folder.
"""
from __future__ import annotations

import base64
import os
import sqlite3
import tempfile

# Benign workspace-identity metadata (a random UUID + device label + counters —
# no private user content). Since #248 the worker mints this ONLY onto a
# canonical folder store (on the first committed folder write), never off-folder,
# so off-folder these keys are absent and getSettings() is literally empty
# (test_off_folder_settings_are_empty below). The set is retained so folder-mode
# assertions can name the identity keys explicitly.
_IDENTITY_KEYS = {
    "workspace_uuid", "device_label", "created_at", "write_generation",
    "last_written_at",
}
# Keys that would represent durable private USER data/prefs — must NOT appear
# in the off-folder settings store.
_USER_PREF_KEYS = {"has_email_only", "self_email"}


def _user_keys(settings):
    return set(settings or {}) - _IDENTITY_KEYS


def _settings_from_db_bytes(b64):
    """Open a base64-encoded SQLite image READ-ONLY with stdlib sqlite3 and
    return its `settings` table as a dict.

    The byte-level oracle (#248): this asserts on what is DURABLY written to the
    folder file on disk — the bytes the worker exported via poolUtil.exportFile —
    not the worker's in-RAM view returned by getSettings(). Opening the bytes as
    a real SQLite DB also proves the export produced a valid DB with the expected
    schema, not just plausible RAM. Stdlib only (no new deps); ``?mode=ro`` so the
    parse can never mutate the copy.
    """
    raw = base64.b64decode(b64)
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(raw)
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return dict(con.execute("SELECT key, value FROM settings").fetchall())
        finally:
            con.close()
    finally:
        os.unlink(path)


def _boot_browse_only(page, base_url):
    """Boot with NO folder attached → browse-only-desktop."""
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    # Let the gate resolve against the ready worker provider.
    page.wait_for_function(
        "() => window.__privateDataTier "
        "&& window.__privateDataTier.indexOf('browse-only') === 0",
        timeout=10000,
    )


def _attempt(page, expr):
    """Run an async dataProvider call; return {ok|threw, name, browseOnly}."""
    return page.evaluate(
        """async (src) => {
            const fn = new Function('return (' + src + ')()');
            try { const v = await fn(); return { ok: true, value: v }; }
            catch (e) { return { threw: true, name: e.name, browseOnly: e.browseOnly === true,
                                 message: String(e.message || e) }; }
        }""",
        expr,
    )


def test_browse_only_refuses_create_group(standalone_page, base_url_fixture):
    page = standalone_page
    _boot_browse_only(page, base_url_fixture)
    assert page.evaluate("() => window.__privateDataEnabled()") is False
    r = _attempt(page, "() => window.__dataProvider.createGroup({name:'nope', note:'', fellow_record_ids:[]})")
    assert r.get("threw") is True, r
    assert r.get("browseOnly") is True, r


def test_browse_only_refuses_import_relationships_bytes(standalone_page, base_url_fixture):
    """#252 no-bypass audit. importRelationshipsBytes (the restore path, and the
    future email-import path) must NOT durably write private data off-folder.
    Unlike createGroup/setSetting it carries no page-side refuseIfBrowseOnly and
    the worker handler has no folder guard — so a console/restore call could land
    a durable private store in the OPFS slot in browse-only mode, bypassing the
    gate (CLAUDE.md: "a gated capability whose RPC still succeeds from the
    DevTools console is not reduced"). Export is a read (fine); the import must be
    refused."""
    page = standalone_page
    _boot_browse_only(page, base_url_fixture)
    r = _attempt(
        page,
        "() => window.__dataProvider.exportRelationshipsBytes()"
        ".then(function (b) { return window.__dataProvider.importRelationshipsBytes(b); })",
    )
    assert r.get("threw") is True, f"import must be refused browse-only, got: {r}"
    assert r.get("browseOnly") is True, r


def test_worker_is_load_bearing_off_folder_via_raw_rpc(standalone_page, base_url_fixture):
    """#252 'full data-layer hardening': the WORKER itself — not just the page —
    refuses durable private writes off-folder. Calls the raw worker RPC
    (`window.__dataProvider._rpc`) directly, bypassing the page-side
    refuseIfBrowseOnly, and asserts every mutating relationships.db op is refused
    at the OPFS owner with a BrowseOnlyError. This is the load-bearing half: a
    DevTools-console call can't write durable private data in browse-only mode
    (CLAUDE.md — capability reductions enforce at the data layer, never UI-only)."""
    page = standalone_page
    _boot_browse_only(page, base_url_fixture)
    ops = [
        ("createGroup", "{name:'x', note:'', fellow_record_ids:[]}"),
        ("updateGroup", "{id:1, patch:{name:'y'}}"),
        ("deleteGroup", "{id:1}"),
        ("setSetting", "{key:'self_email', value:'me@example.com'}"),
        ("importRelationshipsBytes", "{bytes:new Uint8Array(0)}"),
    ]
    for op, args in ops:
        r = _attempt(page, f"() => window.__dataProvider._rpc.call('{op}', {args})")
        assert r.get("threw") is True, (op, r)
        # name survives the worker→page error envelope (errorName); the
        # browseOnly boolean does not, so key on name (set by the worker guard).
        assert r.get("name") == "BrowseOnlyError", (op, r)


def test_browse_only_refuses_set_setting(standalone_page, base_url_fixture):
    page = standalone_page
    _boot_browse_only(page, base_url_fixture)
    r = _attempt(page, "() => window.__dataProvider.setSetting('self_email', 'me@example.com')")
    assert r.get("threw") is True, r
    assert r.get("browseOnly") is True, r


def test_browse_only_reads_still_work(standalone_page, base_url_fixture):
    """Reads + the legacy migration peek are never gated."""
    page = standalone_page
    _boot_browse_only(page, base_url_fixture)
    groups = _attempt(page, "() => window.__dataProvider.listGroups()")
    settings = _attempt(page, "() => window.__dataProvider.getSettings()")
    assert groups.get("ok") is True and groups.get("value") == [], groups
    # Reads succeed; no durable private USER data/prefs (identity metadata aside).
    assert settings.get("ok") is True, settings
    assert _user_keys(settings.get("value")) == set(), settings


def test_no_durable_private_write_when_browse_only(standalone_page, base_url_fixture):
    """The core durability invariant: a browse-only mutation attempt writes
    nothing durable. The guard refuses createGroup at the page layer (before any
    worker write), and the worker mints no identity stamp off-folder — so groups
    AND settings stay empty. (In-session, not reload-based: reloading the same
    context races the OPFS single-owner lock; since the write is refused at the
    guard, no write occurs regardless of reload.)"""
    page = standalone_page
    _boot_browse_only(page, base_url_fixture)
    _attempt(page, "() => window.__dataProvider.createGroup({name:'should-not-persist', note:'', fellow_record_ids:[]})")
    groups = _attempt(page, "() => window.__dataProvider.listGroups()")
    settings = _attempt(page, "() => window.__dataProvider.getSettings()")
    assert groups.get("value") == [], groups
    assert _user_keys(settings.get("value")) == set(), settings


def test_prefs_stay_localstorage_only_off_folder(standalone_page, base_url_fixture):
    """The two trivial prefs must not land in the durable settings store
    off-folder — the boot reconciles are gated on privateDataEnabled()."""
    page = standalone_page
    _boot_browse_only(page, base_url_fixture)
    settings = _attempt(page, "() => window.__dataProvider.getSettings()").get("value") or {}
    leaked = _USER_PREF_KEYS & set(settings)
    assert leaked == set(), f"prefs leaked into durable store off-folder: {leaked} in {settings}"


def test_off_folder_settings_are_empty(standalone_page, base_url_fixture):
    """The strongest reading of CST-PWA-STORAGE-EVICTABLE: browse-only is
    localStorage-only, so the durable OPFS settings store is *literally* empty —
    not even benign workspace-identity metadata. Since #248 the worker mints
    identity only onto a canonical folder store (see
    test_folder_store_carries_identity_after_write); off-folder it never runs."""
    page = standalone_page
    _boot_browse_only(page, base_url_fixture)
    settings = _attempt(page, "() => window.__dataProvider.getSettings()").get("value")
    assert settings == {}, settings


def test_folder_store_carries_identity_after_write(worker_data_folder):
    """The flip side of #248: a folder store IS canonical, so identity is minted
    onto it on the first committed folder write. This is the row the chooser
    ranks by (CST-PWA-NO-SYNC), so it must survive the off-folder gating. Drives
    a real mutation through the worker, then asserts workspace_uuid + the write
    generation are present in the folder store's settings."""
    wd = worker_data_folder
    assert wd.page.evaluate("() => window.__privateDataEnabled()") is True
    full = wd.get_full_fellows()
    wd.create_group("identity check", fellow_record_ids=[full[0]["record_id"]])
    settings = wd.list_settings() or {}
    assert "workspace_uuid" in settings, settings
    assert settings.get("workspace_uuid"), settings
    # write_generation is bumped on each committed folder write (>= 1 here).
    assert int(settings.get("write_generation", "0")) >= 1, settings


def test_folder_attached_allows_create_group(worker_data_folder):
    """Sanity: with a verified folder, the same op the browse-only tests refuse
    succeeds (mutations are gated on the folder, not broken)."""
    wd = worker_data_folder
    assert wd.page.evaluate("() => window.__privateDataEnabled()") is True
    full = wd.get_full_fellows()
    g = wd.create_group("ok with folder", fellow_record_ids=[full[0]["record_id"]])
    assert isinstance(g["id"], int)
    assert g["name"] == "ok with folder"


# ===== Byte-level oracle (#248): assert what is durably ON DISK ==============
# test_folder_store_carries_identity_after_write (above) asserts the worker's
# in-RAM view via getSettings(). These two open the actual bytes the worker
# exported to the folder file (and its backup ring) as a real SQLite DB — the
# file-content checks the manual folder QA performs by hand ("inspect via
# Restore/inspect, or DevTools"). They exercise a different link in the chain:
# the export, not just the live connection.


def test_folder_file_on_disk_carries_identity(worker_data_folder):
    """#248 byte-level: identity is in the bytes exported to the canonical folder
    file, not only in the worker's RAM. Drive a real mutation, then open the
    on-disk Fellows/relationships.db and assert the identity row is durably
    present. Covers the manual QA item "fresh folder attach → identity present in
    the folder's relationships.db". Folder writes are awaited inside the mutation
    handler, so by the time create_group returns the export has landed — no poll
    needed."""
    wd = worker_data_folder
    full = wd.get_full_fellows()
    wd.create_group("disk identity", fellow_record_ids=[full[0]["record_id"]])
    probe = wd.page.evaluate("() => window.__probeFolderDbBytes()")
    assert probe["relDbBase64"], f"no relationships.db landed in the folder: {probe}"
    on_disk = _settings_from_db_bytes(probe["relDbBase64"])
    assert on_disk.get("workspace_uuid"), on_disk
    # _ensureWorkspaceIdentity mints write_generation '0', then
    # _stampWriteGeneration bumps it before the export — so the file shows >= 1.
    assert int(on_disk.get("write_generation", "0")) >= 1, on_disk


def test_folder_backup_on_disk_carries_identity(worker_data_folder):
    """#248 + CST-PWA-NO-SYNC byte-level: the folder backup ring also carries
    identity, so a restored backup keeps its canonical-copy ranking
    (write_generation). Force exactly one snapshot via an export/import
    round-trip (importRelationshipsBytes always snapshots-before-import), then
    open the latest folder bak.* as a SQLite DB and assert the identity row is in
    its bytes. Covers the manual QA item "backup ring in folder mode still
    carries identity"."""
    wd = worker_data_folder
    full = wd.get_full_fellows()
    wd.create_group("backup identity", fellow_record_ids=[full[0]["record_id"]])
    wd.page.evaluate(
        """async () => {
            var dp = window.__dataProvider;
            var bytes = await dp.exportRelationshipsBytes();
            await dp.importRelationshipsBytes(bytes);
        }"""
    )
    probe = wd.page.evaluate("() => window.__probeFolderDbBytes()")
    assert probe["backupNames"], f"no folder backup was written: {probe}"
    assert probe["latestBackupBase64"], probe
    backup = _settings_from_db_bytes(probe["latestBackupBase64"])
    assert backup.get("workspace_uuid"), backup


# ===== Permission-lifecycle: lapse → reduce → reconnect → restore ===========
# The OPFS-backed fake folder handle always reports 'granted', so a real
# permission lapse can't be reproduced. The worker carries a fail-closed e2e
# seam (__e2eForceFolderPermission) that forces queryPermission to a
# capability-REDUCING state, letting this exercise the app's HANDLING of the
# reconnect / re-grant flow. The one thing it can't assert is that real Chrome
# actually returns 'prompt' after a restart — a browser-behavior fact, the
# documented manual residual (PR #251 maintainer QA).


def test_permission_lapse_reduces_capability_then_reconnect_restores(worker_data_folder):
    """A verified folder whose permission lapses (the 'prompt' a real OS handle
    returns after a browser restart) must drop the app to browse-only — the gate
    keys off live permission, not a one-time attach — and the real reconnect()
    path must restore private-folder once permission is re-granted."""
    wd = worker_data_folder
    page = wd.page
    # Precondition: folder attached, permission granted, private data live.
    assert page.evaluate("() => window.__privateDataEnabled()") is True
    pre = page.evaluate("() => window.__folderController.getState()")
    assert pre["permission"] == "granted", pre

    # 1) Simulate the lapse. Detection: badge 'inaccessible', and the gate
    #    reduces capability to browse-only (no durable private store while the
    #    folder is unverified).
    page.evaluate("() => window.__dataProvider._e2eForceFolderPermission('prompt')")
    lapsed = page.evaluate("() => window.__folderController.getState()")
    assert lapsed["permission"] == "prompt", lapsed
    assert page.evaluate(
        "(s) => window.__folderController.badge(s)", lapsed
    ) == "inaccessible"
    tier = page.evaluate(
        "async () => { await window.__updatePrivateDataGate(); return window.__privateDataTier; }"
    )
    assert tier == "browse-only-desktop", tier
    assert page.evaluate("() => window.__privateDataEnabled()") is False

    # 2) User re-grants: requestPermission succeeds and queryPermission reports
    #    'granted' again (modelled by clearing the forced lapse). The real
    #    reconnect() path (page requestPermission → worker re-query) restores
    #    private-folder.
    page.evaluate("() => window.__dataProvider._e2eForceFolderPermission(null)")
    restored = page.evaluate("async () => await window.__folderController.reconnect()")
    assert restored["permission"] == "granted", restored
    tier2 = page.evaluate(
        "async () => { await window.__updatePrivateDataGate(); return window.__privateDataTier; }"
    )
    assert tier2 == "private-folder", tier2
    assert page.evaluate("() => window.__privateDataEnabled()") is True


# ===== Stranded OPFS data → migration prompt (CST-PWA-STORAGE-EVICTABLE) ======
# The "Avoided" claim — browse-only is localStorage-only, nothing durable in
# OPFS off-folder — holds for a never-had-a-folder install but NOT for a
# browse-only state reached via a dropped folder handle: the relationships rows
# the worker hydrated into OPFS during the folder session linger there. The
# honest handling (Framing A: "Mitigated", not "Avoided") is to surface that
# stranded data with a dedicated 'migrate' banner so the user moves it onto disk
# before the browser can evict it — never to silently leave it, and never to
# wipe it (that would be data loss).


def test_stranded_opfs_groups_fire_migration_prompt(worker_data_folder):
    """Groups in OPFS with NO folder attached (handle dropped — Lock, or the
    'no-handle' a real OS returns after a browser restart) must surface the
    'migrate' folder banner, not the generic set-up nudge and not silence."""
    wd = worker_data_folder
    page = wd.page
    # 1) Folder attached → create a group so OPFS holds private data.
    page.evaluate(
        "() => window.__dataProvider.createGroup({name:'Stranded', note:'', fellow_record_ids:[]})"
    )
    assert page.evaluate("() => window.__dataProvider.countRelationships()")["groups"] >= 1

    # 2) Drop the folder handle. clearFolderHandle resets the handle ref only,
    #    never the OPFS db, so the rows linger off-folder (the stranded state).
    page.evaluate("() => window.__dataProvider._clearFolderHandle()")
    assert page.evaluate("() => window.__folderController.getState()")["hasHandle"] is False
    assert page.evaluate("() => window.__dataProvider.countRelationships()")["groups"] >= 1

    # 3) The banner must show the MIGRATE variant — and name the group count
    #    ("Save your 1 saved group"), the personalized rescue copy restored from
    #    PR #240 (its merge was dropped from main; see fix/restore-pr240-…).
    page.evaluate("() => window.__refreshFolderPushBanner()")
    page.wait_for_function(
        "() => { var b = document.getElementById('folder-push-banner');"
        " return b && !b.classList.contains('hidden')"
        " && /save your 1 saved group\\b/i.test(b.textContent); }",
        timeout=5000,
    )
    cta = page.evaluate("() => document.getElementById('folder-push-cta').textContent")
    assert "Save my groups" in cta, cta


def test_clean_no_folder_shows_generic_nudge_not_migrate(worker_data_folder):
    """Negative half: with NO stranded data, the banner is the generic 'set up a
    folder' nudge — never the 'migrate' variant. Don't cry wolf about data that
    isn't there."""
    wd = worker_data_folder
    page = wd.page
    page.evaluate("() => window.__dataProvider._clearFolderHandle()")
    assert page.evaluate("() => window.__folderController.getState()")["hasHandle"] is False
    counts = page.evaluate("() => window.__dataProvider.countRelationships()")
    assert not (counts and (counts["groups"] or counts["members"]
                            or counts["tags"] or counts["notes"])), counts
    page.evaluate("() => window.__refreshFolderPushBanner()")
    page.wait_for_function(
        "() => { var b = document.getElementById('folder-push-banner');"
        " return b && !b.classList.contains('hidden')"
        " && /need a data folder/i.test(b.textContent); }",
        timeout=5000,
    )
    banner_text = page.evaluate(
        "() => document.getElementById('folder-push-banner').textContent"
    )
    assert "Save your" not in banner_text, banner_text
    assert "only in browser storage" not in banner_text, banner_text


def test_stranded_opfs_groups_migrate_into_freshly_picked_folder(worker_data_folder):
    """END-TO-END migration (restored from PR #240, whose merge was silently
    dropped from main before #271 re-added the prompt generically): when the user
    acts on the migrate prompt and picks a fresh folder, the groups stranded in
    OPFS are *copied into* the folder — the data survives, the on-disk file holds
    it, and the gate reopens.

    #271's tests only assert the prompt *fires*; this covers the 'does the
    migration actually complete' path the pre-ship plan (§4.2) flags as the
    highest-risk one with no automated equivalent."""
    wd = worker_data_folder
    page = wd.page

    # 1) Folder attached → create two groups; they land in OPFS and are written
    #    through to the folder.
    page.evaluate(
        "() => window.__dataProvider.createGroup({name:'M1', note:'', fellow_record_ids:[]})"
    )
    page.evaluate(
        "() => window.__dataProvider.createGroup({name:'M2', note:'', fellow_record_ids:[]})"
    )
    assert page.evaluate("() => window.__dataProvider.countRelationships()")["groups"] == 2

    # 2) Strand the data: drop the folder handle AND clear the on-disk folder, so
    #    re-picking lands on a FRESH empty folder and exercises the OPFS→folder
    #    write (migration) path rather than re-adopting an existing store. Neither
    #    call touches the OPFS buffer, so its rows linger (the stranded state).
    page.evaluate("() => window.__dataProvider._clearFolderHandle()")
    page.evaluate("() => window.__resetE2EUserFolderMin()")
    assert page.evaluate("() => window.__folderController.getState()")["hasHandle"] is False
    assert page.evaluate("() => window.__dataProvider.countRelationships()")["groups"] == 2

    # 3) Act on the migrate prompt: pick a folder from Settings. The choose flow
    #    probes the fresh folder, writes the current OPFS (groups included) into
    #    it (writeNow), and flips the gate — all without a reload.
    page.evaluate("() => { location.hash = '#/settings'; }")
    page.locator("#settings-folder-choose").wait_for(state="visible", timeout=5000)
    page.locator("#settings-folder-choose").click()
    page.wait_for_function(
        "() => { var t = document.querySelector('#settings-folder-badge .settings-folder-badge-text');"
        " return t && /Saved to/.test(t.textContent); }",
        timeout=10000,
    )

    # 4a) The groups survived the migration and are live again.
    assert page.evaluate("() => window.__dataProvider.listGroups().then(g => g.length)") == 2
    # 4b) The gate reopened (private surfaces are back).
    page.wait_for_function(
        "() => document.body && !document.body.classList.contains('no-private-data')",
        timeout=8000,
    )
    # 4c) Byte-of-truth: the freshly-picked folder file actually holds the two
    #     groups — not just the worker's in-RAM view.
    scan = page.evaluate(
        """async () => {
            const root = await navigator.storage.getDirectory();
            const parent = await root.getDirectoryHandle('__e2e_user_folder__');
            return await window.__folderController.scanCandidates(parent);
        }"""
    )
    fellows = [c for c in scan["candidates"] if c["subfolderName"] == "Fellows"]
    assert fellows and fellows[0]["groups"] == 2, scan


# ===== Private-DB export is a real portability bridge (round-trip) ============
# CST-PWA-PRIVATE-SNAPSHOT and CST-PWA-NO-SYNC both lean on the timestamped `.db`
# export as the manual cross-install/cross-device portability bridge. Until now
# that handling was asserted only in prose — no attestation row cited a test that
# the export actually produces a valid, re-importable artifact. This is that
# executable evidence: export the live Private DB to bytes, confirm they're a
# valid SQLite file carrying the data, and re-import them so the counts round-trip.
# Whether the export should become a first-class, gated invariant (its own AC,
# rather than evidence cited inside two CST rows) is tracked in #272.


def test_private_db_export_round_trips(worker_data_folder):
    """Export → valid SQLite bytes carrying the data → re-import → row counts
    match. Proves the `.db` export is a genuine portability bridge, not just a
    claim. (Re-importing the same bytes is idempotent; import is allowed here
    because a folder is attached — off-folder it is refused, see above.)"""
    wd = worker_data_folder
    page = wd.page
    page.evaluate(
        "() => window.__dataProvider.createGroup({name:'Portable', note:'', fellow_record_ids:[]})"
    )
    before = page.evaluate("() => window.__dataProvider.countRelationships()")
    assert before["groups"] >= 1, before
    result = page.evaluate(
        """async () => {
          const dp = window.__dataProvider;
          const bytes = await dp.exportRelationshipsBytes();
          const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
          const insp = await dp.inspectRelationshipsBytes(u8);
          await dp.importRelationshipsBytes(u8);              // re-import the export
          const after = await dp.countRelationships();
          return {
            header: new TextDecoder().decode(u8.slice(0, 15)),
            size: u8.length,
            inspectValid: !!(insp && insp.valid),
            inspectGroups: insp && insp.counts ? insp.counts.groups : null,
            afterGroups: after.groups,
          };
        }"""
    )
    assert result["header"] == "SQLite format 3", result      # readable by any SQLite tool
    assert result["size"] > 0, result
    assert result["inspectValid"] is True, result
    assert result["inspectGroups"] >= 1, result               # the export carries the data
    assert result["afterGroups"] == before["groups"], result  # round-trips cleanly
