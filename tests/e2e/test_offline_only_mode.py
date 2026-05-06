"""E2E: session-expired / 401 response serves cached data instead of booting to the email gate.

PR #50 ("install once, works forever"): a stale session must not lock a
user out of data they already downloaded. The implementation moved with
Phase 1 of plans/local_first_worker_architecture.md — the directory
data source is now the worker-owned fellows.db, not /api/fellows
directly. The user-visible invariant is unchanged. To trigger the
fallback path post-cutover both /fellows.db (worker source) AND
/api/fellows (api+idb fallback source) need to fail; the IDB cache
remains the third-tier fallback that backs invariant 10 until Phase 6
retires it.
"""
import json

import pytest
from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


API_FELLOWS = "**/api/fellows**"
FELLOWS_DB = "**/fellows.db"


def _seed_indexeddb_with_fellows(page, fellows):
    """Prime the fellows-local-db IndexedDB store with a known payload.

    Runs before any network request — the app's boot chain will find this
    cache when it tries to fall back after a 401.
    """
    script = """
        async (fellows) => {
            return new Promise((resolve, reject) => {
                const req = indexedDB.open('fellows-local-db', 1);
                req.onupgradeneeded = () => {
                    const db = req.result;
                    if (!db.objectStoreNames.contains('meta')) {
                        db.createObjectStore('meta', { keyPath: 'id' });
                    }
                };
                req.onsuccess = () => {
                    const db = req.result;
                    const tx = db.transaction('meta', 'readwrite');
                    tx.objectStore('meta').put({ id: 'allFellows', data: fellows });
                    tx.oncomplete = () => { db.close(); resolve(true); };
                    tx.onerror = () => reject(tx.error);
                };
                req.onerror = () => reject(req.error);
            });
        }
    """
    page.evaluate(script, fellows)


def _make_standalone_page(context):
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    page.add_init_script(
        "window.localStorage.setItem('fellows_authenticated_once', '1');"
    )
    return page


SAMPLE_FELLOWS = [
    {
        "record_id": "cached-1",
        "slug": "ada_cached",
        "name": "Ada Cached",
        "bio_tagline": "from indexeddb",
        "has_image": 0,
        "has_contact_email": 1,
        "contact_email": "ada@example.com",
    },
    {
        "record_id": "cached-2",
        "slug": "bob_cached",
        "name": "Bob Cached",
        "bio_tagline": "from indexeddb",
        "has_image": 0,
        "has_contact_email": 0,
    },
]


class TestOfflineOnlyMode:
    """Behaviour when /api/fellows returns 401 during boot."""

    def test_401_with_cached_data_shows_directory_from_cache(self, context, base_url_fixture):
        # Post-cutover, the worker stores fellows.db in OPFS so a
        # returning visit with 401 still shows real data (the worker
        # doesn't re-fetch). To exercise the IDB-cache fallback path
        # explicitly, this test simulates a profile where the worker's
        # OPFS cache is empty (cold-start equivalent) by routing
        # /fellows.db to 401 BEFORE any successful boot, plus seeding
        # IDB before any boot — so the boot's only local data source
        # is the IDB seed.
        page = _make_standalone_page(context)
        try:
            # Route 401 BEFORE first navigation so the worker never
            # successfully populates its OPFS cache.
            context.route(
                FELLOWS_DB,
                lambda r: r.fulfill(status=401, body="session expired"),
            )
            context.route(
                API_FELLOWS,
                lambda r: r.fulfill(status=401, body="session expired"),
            )
            # Navigate once to set up a context where IndexedDB exists
            # (we need to be on the origin to be able to seed it). The
            # boot will fail to load fellows from anywhere; we'll seed
            # IDB and reload to get the cache-fallback render.
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            # Don't wait for #loading hide here — boot may render the
            # boot-failure panel. We just need the origin to be loaded
            # so indexedDB is reachable.
            page.wait_for_function(
                "() => !!(window.indexedDB)",
                timeout=5000,
            )
            _seed_indexeddb_with_fellows(page, SAMPLE_FELLOWS)
            # Reload — boot path now sees IDB cache populated, falls back
            # to it after worker + api both 401.
            page.reload(wait_until="domcontentloaded")
            page.locator("#loading").wait_for(state="hidden", timeout=10000)

            # Directory visible with cached names.
            directory = page.locator("#directory")
            directory.wait_for(state="visible", timeout=5000)
            expect(page.get_by_role("link", name="Ada Cached")).to_be_visible()

            # Build badge signals offline-only mode.
            badge_server = page.locator("#build-badge-server")
            expect(badge_server).to_contain_text("offline", timeout=3000)

            # Email-gate / install-landing / auth-error panels all stay hidden.
            expect(page.locator("#install-gate-private")).to_be_hidden()
            expect(page.locator("#install-landing")).to_be_hidden()
            expect(page.locator("#auth-error-panel")).to_be_hidden()
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            page.close()

    def test_401_without_cached_data_in_standalone_pwa_falls_back_to_gate(self, context, base_url_fixture):
        """Standalone PWA + 401 + no cache → must reach the email gate, not
        the boot-error panel (issue #125). Pre-fix, the catch handler at
        bootDirectoryAsApp's tail only handed off to startBrowserUx when
        ``!isStandaloneDisplayMode() && hasAuthenticatedOnce()`` — which
        was false in standalone mode, trapping users in a boot-error loop
        with no in-app way back to the gate (PWA windows have no URL bar).
        The fix extends the handoff to fire on any HTTP 401/403, regardless
        of display mode.
        """
        page = _make_standalone_page(context)
        # Mock /fellows.db and /api/fellows as 401 (expired session).
        context.route(
            FELLOWS_DB,
            lambda r: r.fulfill(status=401, body="session expired"),
        )
        context.route(
            API_FELLOWS,
            lambda r: r.fulfill(status=401, body="session expired"),
        )
        # Mock /api/auth/status so startBrowserUx renders the gate (rather
        # than the local-dev passthrough) once handoff fires.
        context.route(
            "**/api/auth/status",
            lambda r: r.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "authEnabled": True,
                    "authenticated": False,
                    "hasSessionCookie": False,
                    "installRecentlyAllowed": False,
                }),
            ),
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            # The fix routes the catch handler to startBrowserUx → email
            # gate. The gate's load-bearing element is the private container.
            page.locator("#install-gate-private").wait_for(state="visible", timeout=10000)
            # Pre-fix, the boot-error panel would have rendered. Asserting
            # both "gate visible" AND "boot-error panel hidden" pins the
            # fix-branch decision against any future regression that flips
            # back to the trap behavior.
            expect(page.locator("#boot-error-panel")).to_be_hidden()
            expect(page.locator("#auth-error-panel")).to_be_hidden()
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute("**/api/auth/status")
            page.close()

    def test_401_without_cached_data_in_browser_tab_falls_back_to_gate(self, context, base_url_fixture):
        """Browser tab + marker + 401 + no cache → the PR #49 safety net
        kicks in (quiet email gate). We never leave the user staring at a
        scary boot-failure panel when we can show them a way forward.
        """
        page = context.new_page()
        # No standalone init — this is the browser-tab-as-app path.
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        # Both /fellows.db (worker source) and /api/fellows (api+idb
        # fallback) need to fail to reach the no-cache code path.
        context.route(
            FELLOWS_DB,
            lambda r: r.fulfill(status=401, body="session expired"),
        )
        context.route(
            API_FELLOWS,
            lambda r: r.fulfill(status=401, body="session expired"),
        )
        # Mock auth-status as "auth enabled, unauthenticated" so the
        # startBrowserUx fallback takes the email-gate branch (not the
        # local-dev passthrough that would show the install landing).
        context.route(
            "**/api/auth/status",
            lambda r: r.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "authEnabled": True,
                    "authenticated": False,
                    "hasSessionCookie": False,
                    "installRecentlyAllowed": False,
                }),
            ),
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            # Wait for the gate fallback to render. The boot path:
            # (a) worker tries ensureFellowsDb → 401 → falls back to api+idb.
            # (b) api+idb getList → 401 → tryListFromCache → no IDB cache.
            # (c) bootDirectoryAsApp catch → !standalone + hasAuth → startBrowserUx.
            # (d) startBrowserUx sees authStatus=200 unauthenticated → email gate.
            page.locator("#install-gate-private").wait_for(state="visible", timeout=10000)
            expect(page.locator("#auth-error-panel")).to_be_hidden()
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute("**/api/auth/status")
            page.close()
