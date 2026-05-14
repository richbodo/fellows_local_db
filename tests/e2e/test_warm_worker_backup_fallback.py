"""E2E: backup / restore work via the warm worker even when the page-level
dataProvider is on the api+idb fallback.

Phase 0 of plans/user_folder_storage.md. When the worker spawned
successfully and has relationships.db open (worker.init.opfsCapable
true; relationships.db handle alive), the user's saved data IS
accessible — it's just that the page-level dataProvider fell back to
api+idb because the directory-data fetch was session-gated. Before
this fix the Settings backup buttons disappeared entirely (the api
provider's exportRelationshipsBytes etc. all rejected with
localDataUnavailable, which triggered the never-SaaS sign-in panel,
which has no backup button).

After this fix, the same buttons stay on the page and route through
warmWorker.rpc directly, so a user with an expired session can still
download a backup of their groups, notes, tags, and settings before
they reinstall, switch browsers, or re-authenticate.

Companion to:
  - test_never_saas_copy.py (copy is honest in the same scenario)
  - test_search_offline_fallback.py (search still works in the same scenario)
"""
import base64
import json

import pytest
from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


FELLOWS_DB = "**/fellows.db"
API_FELLOWS = "**/api/fellows**"
API_AUTH_STATUS = "**/api/auth/status"


SEED_FELLOWS = [
    {
        "record_id": "seed-1",
        "slug": "seed_one",
        "name": "Seed One",
        "has_image": 0,
        "has_contact_email": 1,
        "contact_email": "one@example.com",
    },
]


def _make_standalone_page(context):
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    page.add_init_script(
        "window.localStorage.setItem('fellows_authenticated_once', '1');"
    )
    return page


def _seed_indexeddb_with_fellows(page, fellows):
    """Prime fellows-local-db so the directory renders from cache once
    /api/fellows 401s during boot."""
    page.evaluate(
        """
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
        """,
        fellows,
    )


def _boot_into_api_idb_fallback(context, page, base_url):
    """Drive a fresh boot into the api+idb fallback. The worker spawns,
    opens OPFS (relationships.db gets created fresh), but the
    auth-gated /fellows.db fetch 401s — same path the user's phone
    hit. Returns once the page is in steady state at the directory
    with provider kind == 'api+idb'."""
    context.route(
        FELLOWS_DB,
        lambda r: r.fulfill(status=401, body="session expired"),
    )
    context.route(
        API_FELLOWS,
        lambda r: r.fulfill(status=401, body="session expired"),
    )
    context.route(
        API_AUTH_STATUS,
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
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => !!(window.indexedDB)", timeout=5000)
    _seed_indexeddb_with_fellows(page, SEED_FELLOWS)
    page.reload(wait_until="domcontentloaded")
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    page.locator("#directory").wait_for(state="visible", timeout=5000)
    kind = page.evaluate(
        "() => (window.__dataProvider && window.__dataProvider.kind) || null"
    )
    assert kind == "api+idb", f"expected api+idb fallback, got {kind!r}"


class TestWarmWorkerBackupFallback:
    """Backup, restore, and the underlying relationships.db reads work
    via the warm worker when the page-level provider is api+idb but
    the worker reports OPFS-capable + relationships.db open."""

    def test_download_userdata_button_is_reachable_in_api_idb_fallback(
        self, context, base_url_fixture
    ):
        """The export section stays in the DOM and the Download button is
        visible. Pre-fix the Settings page replaces it with the
        never-SaaS sign-in panel that has no backup affordance."""
        page = _make_standalone_page(context)
        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            page.evaluate("location.hash = '#/settings'")
            page.wait_for_timeout(500)
            expect(page.locator("#settings-download-userdata")).to_be_visible(
                timeout=5000
            )
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()

    def test_export_relationships_returns_valid_sqlite_bytes(
        self, context, base_url_fixture
    ):
        """Calling exportRelationshipsBytes via the active dataProvider
        in api+idb mode must return a real SQLite blob (first 16 bytes =
        'SQLite format 3\\0'). Pre-fix it rejected with
        localDataUnavailable; post-fix it routes through warmWorker.rpc.

        The exported DB is a freshly-bootstrapped relationships.db (no
        user data yet — this test is about the plumbing). The schema
        rows from `bootstrapRelationshipsSchema` are enough to make the
        DB non-empty and confirm we're reading a real file, not getting
        an empty buffer back."""
        page = _make_standalone_page(context)
        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            header_b64 = page.evaluate(
                """
                async () => {
                    const bytes = await window.__dataProvider.exportRelationshipsBytes();
                    if (!bytes || !bytes.byteLength) return null;
                    const u8 = new Uint8Array(bytes.buffer || bytes, 0, 16);
                    return btoa(String.fromCharCode.apply(null, u8));
                }
                """
            )
            assert header_b64, "exportRelationshipsBytes returned no bytes"
            header = base64.b64decode(header_b64)
            assert header.startswith(b"SQLite format 3"), (
                f"expected SQLite header in exported bytes, got {header!r}"
            )
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()

    def test_setting_round_trip_in_api_idb_fallback(
        self, context, base_url_fixture
    ):
        """setSetting and getSetting must both work via the warm worker
        fallback. Without this, the Settings page can't save the user's
        email override, and the page-render path (which calls getSetting
        for self_email) blows the whole page away with the
        showUnsupportedAndDisable panel."""
        page = _make_standalone_page(context)
        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            value = page.evaluate(
                """
                async () => {
                    await window.__dataProvider.setSetting(
                        'backup_fallback_marker', 'rich_was_here'
                    );
                    return window.__dataProvider.getSetting('backup_fallback_marker');
                }
                """
            )
            assert value == "rich_was_here", (
                f"expected setting to round-trip via warm worker, got {value!r}"
            )
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()
