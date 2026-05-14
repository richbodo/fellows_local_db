"""E2E: image prewarm must skip when the page is on api+idb fallback.

Before: every cold boot in api+idb fallback hammered the server with
~500 image fetches that all 403'd, then surfaced as a single
`Image prewarm: loaded=0/N errors=N` line in the boot trace AND added
~500 entries to the client-error ring buffer. Wasted network, log
noise, and an exact case where we know the server won't help us.

After: prewarm short-circuits when `offlineOnlyMode` is true, with a
new diagnostic status `skipped-unauthenticated`. Images that the user
already has cached from a prior authenticated boot continue to load
from `fellows-images-v1` Cache API. New users / installs that landed
in fallback have no images locally and surface the gap via the About
page's completeness counter (separate PR).

Companion to test_warm_worker_*_fallback.py and test_never_saas_copy.py
— same scenario fixture, different invariant.
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


# Include several fellows with has_image=1 so that, pre-fix, the prewarm
# WOULD have something to attempt. If all has_image flags were 0 the
# prewarm short-circuits on its own and we'd be testing the wrong path.
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


class TestImagePrewarmSkipInFallback:
    def test_prewarm_skipped_when_offline_only_mode(
        self, context, base_url_fixture
    ):
        """In api+idb fallback the prewarm must short-circuit. Diagnostic
        state should record `skipped-unauthenticated` (so the diag panel
        explains why no images loaded) and NO /images/* requests should
        fire over the wire."""
        page = _make_standalone_page(context)
        image_requests = []

        def _on_request(request):
            if "/images/" in request.url:
                image_requests.append(request.url)

        page.on("request", _on_request)

        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            # The boot path schedules prewarm via setTimeout(0); give it a
            # full event loop turn plus a generous beat so the gate had a
            # chance to fire if it was going to.
            page.wait_for_timeout(500)
            # The gate sets a specific status so a developer reading the
            # diag panel knows WHY no images loaded — distinct from the
            # `running` / `done` / `skipped-save-data` / `skipped-empty`
            # states the existing code already uses.
            state = page.evaluate(
                "() => window.__imagePrewarmState || null"
            )
            assert state is not None, (
                "window.__imagePrewarmState should be exposed for diagnostics"
            )
            assert state.get("status") == "skipped-unauthenticated", (
                f"prewarm must skip in api+idb fallback; got status="
                f"{state.get('status')!r}"
            )
            assert image_requests == [], (
                f"no /images/* requests should fire in fallback, got "
                f"{image_requests[:5]!r}"
            )
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()
