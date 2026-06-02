"""E2E for the PR 3 group detail page: action bar + Contact + Export panel
+ Edit nav + inline note edit + threshold banners + toast.

Pins:
- Action bar shows ✉ Contact / CC|BCC / ⬇ Export / ✎ Edit, with helper text
  reflecting the active mode.
- Contact <a> href is mailto:?cc=...&subject=... below the warn threshold.
- CC ↔ BCC toggle rebuilds the href.
- Soft warning banner appears at WARN_AT (50) recipients.
- Hard threshold (≥ HARD_AT = 100): href is removed; click copies addresses
  to clipboard and shows a toast.
- Export panel toggles open / closed; Export button is disabled with a
  PR 5 hint.
- Edit button navigates to #/edit/<id>; placeholder route renders.
- Inline note edit saves via the worker updateGroup RPC and persists
  across reload; cancel restores the original.

Phase 1 (plans/local_first_worker_architecture.md): setup that
previously went through the dev /api/groups HTTP route now drives the
worker via the worker_data_folder fixture.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect


def _real_fellows(worker_data_folder, with_email=True):
    """Return a list of (record_id, name, contact_email) tuples from the
    worker's fellows.db (the canonical local read source post-cutover)."""
    rows = worker_data_folder.get_full_fellows()
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
    # display:none on group routes, so it's no longer a route-independent
    # readiness signal.
    page.locator("#app-wrap").wait_for(state="visible", timeout=5000)


class TestGroupDetailActionBar:
    def test_action_bar_renders_three_buttons(
        self, worker_data_folder, base_url_fixture
    ):
        page = worker_data_folder.page
        fellows = _real_fellows(worker_data_folder)
        g = worker_data_folder.create_group(
            "Action bar test",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        bar = page.locator(".group-action-bar")
        expect(bar).to_be_visible(timeout=5000)
        contact = page.locator("#group-action-contact")
        expect(contact).to_be_visible()
        expect(contact).to_contain_text("Mail to the whole group")
        expect(page.locator("#group-action-export")).to_contain_text("Export a directory")
        expect(page.locator("#group-action-edit")).to_contain_text("Edit members")
        # CC pill is active by default.
        cc_pill = page.locator('.group-mode-pill[data-mode="cc"]')
        expect(cc_pill).to_have_class(re.compile(r"\bgroup-mode-pill--active\b"))
        bcc_pill = page.locator('.group-mode-pill[data-mode="bcc"]')
        expect(bcc_pill).not_to_have_class(re.compile(r"\bgroup-mode-pill--active\b"))

    def test_contact_href_under_threshold_is_mailto_cc(
        self, worker_data_folder, base_url_fixture
    ):
        page = worker_data_folder.page
        fellows = _real_fellows(worker_data_folder)
        chosen = fellows[:3]
        g = worker_data_folder.create_group(
            "Mailto small",
            fellow_record_ids=[f[0] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        contact = page.locator("#group-action-contact")
        expect(contact).to_have_attribute(
            "href", re.compile(r"^mailto:\?cc=.+&subject=Mailto%20small$")
        )

    def test_cc_bcc_toggle_rewrites_href(
        self, worker_data_folder, base_url_fixture
    ):
        page = worker_data_folder.page
        fellows = _real_fellows(worker_data_folder)
        g = worker_data_folder.create_group(
            "Toggle test",
            fellow_record_ids=[f[0] for f in fellows[:2]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        expect(page.locator("#group-action-contact")).to_have_attribute(
            "href", re.compile(r"^mailto:\?cc=")
        )
        page.locator('.group-mode-pill[data-mode="bcc"]').click()
        expect(page.locator("#group-action-contact")).to_have_attribute(
            "href", re.compile(r"^mailto:\?bcc=")
        )
        # ARIA pressed states flip.
        expect(page.locator('.group-mode-pill[data-mode="cc"]')).to_have_attribute(
            "aria-pressed", "false"
        )
        expect(page.locator('.group-mode-pill[data-mode="bcc"]')).to_have_attribute(
            "aria-pressed", "true"
        )

    def test_soft_warning_banner_at_warn_threshold(
        self, worker_data_folder, base_url_fixture
    ):
        page = worker_data_folder.page
        fellows = _real_fellows(worker_data_folder)
        # 60 recipients — comfortably between WARN (50) and HARD (100).
        chosen = fellows[:60]
        assert len(chosen) == 60, "dev dataset must have ≥ 60 fellows with emails"
        g = worker_data_folder.create_group(
            "Soft warn",
            fellow_record_ids=[f[0] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        soft = page.locator(".group-contact-banner--soft")
        expect(soft).to_be_visible(timeout=5000)
        expect(soft).to_contain_text("60 recipients")
        # Contact link is still a real mailto: URL (the soft path tries it).
        expect(page.locator("#group-action-contact")).to_have_attribute(
            "href", re.compile(r"^mailto:\?cc=")
        )

    def test_hard_threshold_strips_href_and_copies_to_clipboard(
        self, worker_data_folder, base_url_fixture, context
    ):
        # navigator.clipboard.writeText needs the permission in headless
        # Chromium. Granting at the browser-context level keeps this
        # localised to the e2e test.
        context.grant_permissions(
            ["clipboard-read", "clipboard-write"], origin=base_url_fixture
        )
        page = worker_data_folder.page
        fellows = _real_fellows(worker_data_folder)
        chosen = fellows[:120]
        assert len(chosen) == 120, "dev dataset must have ≥ 120 fellows with emails"
        g = worker_data_folder.create_group(
            "Hard limit",
            fellow_record_ids=[f[0] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        # Hard banner visible.
        hard = page.locator(".group-contact-banner--hard")
        expect(hard).to_be_visible(timeout=5000)
        expect(hard).to_contain_text("120 recipients")
        # Contact link has NO href in hard mode (so the click handler
        # intercepts and copies instead of trying a giant mailto URL).
        contact = page.locator("#group-action-contact")
        expect(contact).not_to_have_attribute("href", re.compile(r"."))
        # Click the Contact button → toast appears, addresses on clipboard.
        contact.click()
        toast = page.locator("#app-toast")
        expect(toast).to_be_visible(timeout=3000)
        expect(toast).to_contain_text("120 addresses copied")
        clipboard = page.evaluate("navigator.clipboard.readText()")
        # All 120 emails should be in the clipboard, comma-separated.
        for _, _, email in chosen:
            assert email in clipboard, f"missing {email} in clipboard"


class TestGroupDetailExportPanel:
    def test_export_panel_toggles_open_and_closed(
        self, worker_data_folder, base_url_fixture
    ):
        """Panel show/hide. Actual export downloads are exercised in
        tests/e2e/test_groups_export.py."""
        page = worker_data_folder.page
        fellows = _real_fellows(worker_data_folder)
        g = worker_data_folder.create_group(
            "Export panel",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        panel = page.locator("#group-export-panel")
        expect(panel).to_be_hidden()
        page.locator("#group-action-export").click()
        expect(panel).to_be_visible()
        # Export button is enabled.
        expect(page.locator(".group-export-go")).to_be_enabled()
        # Cancel hides it again.
        page.locator(".group-export-cancel").click()
        expect(panel).to_be_hidden()


class TestGroupDetailEditNav:
    def test_edit_button_navigates_and_enters_edit_mode(
        self, worker_data_folder, base_url_fixture
    ):
        """Click ✎ Edit members on the detail page → URL flips to
        #/edit/<id> and the yellow edit-mode banner appears.
        Deeper edit-mode behaviour (auto-save, cancel-edits, etc.)
        is covered in tests/e2e/test_groups_edit.py."""
        page = worker_data_folder.page
        fellows = _real_fellows(worker_data_folder)
        g = worker_data_folder.create_group(
            "Edit nav",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        page.locator("#group-action-edit").click()
        page.wait_for_url(lambda u: f"#/edit/{g['id']}" in u, timeout=3000)
        banner = page.locator("#edit-mode-banner")
        expect(banner).to_be_visible(timeout=3000)
        expect(page.locator("#edit-mode-banner-name")).to_have_text("Edit nav")


class TestGroupDetailNoteEdit:
    def test_inline_note_edit_saves_and_persists(
        self, worker_data_folder, base_url_fixture
    ):
        page = worker_data_folder.page
        fellows = _real_fellows(worker_data_folder)
        g = worker_data_folder.create_group(
            "Note flow",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        # No note → "add a note" link.
        edit_link = page.locator("#group-detail-note-edit")
        expect(edit_link).to_have_text("add a note")
        edit_link.click()
        textarea = page.locator(".group-detail-note-input")
        expect(textarea).to_be_visible()
        textarea.fill("for the Wellington roundtable")
        page.locator(".group-detail-note-save").click()
        expect(page.locator(".group-detail-note-text")).to_contain_text(
            "for the Wellington roundtable"
        )
        # Now the link reads "edit".
        expect(page.locator("#group-detail-note-edit")).to_have_text("edit")
        # Persists across reload.
        page.reload(wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        expect(page.locator(".group-detail-note-text")).to_contain_text(
            "for the Wellington roundtable"
        )

    def test_inline_note_edit_cancel_restores_original(
        self, worker_data_folder, base_url_fixture
    ):
        page = worker_data_folder.page
        fellows = _real_fellows(worker_data_folder)
        g = worker_data_folder.create_group(
            "Cancel flow",
            note="original note",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data_folder.wait()
        _wait_for_directory(page)
        expect(page.locator(".group-detail-note-text")).to_contain_text("original note")
        page.locator("#group-detail-note-edit").click()
        textarea = page.locator(".group-detail-note-input")
        textarea.fill("changed")
        page.locator(".group-detail-note-cancel").click()
        # Back to original; no PATCH was sent.
        expect(page.locator(".group-detail-note-text")).to_contain_text("original note")
