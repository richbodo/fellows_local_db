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


# Resolves true once the persistent IndexedDB 'allFellows' mirror has rows.
# Post Part-1 fix, a worker-source boot writes this mirror in the getFull
# .then, so the second window has a tier-3 cache to fall back to.
_IDB_ALLFELLOWS_POPULATED = """
() => new Promise((resolve) => {
  const r = indexedDB.open('fellows-local-db', 1);
  r.onsuccess = () => {
    const db = r.result;
    try {
      const tx = db.transaction('meta', 'readonly');
      const g = tx.objectStore('meta').get('allFellows');
      g.onsuccess = () => { const rec = g.result;
        resolve(!!(rec && Array.isArray(rec.data) && rec.data.length > 0)); };
      g.onerror = () => resolve(false);
      tx.oncomplete = () => db.close();
    } catch (e) { try { db.close(); } catch (e2) {} resolve(false); }
  };
  r.onerror = () => resolve(false);
})
"""

# Deletes the 'allFellows' record so the tier-3 cache reads empty — used to
# force the Part-2 "no cached directory to serve" path.
_CLEAR_IDB_ALLFELLOWS = """
() => new Promise((resolve) => {
  const r = indexedDB.open('fellows-local-db', 1);
  r.onsuccess = () => {
    const db = r.result;
    try {
      const tx = db.transaction('meta', 'readwrite');
      tx.objectStore('meta').delete('allFellows');
      tx.oncomplete = () => { db.close(); resolve(true); };
      tx.onerror = () => { db.close(); resolve(false); };
    } catch (e) { try { db.close(); } catch (e2) {} resolve(false); }
  };
  r.onerror = () => resolve(false);
})
"""


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

            # Data provider has fallen back to the api+idb path (the cached
            # data source), which is the load-bearing signal for offline-only
            # mode. Previously this used `#build-badge-server`'s text, but
            # the floating build badge was removed in commit 0ac562d.
            provider_kind = page.evaluate(
                "() => (window.__dataProvider && window.__dataProvider.kind) || null"
            )
            assert provider_kind == "api+idb", (
                f"expected api+idb fallback, got provider kind={provider_kind!r}"
            )

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

            # Instrumentation (email-gate cascade debuggability): this is the
            # exact onboarded-user-hits-the-gate cascade. The boot trace must
            # now LOUDLY record the empty-cache fallback + the handoff cause,
            # and the auth trace must carry the initEmailGate verdict line
            # flagging an already-onboarded install (fellows_authenticated_once
            # is set by _make_standalone_page) reaching the gate. These are the
            # lines that make this report triageable from a diagnostics paste.
            # See docs/email_gate.md § "Why an onboarded user can land on the
            # email gate".
            boot_trace = "\n".join(page.evaluate("() => window.__bootDebugLines || []"))
            assert "tryListFromCache: IndexedDB allFellows EMPTY" in boot_trace, (
                f"expected loud empty-cache fallback line in boot trace:\n{boot_trace}"
            )
            assert "handoff cause: authFailure=true" in boot_trace, (
                f"expected the handoff-cause line in boot trace:\n{boot_trace}"
            )
            auth_trace = "\n".join(page.evaluate("() => window.__authDebugLines || []"))
            assert "initEmailGate: rendering gate" in auth_trace, (
                f"expected the initEmailGate verdict line in auth trace:\n{auth_trace}"
            )
            assert "already-onboarded install" in auth_trace, (
                f"expected the onboarded-install NOTE in auth trace:\n{auth_trace}"
            )
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

    def test_folder_push_banner_stays_hidden_on_gate_after_stale_session(self, context, base_url_fixture):
        """Regression: the folder-push "set up a data folder" banner must NOT
        paint on top of the email gate.

        Repro (the only state that triggers it): an already-installed user
        (fellows_authenticated_once) whose session expired boots via
        bootDirectoryAsApp → pickDataProvider assigns window.__dataProvider →
        401/403 → the catch handler hands off to startBrowserUx → initEmailGate.
        The provider stays assigned, so the banner's old inApp-only guard let
        the nag render over the gate. The fix also requires #app-wrap to be
        visible (the gate hides it via showApp(false)). A fresh incognito
        visitor never reproduces this — they never call bootDirectoryAsApp, so
        the provider is never set; that asymmetry was the field symptom.
        """
        page = context.new_page()
        # Installed browser-tab user → boots via bootDirectoryAsApp; no cache.
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        context.route(
            FELLOWS_DB,
            lambda r: r.fulfill(status=401, body="session expired"),
        )
        context.route(
            API_FELLOWS,
            lambda r: r.fulfill(status=401, body="session expired"),
        )
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
            page.locator("#install-gate-private").wait_for(state="visible", timeout=10000)
            # Bug precondition: the provider lingers (set during the failed
            # bootDirectoryAsApp, never cleared by the gate handoff) and the
            # app shell is hidden.
            assert page.evaluate(
                "() => !!(window.__dataProvider && window.__dataProvider.kind)"
            ), "expected window.__dataProvider to remain set after the gate handoff"
            expect(page.locator("#app-wrap")).to_be_hidden()
            # Drive the banner re-evaluation exactly as the production 1.5s
            # safety-net timer (setTimeout(refreshFolderPushBanner, 1500)) does,
            # but deterministically via the test seam. Without the app-wrap
            # guard this paints the nag over the gate; with it, it stays hidden.
            page.wait_for_function(
                "() => typeof window.__refreshFolderPushBanner === 'function'",
                timeout=5000,
            )
            page.evaluate("() => window.__refreshFolderPushBanner()")
            # Let the async getState()/countRelationships chain settle — a
            # regression would flip the banner visible within this window.
            page.wait_for_timeout(1000)
            expect(page.locator("#folder-push-banner")).to_be_hidden()
            # The gate is still the thing on screen.
            expect(page.locator("#install-gate-private")).to_be_visible()
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute("**/api/auth/status")
            page.close()

    def test_onboarded_multitab_stale_session_shows_cached_directory_not_gate(
        self, context, base_url_fixture
    ):
        """The reported bug, fixed by Part 1 (worker boots populate the IDB
        mirror). An installed/onboarded user opens the app in a SECOND window
        while the first still holds OPFS, and the session has gone stale.

        Pre-fix cascade: 2nd window's worker can't own OPFS (ownership
        conflict) → api+idb → /api/fellows 403 → empty IDB cache → email gate
        (with the not-a-PNA banner on top). Post-fix: the FIRST window's
        worker boot persisted the 'allFellows' mirror, so the 2nd window's
        api+idb fallback serves the CACHED DIRECTORY — not the gate. This is
        the AC-5 stale-session invariant actually holding for the common
        worker-only install. See docs/email_gate.md § onboarded-user...
        """
        page1 = _make_standalone_page(context)
        page1.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page1.locator("#loading").wait_for(state="hidden", timeout=15000)
        # First window booted via the worker; wait for the Part-1 IDB mirror
        # write so the second window has a cache to fall back to.
        page1.wait_for_function(_IDB_ALLFELLOWS_POPULATED, timeout=10000)

        # Second window's session is stale: 403 the directory API. (/fellows.db,
        # the worker source, is mooted by the ownership conflict page1 induces.)
        context.route(API_FELLOWS, lambda r: r.fulfill(status=403, body="session expired"))
        page2 = _make_standalone_page(context)
        try:
            page2.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page2.locator("#loading").wait_for(state="hidden", timeout=15000)
            # Directory renders from the cached mirror — NOT the email gate.
            expect(page2.locator("#app-wrap")).to_be_visible(timeout=5000)
            expect(page2.locator("#install-gate-private")).to_be_hidden()
            expect(page2.locator("#boot-error-panel")).to_be_hidden()
            kind = page2.evaluate(
                "() => (window.__dataProvider && window.__dataProvider.kind) || null"
            )
            assert kind == "api+idb", (
                f"expected api+idb fallback in the 2nd window (worker knocked out "
                f"by the ownership conflict), got {kind!r}"
            )
            # Confirm the multi-tab path: the worker fell back on an OPFS lock.
            boot_trace = "\n".join(page2.evaluate("() => window.__bootDebugLines || []"))
            assert "OPFS lock" in boot_trace, (
                f"expected the 2nd window's worker to fall back on an OPFS lock:\n{boot_trace}"
            )
        finally:
            context.unroute(API_FELLOWS)
            page2.close()
            page1.close()

    def test_ownership_conflict_empty_cache_shows_panel_not_gate(
        self, context, base_url_fixture
    ):
        """Part 2. When the worker can't own OPFS (another window open) AND
        there is no cached directory to serve, the boot surfaces the actionable
        "app open in another window" panel — NOT the email gate (re-auth would
        not release the OPFS lock). Negative invariant for the cascade.
        """
        page1 = _make_standalone_page(context)
        page1.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page1.locator("#loading").wait_for(state="hidden", timeout=15000)
        page1.wait_for_function(_IDB_ALLFELLOWS_POPULATED, timeout=10000)
        # Force the "no cache" condition: clear the mirror page1 just wrote so
        # page2's tier-3 fallback is empty.
        page1.evaluate(_CLEAR_IDB_ALLFELLOWS)

        context.route(API_FELLOWS, lambda r: r.fulfill(status=403, body="session expired"))
        page2 = _make_standalone_page(context)
        try:
            page2.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            # The ownership panel reuses #boot-error-panel with ownership copy.
            page2.locator("#boot-error-panel").wait_for(state="visible", timeout=15000)
            lead = page2.locator("#boot-error-panel .boot-error-lead").inner_text()
            assert "another window" in lead.lower(), (
                f"expected ownership-conflict copy in the panel, got: {lead!r}"
            )
            # Crucially NOT the email gate.
            expect(page2.locator("#install-gate-private")).to_be_hidden()
            boot_trace = "\n".join(page2.evaluate("() => window.__bootDebugLines || []"))
            assert "NOT the email gate" in boot_trace, (
                f"expected the ownership-not-gate boot-trace line:\n{boot_trace}"
            )
        finally:
            context.unroute(API_FELLOWS)
            page2.close()
            page1.close()
