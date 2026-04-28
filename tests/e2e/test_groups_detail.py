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
- Inline note edit saves via PATCH and persists across reload; cancel
  restores the original.
"""
from __future__ import annotations

import json
import re
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect


def _conn(base_url):
    parsed = urlparse(base_url)
    return HTTPConnection(parsed.hostname, parsed.port, timeout=10)


def _wipe_groups(base_url):
    c = _conn(base_url)
    c.request("GET", "/api/groups")
    r = c.getresponse()
    body = r.read()
    c.close()
    if r.status != 200:
        return
    try:
        groups = json.loads(body)
    except ValueError:
        return
    for g in groups:
        c2 = _conn(base_url)
        c2.request("DELETE", f"/api/groups/{g['id']}")
        c2.getresponse().read()
        c2.close()


def _real_fellows(base_url, with_email=True):
    """Return a list of (record_id, name, contact_email) tuples from the dev API."""
    c = _conn(base_url)
    c.request("GET", "/api/fellows?full=1")
    r = c.getresponse()
    body = r.read()
    c.close()
    rows = json.loads(body)
    out = []
    for row in rows:
        rid = row.get("record_id")
        name = row.get("name") or ""
        email = (row.get("contact_email") or "").strip()
        if with_email and not email:
            continue
        out.append((rid, name, email))
    return out


def _create_group(base_url, *, name, fellow_record_ids, note=""):
    c = _conn(base_url)
    payload = json.dumps({
        "name": name,
        "note": note,
        "fellow_record_ids": fellow_record_ids,
    }).encode("utf-8")
    c.request(
        "POST",
        "/api/groups",
        body=payload,
        headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
    )
    r = c.getresponse()
    body = r.read()
    c.close()
    assert r.status == 201, body
    return json.loads(body)


def _wait_for_directory(page):
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    page.locator("#directory").wait_for(state="visible", timeout=5000)


@pytest.fixture(autouse=True)
def _reset_relationships_db(base_url_fixture):
    _wipe_groups(base_url_fixture)
    yield


class TestGroupDetailActionBar:
    def test_action_bar_renders_three_buttons(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture,
            name="Action bar test",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        bar = page.locator(".group-action-bar")
        expect(bar).to_be_visible(timeout=5000)
        contact = page.locator("#group-action-contact")
        expect(contact).to_be_visible()
        expect(contact).to_contain_text("Contact the whole group")
        expect(page.locator("#group-action-export")).to_contain_text("Export a directory")
        expect(page.locator("#group-action-edit")).to_contain_text("Edit group")
        # CC pill is active by default.
        cc_pill = page.locator('.group-mode-pill[data-mode="cc"]')
        expect(cc_pill).to_have_class(re.compile(r"\bgroup-mode-pill--active\b"))
        bcc_pill = page.locator('.group-mode-pill[data-mode="bcc"]')
        expect(bcc_pill).not_to_have_class(re.compile(r"\bgroup-mode-pill--active\b"))

    def test_contact_href_under_threshold_is_mailto_cc(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        chosen = fellows[:3]
        g = _create_group(
            base_url_fixture,
            name="Mailto small",
            fellow_record_ids=[f[0] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        contact = page.locator("#group-action-contact")
        expect(contact).to_have_attribute(
            "href", re.compile(r"^mailto:\?cc=.+&subject=Mailto%20small$")
        )

    def test_cc_bcc_toggle_rewrites_href_and_helper(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture,
            name="Toggle test",
            fellow_record_ids=[f[0] for f in fellows[:2]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        helper_mode = page.locator("#group-action-helper-mode")
        expect(helper_mode).to_have_text("CC")
        expect(page.locator("#group-action-contact")).to_have_attribute(
            "href", re.compile(r"^mailto:\?cc=")
        )
        page.locator('.group-mode-pill[data-mode="bcc"]').click()
        expect(helper_mode).to_have_text("BCC")
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
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        # 60 recipients — comfortably between WARN (50) and HARD (100).
        chosen = fellows[:60]
        assert len(chosen) == 60, "dev dataset must have ≥ 60 fellows with emails"
        g = _create_group(
            base_url_fixture,
            name="Soft warn",
            fellow_record_ids=[f[0] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        soft = page.locator(".group-contact-banner--soft")
        expect(soft).to_be_visible(timeout=5000)
        expect(soft).to_contain_text("60 recipients")
        # Contact link is still a real mailto: URL (the soft path tries it).
        expect(page.locator("#group-action-contact")).to_have_attribute(
            "href", re.compile(r"^mailto:\?cc=")
        )

    def test_hard_threshold_strips_href_and_copies_to_clipboard(
        self, standalone_page, base_url_fixture, context
    ):
        # navigator.clipboard.writeText needs the permission in headless
        # Chromium. Granting at the browser-context level keeps this
        # localised to the e2e test.
        context.grant_permissions(
            ["clipboard-read", "clipboard-write"], origin=base_url_fixture
        )
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        chosen = fellows[:120]
        assert len(chosen) == 120, "dev dataset must have ≥ 120 fellows with emails"
        g = _create_group(
            base_url_fixture,
            name="Hard limit",
            fellow_record_ids=[f[0] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
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
    def test_export_panel_toggles_and_export_disabled_with_pr5_hint(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture,
            name="Export panel",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        panel = page.locator("#group-export-panel")
        expect(panel).to_be_hidden()
        page.locator("#group-action-export").click()
        expect(panel).to_be_visible()
        # Export button disabled with PR 5 hint.
        export_go = page.locator(".group-export-go")
        expect(export_go).to_be_disabled()
        expect(export_go).to_have_attribute("title", re.compile(r"PR 5"))
        # Cancel hides it again.
        page.locator(".group-export-cancel").click()
        expect(panel).to_be_hidden()


class TestGroupDetailEditNav:
    def test_edit_button_navigates_to_edit_route_placeholder(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture,
            name="Edit nav",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#group-action-edit").click()
        page.wait_for_url(lambda u: f"#/edit/{g['id']}" in u, timeout=3000)
        # PR 3 placeholder visible until PR 4 lands real edit-mode entry.
        placeholder = page.locator(".group-detail-page .placeholder")
        expect(placeholder).to_contain_text("Edit mode lands in PR 4")


class TestGroupDetailNoteEdit:
    def test_inline_note_edit_saves_and_persists(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture,
            name="Note flow",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
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
        _wait_for_directory(page)
        expect(page.locator(".group-detail-note-text")).to_contain_text(
            "for the Wellington roundtable"
        )

    def test_inline_note_edit_cancel_restores_original(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture,
            name="Cancel flow",
            note="original note",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        expect(page.locator(".group-detail-note-text")).to_contain_text("original note")
        page.locator("#group-detail-note-edit").click()
        textarea = page.locator(".group-detail-note-input")
        textarea.fill("changed")
        page.locator(".group-detail-note-cancel").click()
        # Back to original; no PATCH was sent.
        expect(page.locator(".group-detail-note-text")).to_contain_text("original note")
