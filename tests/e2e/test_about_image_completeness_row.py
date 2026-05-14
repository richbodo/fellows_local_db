"""E2E: About page surfaces an image-cache completeness row + sign-in
CTA when the user landed in api+idb fallback.

Companion to test_image_prewarm_skip_in_fallback.py. That PR stops
hammering the server with doomed image fetches; this row tells the
user *why* they have no profile photos and gives them a one-click
path to fix it (sign in via the magic-link gate so a subsequent boot
can populate the cache).

Plan: Option A from plans/user_folder_storage.md § Refreshable assets.
"""
import json

import pytest
from playwright.sync_api import expect


FELLOWS_DB = "**/fellows.db"
API_FELLOWS = "**/api/fellows**"
API_AUTH_STATUS = "**/api/auth/status"


def _make_standalone_page(context):
    from conftest import _STANDALONE_DISPLAY_INIT

    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    page.add_init_script(
        "window.localStorage.setItem('fellows_authenticated_once', '1');"
    )
    return page


def _seed_indexeddb_with_fellows(page, fellows):
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


# Seeded fellows ALL have has_image=1 so the completeness denominator
# is non-zero. Cache stays empty (the prewarm is skipped per the
# prewarm-skip fix this PR is stacked on), so the numerator is 0.
SEED_FELLOWS = [
    {
        "record_id": f"seed-{i}",
        "slug": f"seed_{i}",
        "name": f"Seed {i}",
        "has_image": 1,
        "has_contact_email": 1,
        "contact_email": f"seed{i}@example.com",
    }
    for i in range(1, 6)
]


def _boot_into_api_idb_fallback(context, page, base_url):
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


class TestAboutImageCompletenessRow:
    def test_about_row_shows_count_and_signin_cta_in_fallback(
        self, context, base_url_fixture
    ):
        """In api+idb fallback with an incomplete image cache, About
        renders a 'Profile photos' row with a 'Sign in' link to
        /?gate=1. Pre-fix this row doesn't exist; the user has no
        in-app explanation for missing photos."""
        page = _make_standalone_page(context)
        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            page.evaluate("location.hash = '#/about'")
            page.locator("#about-images-row").wait_for(
                state="visible", timeout=5000
            )
            status = page.locator("#about-images-status")
            # Counter should read "0 / 5 cached" (5 seeded fellows, all
            # has_image=1, cache empty because prewarm was skipped).
            expect(status).to_contain_text("0", timeout=3000)
            expect(status).to_contain_text("5")
            # CTA should be present and point at /?gate=1.
            action = page.locator("#about-images-action a")
            expect(action).to_be_visible()
            href = action.get_attribute("href")
            assert href and "gate=1" in href, (
                f"sign-in link should target /?gate=1, got {href!r}"
            )
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()

    def test_about_row_omits_signin_cta_in_worker_mode(
        self, standalone_page, base_url_fixture
    ):
        """Happy path: worker provider, no fallback. The row still
        renders the count (informational), but no sign-in CTA — the
        user is already authenticated; clicking gate=1 would log them
        out and is the wrong affordance."""
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)
        kind = page.evaluate(
            "() => (window.__dataProvider && window.__dataProvider.kind) || null"
        )
        assert kind == "worker", f"happy path needs worker provider, got {kind!r}"
        page.evaluate("location.hash = '#/about'")
        page.locator("#about-images-row").wait_for(state="visible", timeout=5000)
        action = page.locator("#about-images-action a")
        # The action slot exists in DOM but should NOT contain a sign-in
        # link in worker mode. .count() returns 0 when no link rendered.
        assert action.count() == 0, (
            "worker-mode About row must not offer a sign-in CTA; "
            "the user is already signed in"
        )
