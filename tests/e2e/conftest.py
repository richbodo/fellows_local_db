"""Shared fixtures for e2e tests."""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from app.server import PORT

# App treats non-standalone browser tabs as install-only (no directory). E2E that
# needs the directory must emulate installed PWA display mode before navigation.
#
# Also forces the anchor-download fallback in ``downloadBlob`` by removing
# ``window.showSaveFilePicker``. The picker triggers a native OS save dialog
# that Playwright's ``page.expect_download`` does not fire for — so any test
# using ``expect_download`` (group exports, reset-everything backup) hangs
# until timeout. Removing the picker forces ``downloadBlob``'s
# ``triggerAnchorDownload`` fallback path, which Playwright reliably catches.
# No e2e test specifically asserts picker UX; this stub keeps the suite
# deterministic across Playwright/Chromium upgrades.
_STANDALONE_DISPLAY_INIT = """
(function () {
  var orig = window.matchMedia.bind(window);
  window.matchMedia = function (q) {
    q = String(q);
    if (q.indexOf('display-mode: standalone') !== -1) {
      return {
        matches: true,
        media: q,
        addEventListener: function () {},
        removeEventListener: function () {}
      };
    }
    return orig(q);
  };
  try { delete window.showSaveFilePicker; } catch (e) {
    try { window.showSaveFilePicker = undefined; } catch (e2) {}
  }
})();
"""


@pytest.fixture(scope="session", autouse=True)
def _e2e_server(app_server):
    """Ensure app server is running for e2e tests (uses session app_server from tests/conftest.py)."""
    return app_server


@pytest.fixture(scope="session")
def base_url_fixture():
    """Local dev URL, or ``E2E_BASE_URL`` when set (no trailing slash)."""
    env = (os.environ.get("E2E_BASE_URL") or "").strip().rstrip("/")
    if env:
        return env
    return f"http://127.0.0.1:{PORT}"


@pytest.fixture
def standalone_page(context):
    """Playwright page with PWA standalone display mode faked for directory/detail tests."""
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    try:
        yield page
    finally:
        page.close()


# ===== Worker-RPC test data helper ==========================================
# Phase 1 of plans/local_first_worker_architecture.md retired the dev
# server's /api/groups + /api/settings routes — relationships data lives in
# the worker-owned OPFS-stored relationships.db. Tests that previously did
# HTTP setup (POST /api/groups) now drive the same code path the real app
# uses by calling window.__dataProvider methods inside the page via
# page.evaluate. This catches integration bugs that a parallel test-only
# worker spawner would miss.

_WAIT_FOR_DATA_PROVIDER = """
async () => {
  // window.__dataProvider is exposed by app.js's pickDataProvider after
  // worker init returns. Poll up to 10s — first-install boots fetch
  // /fellows.db which can take a beat on cold cache.
  for (var i = 0; i < 100; i++) {
    if (window.__dataProvider && typeof window.__dataProvider.listGroups === 'function') {
      // Wait an extra tick so the kind is settled (avoids races with
      // the auth-failure-fallback path that swaps providers mid-boot).
      await new Promise(function (r) { setTimeout(r, 50); });
      return window.__dataProvider.kind || 'unknown';
    }
    await new Promise(function (r) { setTimeout(r, 100); });
  }
  throw new Error('window.__dataProvider not ready after 10s');
}
"""


class WorkerDataHelper:
    """Sync wrapper over window.__dataProvider for e2e fixture setup.

    Each method runs a single page.evaluate against the live worker. The
    page must already have window.__dataProvider populated — call wait()
    once after navigation, or use the worker_data fixture which does it
    for you.
    """

    def __init__(self, page):
        self.page = page

    def wait(self):
        """Block until window.__dataProvider is populated.

        Returns the provider kind ('worker' or 'api+idb'). Tests that need
        worker-backed mutations should assert kind == 'worker' after this
        and skip otherwise (Playwright's chromium has historically been
        the worker path; if it ever isn't, that's a real regression).
        """
        return self.page.evaluate(_WAIT_FOR_DATA_PROVIDER)

    def provider_kind(self):
        return self.page.evaluate("() => (window.__dataProvider && window.__dataProvider.kind) || null")

    def list_groups(self):
        """Return [{id, name, note, count, ...}, ...] from the worker."""
        return self.page.evaluate("() => window.__dataProvider.listGroups()")

    def create_group(self, name, fellow_record_ids=(), note=""):
        """Create a group via worker RPC. Returns the full group record."""
        payload = {
            "name": name,
            "note": note,
            "fellow_record_ids": list(fellow_record_ids),
        }
        return self.page.evaluate(
            "(p) => window.__dataProvider.createGroup(p)",
            payload,
        )

    def update_group(self, group_id, patch):
        """PATCH-equivalent: applies the keys present in `patch`."""
        return self.page.evaluate(
            "(args) => window.__dataProvider.updateGroup(args.id, args.patch)",
            {"id": group_id, "patch": patch},
        )

    def delete_group(self, group_id):
        return self.page.evaluate(
            "(id) => window.__dataProvider.deleteGroup(id)",
            group_id,
        )

    def get_group(self, group_id):
        return self.page.evaluate(
            "(id) => window.__dataProvider.getGroup(id)",
            group_id,
        )

    def list_settings(self):
        return self.page.evaluate("() => window.__dataProvider.getSettings()")

    def get_setting(self, key):
        return self.page.evaluate(
            "(k) => window.__dataProvider.getSetting(k)",
            key,
        )

    def set_setting(self, key, value):
        return self.page.evaluate(
            "(args) => window.__dataProvider.setSetting(args.k, args.v)",
            {"k": key, "v": value},
        )

    def get_full_fellows(self):
        """Return the full /api/fellows?full=1 equivalent via worker getFull.

        Used by tests that need real record_ids to feed into create_group.
        """
        return self.page.evaluate("() => window.__dataProvider.getFull()")

    def wipe_relationships(self):
        """Delete every group + clear every setting via worker RPC.

        Equivalent to the previous _wipe_groups + _wipe_settings HTTP
        helpers; used by per-test autouse fixtures so tests are
        order-independent.

        Race quirk this handles: app.js's reconcileHasEmailFilterOnBoot
        is fire-and-forget — on boot, if `has_email_only` isn't in
        settings yet, it writes the localStorage default ('1') in the
        background. If wipe runs before that promise resolves, the
        write lands AFTER the wipe and the test sees a leaked setting.
        We wait up to 1s for the reconcile-driven write to land
        (getSetting returns non-null) before clearing, so the wipe
        catches it.
        """
        return self.page.evaluate("""
        async () => {
          var dp = window.__dataProvider;
          if (!dp) return { groups_deleted: 0, settings_cleared: 0 };
          // Drain any in-flight boot writes that are fire-and-forget
          // (reconcileHasEmailFilterOnBoot, reconcileSelfEmailOnBoot,
          // maybeRunOrphanSoftScan). Each writes a setting after boot.
          // We poll up to 1s for has_email_only AND orphan_scan_done
          // to land; if either is still missing after 1s the wipe
          // proceeds anyway — the test just inherits the leaked key.
          for (var attempt = 0; attempt < 20; attempt++) {
            var probe = await dp.getSetting('has_email_only');
            var orphan = await dp.getSetting('orphan_scan_done');
            if ((probe === '0' || probe === '1') && orphan === '1') break;
            await new Promise(function (r) { setTimeout(r, 50); });
          }
          var groups = await dp.listGroups();
          var gn = 0;
          for (var i = 0; i < (groups || []).length; i++) {
            try { await dp.deleteGroup(groups[i].id); gn++; } catch (e) {}
          }
          var bag = await dp.getSettings();
          var sn = 0;
          for (var k in (bag || {})) {
            try { await dp.setSetting(k, ''); sn++; } catch (e) {}
          }
          return { groups_deleted: gn, settings_cleared: sn };
        }
        """)


def make_worker_data(page, base_url):
    """Construct a WorkerDataHelper after navigating to base_url and waiting
    for the worker-backed dataProvider. Used by tests that want explicit
    control over the navigation step (e.g. multi-page-load flows)."""
    page.goto(base_url + "/", wait_until="domcontentloaded")
    helper = WorkerDataHelper(page)
    helper.wait()
    return helper


@pytest.fixture
def worker_data(standalone_page, base_url_fixture):
    """Helper that navigates to the directory, waits for window.__dataProvider,
    and exposes wipe_relationships / create_group / set_setting methods that
    drive the live worker via page.evaluate.

    Wipes relationships state on entry AND exit so tests are
    order-independent. Yields the helper; the caller can also drive the
    same `standalone_page` for any UI-side assertions.
    """
    helper = make_worker_data(standalone_page, base_url_fixture)
    helper.wipe_relationships()
    try:
        yield helper
    finally:
        try:
            helper.wipe_relationships()
        except Exception:
            pass


# Minimal showDirectoryPicker stub for fixtures that need a VERIFIED folder
# attached so privateDataEnabled() is true. (The full-featured stub with
# probe/seed/lock affordances lives in test_user_folder_storage.py; this is
# the lean version conftest needs to attach a folder via the real UI path.)
_FOLDER_PICKER_STUB_MIN = """
(function () {
  var STUB = '__e2e_user_folder__';
  window.showDirectoryPicker = async function () {
    var root = await navigator.storage.getDirectory();
    return await root.getDirectoryHandle(STUB, { create: true });
  };
  window.__resetE2EUserFolderMin = async function () {
    var root = await navigator.storage.getDirectory();
    try { await root.removeEntry(STUB, { recursive: true }); } catch (e) {}
  };
})();
"""


@pytest.fixture
def worker_data_folder(standalone_page, base_url_fixture):
    """Like ``worker_data`` but with a VERIFIED data folder attached, so
    ``privateDataEnabled()`` is true and ``body`` carries no
    ``no-private-data`` class.

    Under the private-data capability gate
    (plans/private_data_capability_gate.md) the group / notes / private-
    settings surfaces are only available when a real durable folder backs
    the store. Tests that exercise those surfaces must boot with a folder
    attached — this fixture is their precondition. It attaches via the same
    Settings UI path real users take (``#settings-folder-choose`` → "Saved
    to"), so it exercises the production attach, not a private back door.

    Drop-in for ``worker_data``: yields a ``WorkerDataHelper`` with the same
    API (``.page``, ``wipe_relationships``, ``create_group``, ``set_setting``).
    Skips (does not fail) when the worker provider is unavailable, matching
    ``folder_page``.
    """
    page = standalone_page
    page.add_init_script(_FOLDER_PICKER_STUB_MIN)
    helper = make_worker_data(page, base_url_fixture)
    if page.evaluate("() => !!(window.__dataProvider && window.__dataProvider.kind === 'worker')") is not True:
        pytest.skip("folder-gated tests need the worker provider")
    # Clean folder + relationships state for an order-independent baseline.
    page.evaluate("() => window.__dataProvider._clearFolderHandle()")
    page.evaluate("() => window.__resetE2EUserFolderMin()")
    helper.wipe_relationships()
    # Attach a verified folder via the real Settings UI path.
    page.goto(base_url_fixture + "/#/settings", wait_until="domcontentloaded")
    page.locator("#settings-folder-choose").wait_for(state="visible", timeout=5000)
    page.locator("#settings-folder-choose").click()
    # Wait for the attach to actually PERSIST the handle before leaving the
    # page — the badge text is present from the start, so badge-visibility
    # is not a completion signal; folder state's hasHandle is.
    page.wait_for_function(
        "async () => { try { var s = await window.__folderController.getState();"
        " return !!s.hasHandle; } catch (e) { return false; } }",
        timeout=10000,
    )
    # Re-boot the directory so the gate re-resolves with the folder present
    # (updatePrivateDataGate runs on boot + after mutations); wait for the
    # gate to flip open.
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    helper.wait()
    page.wait_for_function(
        "() => document.body && !document.body.classList.contains('no-private-data')",
        timeout=8000,
    )
    try:
        yield helper
    finally:
        try:
            helper.wipe_relationships()
            page.evaluate("() => window.__resetE2EUserFolderMin()")
        except Exception:
            pass


def attach_verified_folder(page, base_url):
    """Attach a verified data folder via the real Settings UI path so
    ``privateDataEnabled()`` flips true (``body`` loses ``.no-private-data``).

    Precondition: ``_FOLDER_PICKER_STUB_MIN`` installed via
    ``add_init_script`` before the page's first navigation, the worker
    provider live, and relationships state already wiped by the caller.
    Reusable from both fixtures and page-based tests.
    """
    page.evaluate("() => window.__dataProvider._clearFolderHandle()")
    page.evaluate("() => window.__resetE2EUserFolderMin && window.__resetE2EUserFolderMin()")
    page.goto(base_url + "/#/settings", wait_until="domcontentloaded")
    page.locator("#settings-folder-choose").wait_for(state="visible", timeout=5000)
    page.locator("#settings-folder-choose").click()
    page.wait_for_function(
        "async () => { try { var s = await window.__folderController.getState();"
        " return !!s.hasHandle; } catch (e) { return false; } }",
        timeout=10000,
    )
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && typeof window.__dataProvider.listGroups === 'function'",
        timeout=10000,
    )
    page.wait_for_function(
        "() => document.body && !document.body.classList.contains('no-private-data')",
        timeout=8000,
    )


@pytest.fixture
def folder_attached_page(page, base_url_fixture):
    """A Playwright ``page`` with a VERIFIED folder attached
    (``privateDataEnabled()`` true). For page-based tests that exercise
    group / composer-rail surfaces which, under the capability gate, require
    a folder. Yields the page; the attached folder persists across the
    test's own re-navigations (the handle lives in IndexedDB)."""
    page.add_init_script(_FOLDER_PICKER_STUB_MIN)
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && typeof window.__dataProvider.listGroups === 'function'",
        timeout=10000,
    )
    if page.evaluate(
        "() => !!(window.__dataProvider && window.__dataProvider.kind === 'worker')"
    ) is not True:
        pytest.skip("folder-gated tests need the worker provider")
    page.evaluate(
        "async () => { var dp = window.__dataProvider; var gs = await dp.listGroups();"
        " for (var i=0;i<gs.length;i++){ try{ await dp.deleteGroup(gs[i].id); }catch(e){} }"
        " var bag = await dp.getSettings(); for (var k in bag){ try{ await dp.setSetting(k,''); }catch(e){} } }"
    )
    attach_verified_folder(page, base_url_fixture)
    try:
        yield page
    finally:
        try:
            page.evaluate("() => window.__resetE2EUserFolderMin()")
        except Exception:
            pass
