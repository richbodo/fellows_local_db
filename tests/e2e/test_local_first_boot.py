"""E2E: Phase 2 acceptance — local-first boot with the network down.

Plan: ``plans/local_first_worker_architecture.md`` § Phase 2.

The post-P1 architecture stores ``fellows.db`` and ``relationships.db`` in
OPFS, owned by the dedicated worker. After a successful first boot a
returning visit's worker init opens the local files without making any
HTTP request — directory + groups render from local state regardless of
what ``/fellows.db`` and ``/api/fellows*`` are doing.

This test covers the L4 + L5 invariants by:

1. Letting the first boot complete normally (worker downloads fellows.db,
   the helper seeds a relationship via the worker RPC).
2. Closing the page, then arming context routes so ``/fellows.db`` 503s
   and ``/api/fellows*`` 401s — the catastrophic-server case.
3. Opening a second page in the same browser context (so OPFS persists).
   Directory and the seeded group must still render; the build badge
   shows the offline marker; the email gate / auth-error panels stay
   hidden.
"""
import importlib.util
import os
import sys

import pytest
from playwright.sync_api import expect

# Load the e2e-suite conftest directly. The natural ``from conftest import``
# resolves to whichever conftest pytest registered first in the session,
# which is ``tests/e2e/mobile/conftest.py`` when the mobile tree is
# collected before this file. Loading by absolute path avoids that
# ordering quirk without depending on collection order.
_E2E_CONFTEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conftest.py")
_spec = importlib.util.spec_from_file_location("_e2e_conftest", _E2E_CONFTEST_PATH)
_e2e_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_e2e_conftest)
_STANDALONE_DISPLAY_INIT = _e2e_conftest._STANDALONE_DISPLAY_INIT
WorkerDataHelper = _e2e_conftest.WorkerDataHelper
# Folder-mode helpers. Under the #244 capability gate a durable group only
# persists when a verified folder backs it, so the local-first canary must be
# seeded in folder mode. The fake folder is OPFS-backed and its handle persists
# in IndexedDB, so it re-hydrates on the second boot within the same context —
# and the directory still renders from the worker-owned OPFS fellows.db.
_FOLDER_PICKER_STUB_MIN = _e2e_conftest._FOLDER_PICKER_STUB_MIN
attach_verified_folder = _e2e_conftest.attach_verified_folder


FELLOWS_DB = "**/fellows.db"
API_FELLOWS = "**/api/fellows**"


def _make_standalone_page(context):
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    page.add_init_script(
        "window.localStorage.setItem('fellows_authenticated_once', '1');"
    )
    return page


class TestLocalFirstBoot:
    """L4 + L5: local DBs render before any /api/fellows* or /fellows.db request."""

    def test_returning_visit_renders_from_local_opfs_when_network_down(
        self, context, base_url_fixture
    ):
        # ----- First boot: prime OPFS -----
        page1 = _make_standalone_page(context)
        page1.add_init_script(_FOLDER_PICKER_STUB_MIN)
        try:
            page1.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            helper = WorkerDataHelper(page1)
            kind = helper.wait()
            assert kind == "worker", (
                f"Expected worker-backed dataProvider for first boot, got {kind!r}. "
                "Without a worker provider this test can't validate local-first behavior."
            )
            # Reset relationships state, then attach a verified folder before
            # seeding: under the #244 capability gate a browse-only createGroup
            # is refused, so the canary must be written in folder mode to be
            # durable. The fake folder (OPFS-backed) + its IDB handle re-hydrate
            # on the second boot, so the group still survives the reload.
            helper.wipe_relationships()
            attach_verified_folder(page1, base_url_fixture)
            full = helper.get_full_fellows()
            assert isinstance(full, list) and len(full) >= 2, (
                "Expected at least 2 fellows in the local fellows.db after first boot."
            )
            seed_ids = [full[0]["record_id"], full[1]["record_id"]]
            seed_group = helper.create_group(
                "Local-first canary", fellow_record_ids=seed_ids
            )
            assert seed_group["id"], "create_group did not return an id"
            # Confirm directory is rendering from the worker-owned
            # fellows.db (the L4 happy path) before we shut everything
            # down.
            page1.locator("#directory").wait_for(state="visible", timeout=5000)
        finally:
            page1.close()

        # ----- Second boot: network is gone, OPFS persists -----
        # Routes registered AFTER the first boot completes; OPFS state
        # carries over inside the browser context so the worker's init
        # finds fellows.db + relationships.db without any HTTP traffic.
        context.route(
            FELLOWS_DB,
            lambda r: r.fulfill(status=503, body="service unavailable"),
        )
        context.route(
            API_FELLOWS,
            lambda r: r.fulfill(status=401, body="session expired"),
        )
        # Track whether either protected endpoint was contacted —
        # invariant L4 says local DBs render before any such request.
        contacted = []

        def _track(req):
            url = req.url
            if "/fellows.db" in url or "/api/fellows" in url:
                contacted.append(url)

        page2 = _make_standalone_page(context)
        page2.add_init_script(_FOLDER_PICKER_STUB_MIN)
        page2.on("request", _track)
        try:
            page2.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page2.locator("#loading").wait_for(state="hidden", timeout=10000)
            # Directory rendered from worker-owned local fellows.db.
            directory = page2.locator("#directory")
            directory.wait_for(state="visible", timeout=5000)

            # Provider stayed worker-backed (no fall-through to api+idb).
            kind2 = page2.evaluate(
                "() => (window.__dataProvider && window.__dataProvider.kind) || null"
            )
            assert kind2 == "worker", (
                f"Expected worker provider on second boot, got {kind2!r}. "
                "Local-first means OPFS persistence is enough; the worker "
                "must not fall back to api+idb just because the network is down."
            )

            # Seeded group survived and is reachable through the same RPC
            # path the live UI uses.
            helper2 = WorkerDataHelper(page2)
            groups = helper2.list_groups()
            names = [g["name"] for g in (groups or [])]
            assert "Local-first canary" in names, (
                f"Expected the seeded group to survive into the second boot, got {names!r}."
            )

            # Email-gate / install-landing / auth-error panels all stay
            # hidden — this is decidedly NOT a degraded-UX boot.
            expect(page2.locator("#install-gate-private")).to_be_hidden()
            expect(page2.locator("#install-landing")).to_be_hidden()
            expect(page2.locator("#auth-error-panel")).to_be_hidden()

            # L4 ground-truth: no protected-endpoint request was issued
            # before the directory rendered. /fellows.db must not be
            # fetched at all (the worker's init is network-free; there's
            # no version-keyed refresh until Phase 3). /api/fellows* may
            # be optionally re-fetched in the future as a freshness top-up,
            # but Phase 1's worker provider serves getList/getFull from
            # local OPFS exclusively, so no /api/fellows traffic should
            # appear here either.
            assert not any("/fellows.db" in u for u in contacted), (
                f"L4 violation: /fellows.db was fetched on a returning visit with "
                f"local OPFS primed: {contacted!r}"
            )
            assert not any("/api/fellows" in u for u in contacted), (
                f"Worker provider should serve directory data from local OPFS, "
                f"not from /api/fellows: {contacted!r}"
            )
        finally:
            try:
                helper2 = WorkerDataHelper(page2)
                helper2.wipe_relationships()
                page2.evaluate("() => window.__dataProvider._clearFolderHandle()")
                page2.evaluate("() => window.__resetE2EUserFolderMin()")
            except Exception:
                pass
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            page2.close()
