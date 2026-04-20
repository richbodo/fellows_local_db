"""E2E: session-expired / 401 response serves cached data instead of booting to the email gate.

PR #50 ("install once, works forever"): a stale session must not lock a
user out of data they already downloaded. When /api/fellows returns 401,
the boot chain falls back to the IndexedDB cache populated by a prior
successful boot. The build badge's server line flips to "offline · using
cache" to keep the user oriented.
"""
import json

import pytest
from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


API_FELLOWS = "**/api/fellows**"


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
        page = _make_standalone_page(context)
        try:
            # First visit with the real dev server — this populates IndexedDB
            # with dev-sample fellows via the app's normal boot. We then
            # overwrite IndexedDB with a known payload before the 401 reload.
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page.locator("#loading").wait_for(state="hidden", timeout=10000)
            # Wait until the real API has completed getFull + the IndexedDB
            # save scheduled from it. Without this, our overwrite can race
            # with the (asynchronous) save, and the app's fresh-server data
            # wins on reload.
            page.wait_for_function(
                "() => !!(window.indexedDB)",
                timeout=5000,
            )
            page.wait_for_timeout(500)

            _seed_indexeddb_with_fellows(page, SAMPLE_FELLOWS)

            context.route(
                API_FELLOWS,
                lambda r: r.fulfill(status=401, body="session expired"),
            )
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
            context.unroute(API_FELLOWS)
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
            page.wait_for_timeout(500)
            # No cache → fall back to email gate via startBrowserUx.
            expect(page.locator("#install-gate-private")).to_be_visible()
            expect(page.locator("#auth-error-panel")).to_be_hidden()
        finally:
            context.unroute(API_FELLOWS)
            context.unroute("**/api/auth/status")
            page.close()
