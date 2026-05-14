"""E2E: search must fall back to cached data when /api/search is gated.

Companion to test_offline_only_mode.py. That suite covers the directory
list (getList) when /fellows.db and /api/fellows both 401/403; this one
covers search over the same cached set when /api/search also 401/403s
(the symptom Rich hit on Android: phone in api+idb fallback, search box
silently empty even for cached fellows).

Per docs/email_gate.md invariant 10: "A stale session does not lock
users out of cached data ... The user can still browse the directory,
read profiles, and use the search over cached data."

Pre-fix, runSearch's `.then` returned [] on `!r.ok` and rendered "No
fellows match that search." Post-fix, runSearch falls through to
runLocalSearch (substring filter over loadFullFellows) on a non-2xx
response, the same way the .catch already handled network failures.
"""
import pytest
from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


API_FELLOWS = "**/api/fellows**"
FELLOWS_DB = "**/fellows.db"
API_SEARCH = "**/api/search**"


# filterFellowsLocally substring-matches across name + bio_tagline + cohort
# + fellow_type + search_tags + currently_based_in + global_regions. Keep
# every non-name field empty so the assertions are testing name matches
# only — any non-empty value risks accidentally containing the query.
_SEARCHABLE_FELLOWS = [
    {
        "record_id": "cached-bodo",
        "slug": "richard_bodo",
        "name": "Richard Bodo",
        "bio_tagline": "",
        "has_image": 0,
        "has_contact_email": 1,
        "contact_email": "richbodo@example.com",
    },
    {
        "record_id": "cached-graves",
        "slug": "richard_graves",
        "name": "Richard Graves",
        "bio_tagline": "",
        "has_image": 0,
        "has_contact_email": 1,
        "contact_email": "graves@example.com",
    },
    {
        "record_id": "cached-bird",
        "slug": "aaron_bird",
        "name": "Aaron Bird",
        "bio_tagline": "",
        "has_image": 0,
        "has_contact_email": 1,
        "contact_email": "aaron@example.com",
    },
]


def _seed_indexeddb_with_fellows(page, fellows):
    """Prime the fellows-local-db IndexedDB store with a known payload.

    Same shape that loadFullFellows() expects: object store 'meta',
    keyPath 'id', payload {id: 'allFellows', data: fellows}.
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


def _force_api_idb_fallback_with_cache(context, page, base_url):
    """Boot a page into the api+idb fallback path with seeded IDB cache.

    Mirrors the setup in test_offline_only_mode.py's cached-data test:
    route /fellows.db and /api/fellows to 401 BEFORE first navigation, seed
    IDB once we're on the origin, then reload to take the cache path.
    Leaves all routes in place — the caller is responsible for unrouting.
    """
    context.route(
        FELLOWS_DB,
        lambda r: r.fulfill(status=401, body="session expired"),
    )
    context.route(
        API_FELLOWS,
        lambda r: r.fulfill(status=401, body="session expired"),
    )
    # Land on the origin so indexedDB is reachable, then seed it.
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => !!(window.indexedDB)", timeout=5000)
    _seed_indexeddb_with_fellows(page, _SEARCHABLE_FELLOWS)
    # Reload so the boot path actually consumes the IDB cache.
    page.reload(wait_until="domcontentloaded")
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    page.locator("#directory").wait_for(state="visible", timeout=5000)
    # Sanity-check we landed in api+idb fallback, not the worker path.
    # If a future change makes the worker resilient to 401 on the bytes
    # fetch this assertion will start failing and we'll need a different
    # repro — better to fail loudly than to test the wrong code path.
    # (The former "server: offline" badge text was retired in the
    # never-SaaS copy cleanup; dataProvider.kind is the structural
    # signal now.)
    provider_kind = page.evaluate(
        "() => (window.__dataProvider && window.__dataProvider.kind) || null"
    )
    assert provider_kind == "api+idb", (
        f"expected api+idb fallback, got provider kind={provider_kind!r}"
    )


def _run_search(page, query):
    """Type into the search input, wait past the 250 ms debounce."""
    box = page.locator("#search-input")
    box.fill(query)
    # runSearch is debounced by 250 ms in app.js; give it room plus a tick
    # for the fetch / runLocalSearch promise chain to settle.
    page.wait_for_timeout(500)


class TestSearchOfflineFallback:
    """When /api/search is gated, runSearch must fall back to local cache."""

    def test_search_last_name_falls_back_to_cached_data(self, context, base_url_fixture):
        """`Bodo` over cached data finds Richard Bodo even though /api/search 401s.

        Pre-fix this fails: runSearch fetches /api/search, sees !r.ok,
        renders [] → 'No fellows match that search.' Post-fix runSearch
        routes !r.ok through runLocalSearch, which substring-matches
        against the IDB-cached full list.
        """
        page = _make_standalone_page(context)
        try:
            _force_api_idb_fallback_with_cache(context, page, base_url_fixture)
            # The bug trigger: server can't answer the search either.
            context.route(
                API_SEARCH,
                lambda r: r.fulfill(status=401, body="session expired"),
            )
            _run_search(page, "Bodo")
            list_el = page.locator("#directory-list")
            expect(list_el).to_contain_text("Richard Bodo", timeout=3000)
            # Control: a fellow whose name doesn't contain the query must
            # not appear — otherwise the "fallback" might be rendering the
            # full list unfiltered, which would be a different bug.
            expect(list_el).not_to_contain_text("Aaron Bird")
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_SEARCH)
            page.close()

    def test_search_first_name_falls_back_to_cached_data(self, context, base_url_fixture):
        """`Richard` returns both seeded Richards from the cache."""
        page = _make_standalone_page(context)
        try:
            _force_api_idb_fallback_with_cache(context, page, base_url_fixture)
            context.route(
                API_SEARCH,
                lambda r: r.fulfill(status=401, body="session expired"),
            )
            _run_search(page, "Richard")
            list_el = page.locator("#directory-list")
            expect(list_el).to_contain_text("Richard Bodo", timeout=3000)
            expect(list_el).to_contain_text("Richard Graves")
            expect(list_el).not_to_contain_text("Aaron Bird")
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_SEARCH)
            page.close()
