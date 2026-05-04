"""E2E for PR 4 edit mode.

Pins:
- Clicking ✎ Edit members on the detail page enters edit mode: yellow
  banner appears, rail flips to "editing group" / "Done editing",
  members are pre-selected, has-email filter is unchecked, search is
  cleared.
- Toggling +/✕ in edit mode auto-saves via the worker updateGroup RPC;
  the group's membership reflects the change immediately.
- Done editing navigates to #/groups/<id>; banner hides; rail returns
  to compose mode.
- cancel edits PATCHes the entry-snapshot back; the group ends up as
  it was when edit mode started.
- The compose draft (members + title) is preserved across an edit-
  mode detour.
- The "edit" row action on /#/groups also enters edit mode.
- Reloading mid-edit re-enters edit mode (banner reappears).
- The cancel-edits link carries the design's title attribute.

Phase 1 (plans/local_first_worker_architecture.md): setup that
previously went through the dev server's /api/groups HTTP routes now
drives window.__dataProvider via the worker_data fixture.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect


def _real_fellows(worker_data, with_email=True):
    """Pick real (record_id, name, email) tuples from the live fellows.db
    via worker_data.get_full_fellows(). Replaces the previous HTTP probe
    against /api/fellows?full=1 — the worker is the canonical local
    read source post-cutover."""
    rows = worker_data.get_full_fellows()
    out = []
    for row in rows:
        rid = row.get("record_id")
        name = row.get("name") or ""
        email = (row.get("contact_email") or "").strip()
        if with_email and not email:
            continue
        out.append((rid, name, email))
    return out


def _wait_for_directory(page):
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    # #app-wrap rather than #directory: the directory rail is now
    # display:none on the bare group-detail route. Edit mode itself
    # restores the rail, but readiness needs to fire either way.
    page.locator("#app-wrap").wait_for(state="visible", timeout=5000)


def _aaron_row(page):
    link = page.locator("#directory a.dir-link", has_text="Aaron Bird").first
    expect(link).to_be_visible()
    return link.locator("xpath=..")


class TestEditModeEntry:
    def test_clicking_edit_on_detail_enters_edit_mode(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        fellows = _real_fellows(worker_data)
        chosen = fellows[:2]
        g = worker_data.create_group(
            "Wellington crew",
            fellow_record_ids=[f[0] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        page.locator("#group-action-edit").click()
        page.wait_for_url(lambda u: f"#/edit/{g['id']}" in u, timeout=3000)
        banner = page.locator("#edit-mode-banner")
        expect(banner).to_be_visible(timeout=3000)
        expect(page.locator("#edit-mode-banner-name")).to_have_text("Wellington crew")
        # Cancel link carries the design's title attribute (hover hint).
        cancel = page.locator("#edit-mode-banner-cancel")
        expect(cancel).to_have_attribute(
            "title",
            "revert this group to the state it was in when you opened edit mode",
        )
        # Rail UI flips to edit mode.
        expect(page.locator("#group-rail-eyebrow")).to_have_text("editing group")
        expect(page.locator("#group-rail-create")).to_have_text("Done editing")
        expect(page.locator("#group-rail-create")).to_be_enabled()
        # has-email filter is unchecked on entry.
        expect(page.locator("#has-email-filter")).not_to_be_checked()
        # Search is cleared on entry.
        expect(page.locator("#search-input")).to_have_value("")
        # Members are pre-loaded into the rail (chip count = 2).
        expect(page.locator("#group-rail-members .group-rail-member-name")).to_have_count(2)

    def test_groups_index_edit_row_action_also_enters_edit_mode(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        fellows = _real_fellows(worker_data)
        g = worker_data.create_group(
            "Row-action edit",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        page.locator(".groups-action-edit").click()
        page.wait_for_url(lambda u: f"#/edit/{g['id']}" in u, timeout=3000)
        expect(page.locator("#edit-mode-banner")).to_be_visible(timeout=3000)


class TestEditModeAutoSave:
    def test_toggle_in_edit_mode_patches_membership(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        fellows = _real_fellows(worker_data)
        # Start with 1 fellow, then add one via the directory + marker.
        g = worker_data.create_group(
            "Auto-save",
            fellow_record_ids=[fellows[0][0]],
        )
        before = worker_data.get_group(g["id"])
        assert len(before["members"]) == 1

        page.goto(f"{base_url_fixture}/#/edit/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        # Marker for fellow at index 1 (different from the pre-selected member)
        # — find their name and toggle.
        target_name = fellows[1][1]
        target_link = page.locator(
            "#directory a.dir-link", has_text=re.compile(r"^" + re.escape(target_name) + r"$")
        ).first
        target_link.locator("xpath=..").locator(".dir-mark").click()
        # Wait briefly for the auto-save to land. The chip in the rail updates
        # synchronously, so we can use that as the in-page signal.
        expect(
            page.locator("#group-rail-members .group-rail-member-name")
        ).to_have_count(2, timeout=3000)
        # Verify the worker actually saved.
        page.wait_for_timeout(150)
        after = worker_data.get_group(g["id"])
        ids = sorted(m["record_id"] for m in after["members"])
        assert ids == sorted([fellows[0][0], fellows[1][0]])


class TestDoneEditing:
    def test_done_editing_navigates_back_and_exits(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        fellows = _real_fellows(worker_data)
        g = worker_data.create_group(
            "Done flow",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/edit/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        # The rail's primary button reads "Done editing" in edit mode.
        page.locator("#group-rail-create").click()
        page.wait_for_url(lambda u: f"#/groups/{g['id']}" in u, timeout=3000)
        expect(page.locator("#edit-mode-banner")).to_be_hidden()
        # Rail back to compose mode.
        expect(page.locator("#group-rail-eyebrow")).to_have_text("add to a group")
        expect(page.locator("#group-rail-create")).to_have_text("Create new group")
        # Detail page renders the group. Target the inner title text so
        # the pencil-rename ✎ link beside it doesn't trip the exact match.
        expect(page.locator("#group-detail-title-text")).to_have_text("Done flow")


class TestCancelEdits:
    def test_cancel_edits_reverts_membership_to_snapshot(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        fellows = _real_fellows(worker_data)
        # 2 members at entry. We'll add a third in edit mode, then revert.
        g = worker_data.create_group(
            "Revert test",
            fellow_record_ids=[fellows[0][0], fellows[1][0]],
        )
        page.goto(f"{base_url_fixture}/#/edit/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        # Add a third member.
        third_name = fellows[2][1]
        third_link = page.locator(
            "#directory a.dir-link", has_text=re.compile(r"^" + re.escape(third_name) + r"$")
        ).first
        third_link.locator("xpath=..").locator(".dir-mark").click()
        expect(
            page.locator("#group-rail-members .group-rail-member-name")
        ).to_have_count(3, timeout=3000)
        page.wait_for_timeout(150)
        mid = worker_data.get_group(g["id"])
        assert len(mid["members"]) == 3
        # Click cancel-edits → PATCH snapshot back, navigate.
        page.locator("#edit-mode-banner-cancel").click()
        page.wait_for_url(lambda u: f"#/groups/{g['id']}" in u, timeout=3000)
        page.wait_for_timeout(150)
        after = worker_data.get_group(g["id"])
        ids = sorted(m["record_id"] for m in after["members"])
        assert ids == sorted([fellows[0][0], fellows[1][0]])


class TestComposeDraftSurvivesEdit:
    def test_compose_draft_preserved_across_edit_detour(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        fellows = _real_fellows(worker_data)
        # Existing group to edit.
        g = worker_data.create_group(
            "Existing",
            fellow_record_ids=[fellows[0][0]],
        )
        # worker_data already navigated to /; directory should be ready.
        _wait_for_directory(page)
        # Compose draft: pick Aaron Bird, type a title.
        _aaron_row(page).locator(".dir-mark").click()
        page.locator("#group-rail-title").fill("My in-progress group")
        # Detour into edit mode.
        page.goto(f"{base_url_fixture}/#/edit/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        expect(page.locator("#edit-mode-banner")).to_be_visible(timeout=3000)
        # Done editing.
        page.locator("#group-rail-create").click()
        page.wait_for_url(lambda u: f"#/groups/{g['id']}" in u, timeout=3000)
        # Back to directory.
        page.goto(f"{base_url_fixture}/", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        # Compose draft is restored.
        expect(page.locator("#group-rail-title")).to_have_value("My in-progress group")
        chip = page.locator("#group-rail-members .group-rail-member-name").first
        expect(chip).to_have_text("Aaron Bird")
        expect(_aaron_row(page).locator(".dir-mark")).to_have_text("✕")


class TestReloadDuringEdit:
    def test_reload_in_edit_mode_re_enters(self, worker_data, base_url_fixture):
        page = worker_data.page
        fellows = _real_fellows(worker_data)
        g = worker_data.create_group(
            "Reload test",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/edit/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        expect(page.locator("#edit-mode-banner")).to_be_visible(timeout=3000)
        page.reload(wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        expect(page.locator("#edit-mode-banner")).to_be_visible(timeout=5000)
        expect(page.locator("#edit-mode-banner-name")).to_have_text("Reload test")
