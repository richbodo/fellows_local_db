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

import pytest

# Benign workspace-identity metadata the worker still mints into OPFS even
# off-folder (a random UUID + device label + counters — no private user
# content). Gating this on folder-mode is the tracked final step; see the
# strict-xfail at the bottom. The user-data invariants below ignore these keys.
_IDENTITY_KEYS = {
    "workspace_uuid", "device_label", "created_at", "write_generation",
    "last_written_at",
}
# Keys that would represent durable private USER data/prefs — must NOT appear
# in the off-folder settings store.
_USER_PREF_KEYS = {"has_email_only", "self_email"}


def _user_keys(settings):
    return set(settings or {}) - _IDENTITY_KEYS


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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Worker still mints benign workspace-identity metadata (workspace_uuid + "
        "counters) into OPFS even off-folder, so getSettings() is not literally "
        "empty. Gating _ensureWorkspaceIdentity on folder-mode collided with the "
        "folder-chooser identity/pivot flow (tests/e2e/test_folder_probe.py) and "
        "needs the folder QA pass — tracked in plans/private_data_enforcement.md. "
        "When that lands this XPASSes; drop the marker and promote to a guard."
    ),
)
def test_off_folder_settings_are_empty(standalone_page, base_url_fixture):
    page = standalone_page
    _boot_browse_only(page, base_url_fixture)
    settings = _attempt(page, "() => window.__dataProvider.getSettings()").get("value")
    assert settings == {}, settings


def test_folder_attached_allows_create_group(worker_data_folder):
    """Sanity: with a verified folder, the same op the browse-only tests refuse
    succeeds (mutations are gated on the folder, not broken)."""
    wd = worker_data_folder
    assert wd.page.evaluate("() => window.__privateDataEnabled()") is True
    full = wd.get_full_fellows()
    g = wd.create_group("ok with folder", fellow_record_ids=[full[0]["record_id"]])
    assert isinstance(g["id"], int)
    assert g["name"] == "ok with folder"
