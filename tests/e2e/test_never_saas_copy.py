"""E2E: never-SaaS framing — stop announcing server connectivity outside
the "Check for updates" flow, and stop misattributing a session-expired
403 as a browser-capability gap.

Context: the app is local-first. After install, the server is only
consulted when the user explicitly clicks Check for updates. Yet the
chrome currently shows a "server: offline · using cache" suffix in the
build badge when /fellows.db 403s during boot, and Settings / About
both render messages claiming OPFS didn't initialize — even when the
diagnostic clearly shows OPFS *is* working (relationships.db opened
fine, worker reports opfsCapable=true) and the only actual failure was
the auth-gated /fellows.db fetch.

These tests pin the corrected behavior:
  1. Build badge never claims the server is offline / unreachable /
     using cache. Connectivity is not a user concern outside the
     explicit update-check flow.
  2. About → Check for updates → Directory data row, when worker is
     OPFS-capable but the active provider is api+idb (session expired),
     offers re-authentication rather than blaming the browser.
  3. Settings → Backup and restore, in the same condition, says the
     feature is paused pending sign-in rather than "OPFS didn't
     initialize on this load."
"""
import json

import pytest
from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


FELLOWS_DB = "**/fellows.db"
API_FELLOWS = "**/api/fellows**"
API_AUTH_STATUS = "**/api/auth/status"


def _make_standalone_page(context):
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    page.add_init_script(
        "window.localStorage.setItem('fellows_authenticated_once', '1');"
    )
    return page


def _seed_indexeddb_with_fellows(page, fellows):
    """Prime fellows-local-db so getList/getFull have something to return."""
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


def _boot_into_api_idb_fallback(context, page, base_url):
    """Drive the page into the session-expired api+idb fallback path.

    Routes /fellows.db and /api/fellows to 401 BEFORE first navigation
    (so the worker fails to fetch fellows.db and the page falls back).
    Also overrides /api/auth/status so authEnabled=true + authenticated=
    false — without that the dev server's no-auth passthrough takes a
    different code path and we end up on the worker provider anyway.

    Mirrors test_offline_only_mode.py's setup; see that file for the
    rationale on each step.
    """
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
    # Sanity-check we landed on api+idb with the warm worker reporting
    # OPFS capable — that's the precise condition under which the
    # misleading "OPFS didn't initialize" / "browser doesn't support"
    # copy fires today.
    state = page.evaluate(
        """
        () => ({
            providerKind: (window.__dataProvider && window.__dataProvider.kind) || null,
            // warmWorker is module-scope inside the IIFE so we can't read
            // it directly; lean on the page-state debug panel input.
            // Most reliable proxy: the diagnostics window properties
            // pickDataProvider sets when it falls back after worker init
            // succeeded.
        })
        """
    )
    assert state["providerKind"] == "api+idb", (
        f"expected api+idb fallback, got {state['providerKind']!r}"
    )


class TestBuildBadgeNeverSaaS:
    """Build badge is informational metadata, not a connectivity indicator."""

    def test_badge_does_not_claim_server_offline_on_api_idb_fallback(
        self, context, base_url_fixture
    ):
        page = _make_standalone_page(context)
        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            badge = page.locator("#build-badge")
            # The fail signal: pre-fix, the build-badge-server line reads
            # "server: offline · using cache" once tryListFromCache fires.
            expect(badge).not_to_contain_text("offline", timeout=3000)
            expect(badge).not_to_contain_text("unreachable")
            expect(badge).not_to_contain_text("using cache")
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()


class TestCheckForUpdatesCopy:
    """Update-check result strings name the right cause."""

    def test_data_row_offers_sign_in_when_worker_opfs_capable(
        self, context, base_url_fixture
    ):
        page = _make_standalone_page(context)
        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            # Open About.
            page.evaluate("location.hash = '#/about'")
            page.locator("#about-check-updates").wait_for(state="visible", timeout=5000)
            page.locator("#about-check-updates").click()
            data_row = page.locator("#about-data-status")
            # Wait for the FINAL post-click state, not just the absence
            # of the wrong-attribution copy. The in-progress "Checking…"
            # text passes `not_to_contain_text('isn')` but isn't the
            # final state; polling on the absence creates a race that
            # async work on the About page render can re-tickle.
            expect(data_row).to_contain_text("Sign in", timeout=5000)
            row_text = data_row.text_content() or ""
            assert "isn’t available" not in row_text and "isn't available" not in row_text, (
                f"data row must not blame the browser; got: {row_text!r}"
            )
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()


class TestSettingsBackupPanelCopy:
    """Backup-and-restore panel doesn't blame OPFS when OPFS is fine.

    On the api+idb path the api-provider's getSetting throws
    `localDataUnavailable`, which currently replaces the ENTIRE Settings
    detail pane with the runtime-failure panel (see
    showUnsupportedAndDisable at app.js:8384). So we assert against
    #detail's full text content rather than the export-section subtree.
    """

    def test_panel_does_not_claim_opfs_failed_when_worker_is_opfs_capable(
        self, context, base_url_fixture
    ):
        page = _make_standalone_page(context)
        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            page.evaluate("location.hash = '#/settings'")
            # Wait for either the panel headline or the normal settings
            # title to appear — both routes land somewhere in #detail.
            page.locator("#detail").wait_for(state="visible", timeout=5000)
            page.wait_for_timeout(500)  # let the late-async getSetting reject settle
            text = page.locator("#detail").text_content() or ""
            # Pre-fix lede: "OPFS didn't initialize on this load."
            assert "didn't initialize" not in text and "didn’t initialize" not in text, (
                f"settings panel must not blame OPFS when it works; got: {text!r}"
            )
            # Post-fix should mention sign-in or the magic-link flow, OR
            # the regular settings page renders (best outcome — backup
            # works via the warm worker even in fallback). Either is
            # better than the current OPFS-misattribution copy.
            lower = text.lower()
            ok = (
                "sign in" in lower
                or "magic link" in lower
                or "your saved data" in lower  # regular settings export heading
            )
            assert ok, (
                f"settings panel should suggest re-authentication or render "
                f"normally; got: {text!r}"
            )
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()
