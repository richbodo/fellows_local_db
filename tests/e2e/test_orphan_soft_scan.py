"""E2E for the post-PR-#113 orphan soft scan + orphan row UI.

plans/opt_in_directory_data_updates.md. The soft scan runs once per
profile (gated by `relationships.settings.orphan_scan_done`) to surface
any group_members rows whose record_id is no longer in fellows.db. A
toast fires once; subsequent boots skip it. The orphan row in group
detail renders with a per-row Remove affordance regardless of whether
the toast has been shown.
"""
from __future__ import annotations

from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


def _make_standalone_page(context):
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    return page


def _wait_for_worker_ready(page, timeout_ms=15000):
    """Wait for worker provider live (kind='worker'). Sync predicate —
    async predicates have a quirk in this codebase that leaves
    `window.__dataProvider` unreachable from later page.evaluate calls.
    """
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=timeout_ms,
    )
    # Wait for boot path's getFull to settle (its second route() call
    # is what would otherwise re-render and clobber click-handler state).
    page.wait_for_function(
        "() => window.__bootMarks && window.__bootMarks.get_full_done != null",
        timeout=timeout_ms,
    )


def _seed_orphan_group(page, group_name, orphan_rid):
    """Create a group whose only member is a record_id that does not
    exist in fellows.db. The soft scan + group-detail render flag this
    as an orphan."""
    page.evaluate(
        """
        async (args) => {
          const dp = window.__dataProvider;
          await dp.createGroup({
            name: args.name,
            note: '',
            fellow_record_ids: [args.rid]
          });
        }
        """,
        {"name": group_name, "rid": orphan_rid},
    )


def test_soft_scan_fires_toast_once_and_marks_done(context, base_url_fixture):
    """First boot with an orphan present: toast appears and the
    `orphan_scan_done` setting flips to '1'. Subsequent reload does
    not re-show the toast."""
    page = _make_standalone_page(context)
    try:
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_worker_ready(page)
        # Wait for the boot soft scan to complete so we don't race with
        # it when clearing the marker. The boot scan always sets the
        # marker (whether or not orphans were found) — once we see '1'
        # the boot scan is definitely done.
        # NB: poll via repeated sync page.evaluate. wait_for_function
        # with an async predicate has a quirk in this codebase (see
        # _wait_for_worker_ready) that breaks subsequent evaluates.
        deadline_ms = 10_000
        elapsed = 0
        while elapsed < deadline_ms:
            val = page.evaluate("() => window.__dataProvider.getSetting('orphan_scan_done')")
            if val == "1":
                break
            page.wait_for_timeout(200)
            elapsed += 200
        assert val == "1", f"boot soft scan did not set marker within {deadline_ms}ms"

        # Seed an orphan group + clear the marker so the next boot's
        # scan re-runs against the now-orphan-bearing relationships.db.
        page.evaluate(
            """
            async () => {
              const dp = window.__dataProvider;
              await dp.createGroup({
                name: 'orphan-toast-canary',
                note: '',
                fellow_record_ids: ['rec_orphan_for_toast_scan']
              });
              await dp.setSetting('orphan_scan_done', '');
            }
            """
        )

        page.reload(wait_until="domcontentloaded")
        _wait_for_worker_ready(page)

        toast = page.locator("#app-toast")
        expect(toast).to_be_visible(timeout=10000)
        expect(toast).to_contain_text("no longer in the directory")

        # Marker is set after the scan runs.
        marker = page.evaluate("() => window.__dataProvider.getSetting('orphan_scan_done')")
        assert marker == "1", f"orphan_scan_done should be set after scan; got {marker!r}"

        # Reload again — marker prevents the toast from re-firing.
        # Wait long enough that a fresh toast would have been visible.
        page.reload(wait_until="domcontentloaded")
        _wait_for_worker_ready(page)
        page.wait_for_timeout(500)
        # Either the toast element doesn't exist yet (no toast was
        # triggered this boot), or it exists but is not visible.
        toast_count = page.locator("#app-toast.app-toast--visible").count()
        assert toast_count == 0, (
            f"orphan toast should not re-appear after marker is set; got count={toast_count}"
        )
    finally:
        page.close()


def test_unresolved_member_shows_hint_in_rail_and_visual_directory(
    context, base_url_fixture
):
    """Issue #111 second half: when a group_member's record_id can't be
    resolved against fellows.db, the composer rail (edit mode) and the
    visual-directory portrait grid both render a muted '(fellow data
    unavailable)' hint instead of just the raw record_id.

    Group detail itself uses the richer 'Profile no longer available'
    orphan row (PR #117); this test covers the other surfaces.
    """
    page = _make_standalone_page(context)
    try:
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_worker_ready(page)

        _seed_orphan_group(
            page,
            group_name="orphan-hint-canary",
            orphan_rid="rec_orphan_for_hint_render",
        )
        group_id = page.evaluate(
            """
            async () => {
              const groups = await window.__dataProvider.listGroups();
              const g = groups.find((x) => x.name === 'orphan-hint-canary');
              return g ? g.id : null;
            }
            """
        )
        assert group_id is not None

        # Visual directory: hint shows under the portrait.
        page.goto(
            base_url_fixture + "/#/groups/" + str(group_id) + "/directory",
            wait_until="domcontentloaded",
        )
        unresolved_cell = page.locator(".group-directory-cell--unresolved")
        expect(unresolved_cell).to_be_visible(timeout=5000)
        expect(unresolved_cell).to_contain_text("(fellow data unavailable)")
        expect(unresolved_cell).to_contain_text("rec_orphan_for_hint_render")

        # Modal opened from that cell carries the same hint.
        unresolved_cell.click()
        modal_hint = page.locator(".fellow-modal-unresolved-hint")
        expect(modal_hint).to_be_visible(timeout=3000)
        expect(modal_hint).to_contain_text("(fellow data unavailable)")
        page.locator(".fellow-modal-close").click()

        # Edit mode: rail chip carries the hint instead of just the rid.
        page.goto(
            base_url_fixture + "/#/edit/" + str(group_id),
            wait_until="domcontentloaded",
        )
        rail_chip = page.locator(".group-rail-member--unresolved")
        expect(rail_chip).to_be_visible(timeout=5000)
        expect(rail_chip).to_contain_text("(fellow data unavailable)")
        expect(rail_chip).to_contain_text("rec_orphan_for_hint_render")
    finally:
        page.close()


def test_orphan_row_renders_with_remove_affordance(context, base_url_fixture):
    """Group detail flags orphan members and offers a Remove button.
    Clicking Remove drops the row from group_members and re-renders."""
    page = _make_standalone_page(context)
    try:
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_worker_ready(page)

        _seed_orphan_group(
            page, group_name="orphan-row-canary", orphan_rid="rec_orphan_for_row_render"
        )
        # Look up the group ID and navigate.
        group_id = page.evaluate(
            """
            async () => {
              const groups = await window.__dataProvider.listGroups();
              const g = groups.find((x) => x.name === 'orphan-row-canary');
              return g ? g.id : null;
            }
            """
        )
        assert group_id is not None, "seeded group should be visible via listGroups"
        page.goto(base_url_fixture + "/#/groups/" + str(group_id), wait_until="domcontentloaded")

        orphan_row = page.locator(".group-detail-member-orphan")
        expect(orphan_row).to_be_visible(timeout=5000)
        expect(orphan_row).to_contain_text("Profile no longer available")
        expect(orphan_row).to_contain_text("rec_orphan_for_row_render")

        remove_btn = page.locator(".group-detail-orphan-remove")
        expect(remove_btn).to_be_visible()
        remove_btn.click()

        # After the remove call settles + the page re-renders, the orphan
        # row is gone and the group has zero members.
        expect(page.locator(".group-detail-member-orphan")).to_have_count(0, timeout=10000)
        members = page.evaluate(
            """
            async (gid) => {
              const detail = await window.__dataProvider.getGroup(gid);
              return (detail.members || []).map((m) => m.record_id);
            }
            """,
            group_id,
        )
        assert members == [], (
            f"Remove should drop the rid from group_members; got {members}"
        )
    finally:
        page.close()
