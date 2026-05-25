"""E2E for the opt-in directory data update flow.

plans/opt_in_directory_data_updates.md. The boot path is install-only —
covered by test_versioned_fellows_db.py:test_install_only_does_not_refetch_on_sha_mismatch.
This file covers the user-driven path:

  1. Click "Check for updates" with a mismatched fellows_db_sha →
     "Directory Data update available" appears + the action button
     surfaces.
  2. Click "Update directory data" with NO group impact → silent apply,
     status flips to "Directory data updated.", no dialog rendered.
  3. Click with group impact → confirm dialog lists affected members.
     Cancel restores the previous status (no swap). Update anyway
     completes the swap and refreshes the directory in place.
"""
from __future__ import annotations

import json

from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


BUILD_META_PATH = "**/build-meta.json"


def _route_build_meta(context, *, git_sha="boot-sha", fellows_db_sha=None):
    payload = {"git_sha": git_sha, "built_at": "2026-05-06T00:00:00Z"}
    if fellows_db_sha is not None:
        payload["fellows_db_sha"] = fellows_db_sha
    body = json.dumps(payload)

    def _fulfill(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=body,
            headers={"Cache-Control": "no-cache"},
        )

    context.route(BUILD_META_PATH, _fulfill)


def _make_standalone_page(context):
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    return page


def _wait_for_worker_ready(page, timeout_ms=15000):
    """Wait for the worker provider to be live (kind='worker' on
    window.__dataProvider).

    We deliberately use a sync predicate rather than awaiting getList
    inside the predicate. Playwright's wait_for_function with an
    async predicate runs in an isolation that, in our app, leaves
    `window.__dataProvider` not reachable from subsequent
    `page.evaluate` calls — even though the value was "live" at the
    moment the predicate resolved. Sync predicate sidesteps that.
    """
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=timeout_ms,
    )


def _boot_then_about(page, base_url):
    """Boot the directory at `/`, wait for boot's second route() (the
    one triggered after getFull completes) to land, THEN navigate to
    /#/about.

    Why: bootDirectoryAsApp calls route() twice — after getList and
    after getFull. If we navigate to /#/about before getFull settles,
    the second route() re-renders About from scratch and wipes the
    Checking…/status text the click handler is about to set. Waiting
    for `window.__bootMarks.get_full_done` proves the boot's second
    route() has fired against `/`; the subsequent hashchange to
    /#/about then runs route() once and stays put.
    """
    page.goto(base_url + "/", wait_until="domcontentloaded")
    _wait_for_worker_ready(page)
    page.wait_for_function(
        "() => window.__bootMarks && window.__bootMarks.get_full_done != null",
        timeout=15000,
    )
    page.goto(base_url + "/#/about", wait_until="domcontentloaded")
    page.wait_for_selector("#about-check-data-update", timeout=5000)


def test_check_updates_surfaces_directory_data_button(context, base_url_fixture):
    """Mock /build-meta.json to report a fake fellows_db_sha. Clicking
    "Check for updates" should populate the Directory data row with
    "Directory Data update available" and surface the action button."""
    page = _make_standalone_page(context)
    try:
        # Boot with no fellows_db_sha so the cold-start ensureFellowsDb
        # writes the real digest into meta sidecar; we'll then drift the
        # mock's reported SHA so compare reports an update available.
        _route_build_meta(context, git_sha="boot-sha")
        _boot_then_about(page, base_url_fixture)

        # Now drift: re-arm the mock with a deliberately different SHA.
        context.unroute(BUILD_META_PATH)
        _route_build_meta(context, git_sha="boot-sha", fellows_db_sha="f" * 64)

        page.locator("#about-check-data-update").click()
        data_status = page.locator("#about-data-status")
        expect(data_status).to_contain_text("Directory Data update available", timeout=5000)
        expect(page.locator("#about-data-update-btn")).to_be_visible()
    finally:
        context.unroute(BUILD_META_PATH)
        page.close()


def test_apply_with_no_group_impact_succeeds_silently(context, base_url_fixture):
    """No groups → no impact → no dialog. The swap commits and the
    status flips to "Directory data updated." """
    page = _make_standalone_page(context)
    try:
        _route_build_meta(context, git_sha="boot-sha")
        _boot_then_about(page, base_url_fixture)

        context.unroute(BUILD_META_PATH)
        _route_build_meta(context, git_sha="boot-sha", fellows_db_sha="f" * 64)

        page.locator("#about-check-data-update").click()
        expect(page.locator("#about-data-update-btn")).to_be_visible(timeout=5000)
        page.locator("#about-data-update-btn").click()

        data_status = page.locator("#about-data-status")
        expect(data_status).to_contain_text("Directory data updated", timeout=10000)
        # No dialog should have been rendered (no impact).
        expect(page.locator("#directory-update-dialog")).to_have_count(0)
    finally:
        context.unroute(BUILD_META_PATH)
        page.close()


def test_apply_with_group_impact_shows_dialog_and_can_cancel(context, base_url_fixture):
    """Seed a group with a synthetic record_id that's not in fellows.db,
    so the preview reports it as affected. The dialog lists it; Cancel
    leaves the directory unchanged."""
    page = _make_standalone_page(context)
    try:
        _route_build_meta(context, git_sha="boot-sha")
        _boot_then_about(page, base_url_fixture)

        # Seed a group with a synthetic member rid that won't appear in
        # the staged fellows.db. The worker will flag it as affected
        # during preview.
        page.evaluate(
            """
            async () => {
              const dp = window.__dataProvider;
              await dp.createGroup({
                name: 'opt-in-canary',
                note: '',
                fellow_record_ids: ['rec_synthetic_orphan_xyz']
              });
            }
            """
        )

        context.unroute(BUILD_META_PATH)
        _route_build_meta(context, git_sha="boot-sha", fellows_db_sha="f" * 64)

        page.locator("#about-check-data-update").click()
        expect(page.locator("#about-data-update-btn")).to_be_visible(timeout=5000)
        page.locator("#about-data-update-btn").click()

        # Dialog renders, lists the affected member.
        dialog = page.locator("#directory-update-dialog")
        expect(dialog).to_be_visible(timeout=10000)
        expect(dialog).to_contain_text("opt-in-canary")
        expect(dialog).to_contain_text("rec_synthetic_orphan_xyz")

        # Cancel — dialog dismissed, status reflects the cancel, no swap.
        page.locator("#directory-update-dialog-cancel").click()
        expect(dialog).to_have_count(0)
        expect(page.locator("#about-data-status")).to_contain_text(
            "Update cancelled", timeout=5000
        )

        # Verify the canary group still references the orphan rid (no
        # swap happened, so the group_members row is unchanged).
        group_check = page.evaluate(
            """
            async () => {
              const groups = await window.__dataProvider.listGroups();
              const canary = groups.find((g) => g.name === 'opt-in-canary');
              if (!canary) return { found: false };
              const detail = await window.__dataProvider.getGroup(canary.id);
              return {
                found: true,
                memberRids: (detail.members || []).map((m) => m.record_id)
              };
            }
            """
        )
        assert group_check["found"], "canary group should still exist after cancel"
        assert "rec_synthetic_orphan_xyz" in group_check["memberRids"], (
            f"cancelled swap must leave group_members untouched; got {group_check}"
        )
    finally:
        context.unroute(BUILD_META_PATH)
        page.close()


def test_stale_worker_surfaces_reload_affordance(context, base_url_fixture):
    """When the page is on a newer build than the worker (the SW-upgrade
    race), `compareFellowsDbSha` rejects with 'unknown op: ...'. The UI
    must surface a clear "Reload the app to enable update checks" prompt
    with a Reload button — not the generic "Couldn't check (offline?)".

    Simulated by monkey-patching the provider method to throw the same
    error shape the worker dispatcher emits for unknown ops.
    """
    page = _make_standalone_page(context)
    try:
        _route_build_meta(context, git_sha="boot-sha")
        _boot_then_about(page, base_url_fixture)

        context.unroute(BUILD_META_PATH)
        _route_build_meta(context, git_sha="boot-sha", fellows_db_sha="f" * 64)

        # Pretend the worker is older than this page: the new RPC is
        # registered on the page-side provider (so the early
        # 'unsupported' branch in checkForDirectoryDataUpdate doesn't
        # fire), but calling it rejects exactly the way an old
        # worker's dispatcher would.
        page.evaluate(
            """
            () => {
              window.__dataProvider._compareFellowsDbSha = function () {
                return Promise.reject(new Error('unknown op: compareFellowsDbSha'));
              };
            }
            """
        )

        page.locator("#about-check-data-update").click()
        data_status = page.locator("#about-data-status")
        expect(data_status).to_contain_text(
            "Reload the app to enable update checks", timeout=5000
        )
        expect(page.locator("#about-data-reload-btn")).to_be_visible()
    finally:
        context.unroute(BUILD_META_PATH)
        page.close()


def test_apply_with_group_impact_confirm_completes_swap(context, base_url_fixture):
    """Same setup as the cancel test, but confirm the swap. After
    apply, the directory data is refreshed and the status confirms the
    update."""
    page = _make_standalone_page(context)
    try:
        _route_build_meta(context, git_sha="boot-sha")
        _boot_then_about(page, base_url_fixture)

        page.evaluate(
            """
            async () => {
              const dp = window.__dataProvider;
              await dp.createGroup({
                name: 'opt-in-confirm-canary',
                note: '',
                fellow_record_ids: ['rec_synthetic_orphan_xyz_confirm']
              });
            }
            """
        )

        context.unroute(BUILD_META_PATH)
        _route_build_meta(context, git_sha="boot-sha", fellows_db_sha="f" * 64)

        page.locator("#about-check-data-update").click()
        expect(page.locator("#about-data-update-btn")).to_be_visible(timeout=5000)
        page.locator("#about-data-update-btn").click()
        expect(page.locator("#directory-update-dialog")).to_be_visible(timeout=10000)
        page.locator("#directory-update-dialog-confirm").click()

        expect(page.locator("#about-data-status")).to_contain_text(
            "Directory data updated", timeout=10000
        )
        # The orphan rid is still in group_members (we don't auto-prune;
        # the user removes it via the orphan row UI).
        group_check = page.evaluate(
            """
            async () => {
              const groups = await window.__dataProvider.listGroups();
              const canary = groups.find((g) => g.name === 'opt-in-confirm-canary');
              if (!canary) return { found: false };
              const detail = await window.__dataProvider.getGroup(canary.id);
              return {
                found: true,
                memberRids: (detail.members || []).map((m) => m.record_id)
              };
            }
            """
        )
        assert group_check["found"]
        assert "rec_synthetic_orphan_xyz_confirm" in group_check["memberRids"], (
            f"orphan rid should remain in group_members until user removes it; "
            f"got {group_check}"
        )
    finally:
        context.unroute(BUILD_META_PATH)
        page.close()
