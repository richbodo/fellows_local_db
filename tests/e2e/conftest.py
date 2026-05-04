"""Shared fixtures for e2e tests."""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from app.server import PORT

# App treats non-standalone browser tabs as install-only (no directory). E2E that
# needs the directory must emulate installed PWA display mode before navigation.
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
          // Drain any in-flight boot writes (reconcileHasEmailFilterOnBoot,
          // reconcileSelfEmailOnBoot). Both fire on bootDirectoryAsApp and
          // are fire-and-forget; we poll up to 1s for has_email_only to
          // appear (it's the marker that reconcile has executed at least
          // once on this page load).
          for (var attempt = 0; attempt < 20; attempt++) {
            var probe = await dp.getSetting('has_email_only');
            if (probe === '0' || probe === '1') break;
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
