"""E2E: Groups read/write works via the warm worker even when the
page-level dataProvider is on the api+idb fallback.

Phase 0b of plans/user_folder_storage.md, follow-up to Phase 0
(test_warm_worker_backup_fallback.py). Same scenario, different data
surface: relationships.db has both groups AND settings tables, and
both need to be reachable when the page falls back to api+idb because
the session-gated /fellows.db fetch returned 401.

Pre-fix, the Groups index in api+idb fallback rendered the
"Sign in to refresh" panel (post-PR #173) instead of the user's saved
groups. Post-fix, listGroups / getGroup / createGroup / updateGroup /
deleteGroup all route through warmWorker.rpc so the groups feature
keeps working with an expired session.
"""
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
    {
        "record_id": "seed-2",
        "slug": "seed_two",
        "name": "Seed Two",
        "has_image": 0,
        "has_contact_email": 1,
        "contact_email": "two@example.com",
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
    """Same setup as test_warm_worker_backup_fallback._boot_into_api_idb_fallback.
    Kept inline rather than imported to keep the test file standalone."""
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


class TestWarmWorkerGroupsFallback:
    """Groups RPCs work via the warm worker when the page is on api+idb."""

    def test_list_groups_returns_array_not_localdataunavailable(
        self, context, base_url_fixture
    ):
        """listGroups must return an array (possibly empty) — not reject
        with localDataUnavailable as it does pre-fix via the api provider."""
        page = _make_standalone_page(context)
        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            result = page.evaluate(
                """
                async () => {
                    try {
                        const groups = await window.__dataProvider.listGroups();
                        return { ok: true, length: Array.isArray(groups) ? groups.length : null };
                    } catch (err) {
                        return { ok: false, message: String(err && err.message || err),
                                 localDataUnavailable: !!(err && err.localDataUnavailable) };
                    }
                }
                """
            )
            assert result.get("ok"), (
                f"listGroups should succeed via warm worker, got {result!r}"
            )
            assert result.get("length") is not None, (
                f"listGroups should return an array, got {result!r}"
            )
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()

    def test_create_then_get_then_delete_round_trip(
        self, context, base_url_fixture
    ):
        """createGroup → getGroup → deleteGroup must all work via the
        warm worker. getGroup's response must include `members` as an
        array of {record_id, name} — that's withResolvedMembers'
        contract, which previously lived inside createWorkerDataProvider
        but is now reachable from createApiPlusIdbDataProvider too."""
        page = _make_standalone_page(context)
        try:
            _boot_into_api_idb_fallback(context, page, base_url_fixture)
            outcome = page.evaluate(
                """
                async () => {
                    const dp = window.__dataProvider;
                    // Create with one member (using a real seeded record_id
                    // so member-name resolution can find a name).
                    const created = await dp.createGroup({
                        name: 'Phase 0b smoke',
                        note: 'wired via warm worker',
                        fellow_record_ids: ['seed-1']
                    });
                    if (!created || !created.id) {
                        return { ok: false, stage: 'create', detail: created };
                    }
                    const fetched = await dp.getGroup(created.id);
                    if (!fetched || !Array.isArray(fetched.members)) {
                        return { ok: false, stage: 'get', detail: fetched };
                    }
                    // members should be objects with record_id + name keys,
                    // not bare record_id strings. Pre-helper-hoist they'd
                    // come back as bare strings since withResolvedMembers
                    // wouldn't run.
                    const member = fetched.members[0];
                    const hasShape =
                        member && typeof member === 'object' &&
                        'record_id' in member && 'name' in member;
                    await dp.deleteGroup(created.id);
                    const after = await dp.listGroups();
                    return {
                        ok: true,
                        memberHasShape: hasShape,
                        memberName: member && member.name,
                        listEmptyAfterDelete: Array.isArray(after) && after.length === 0
                    };
                }
                """
            )
            assert outcome.get("ok"), (
                f"round-trip should succeed, got {outcome!r}"
            )
            assert outcome.get("memberHasShape"), (
                f"members should be {{record_id, name}} objects via "
                f"withResolvedMembers, got {outcome!r}"
            )
            assert outcome.get("memberName") == "Seed One", (
                f"members should resolve their names from the fellow cache; "
                f"got {outcome.get('memberName')!r}"
            )
            assert outcome.get("listEmptyAfterDelete"), (
                f"deleteGroup should leave list empty, got {outcome!r}"
            )
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            context.unroute(API_AUTH_STATUS)
            page.close()
