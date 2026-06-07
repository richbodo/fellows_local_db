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
