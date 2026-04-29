"""E2E for the visual directory + group export panel.

Pins:
- #/groups/<id>/directory renders a portrait grid + Contact bar.
- "visual directory" row action on /#/groups goes there.
- Clicking a portrait opens a contact-info modal (name, mailto:, tel:,
  links, "View full profile" link).
- The Export panel:
  - PDF/HTML are mutually-exclusive radios; selecting HTML produces a
    single self-contained .html file (HTML5 doctype, contains the
    member's name, contact-bar mailto:);
  - selecting PDF produces a .pdf file (magic bytes %PDF-);
  - the email input lives inside the post-export result row, prefilled
    from settings when set and showing a cue when empty;
  - Export only creates the file — it does not navigate to mailto: by
    itself; the post-export result row exposes a View link and an
    Email button (always — there's no upfront opt-in checkbox).
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


def _wipe_settings(base_url):
    c = _conn(base_url)
    c.request("GET", "/api/settings")
    r = c.getresponse()
    body = r.read()
    c.close()
    if r.status != 200:
        return
    try:
        bag = json.loads(body)
    except ValueError:
        return
    for k in bag.keys():
        c2 = _conn(base_url)
        payload = json.dumps({"value": ""}).encode("utf-8")
        c2.request(
            "PUT", f"/api/settings/{k}", body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        c2.getresponse().read()
        c2.close()


def _real_fellows(base_url, with_email=True):
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
        out.append((rid, name, email, row.get("slug") or ""))
    return out


def _create_group(base_url, *, name, fellow_record_ids, note=""):
    c = _conn(base_url)
    payload = json.dumps({
        "name": name, "note": note, "fellow_record_ids": fellow_record_ids,
    }).encode("utf-8")
    c.request(
        "POST", "/api/groups", body=payload,
        headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
    )
    r = c.getresponse()
    body = r.read()
    c.close()
    assert r.status == 201, body
    return json.loads(body)


def _wait_for_directory(page):
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    # #app-wrap rather than #directory: the directory rail is now
    # display:none on group routes, so it's no longer a route-independent
    # readiness signal.
    page.locator("#app-wrap").wait_for(state="visible", timeout=5000)


@pytest.fixture(autouse=True)
def _reset(base_url_fixture):
    _wipe_groups(base_url_fixture)
    _wipe_settings(base_url_fixture)
    yield


class TestVisualDirectoryPage:
    def test_directory_route_renders_portrait_grid(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        chosen = fellows[:3]
        g = _create_group(
            base_url_fixture, name="Visual",
            fellow_record_ids=[f[0] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}/directory", wait_until="domcontentloaded")
        _wait_for_directory(page)
        title = page.locator(".group-directory-title")
        expect(title).to_have_text("Visual")
        cells = page.locator(".group-directory-cell")
        expect(cells).to_have_count(3)
        # Contact bar uses mailto:?cc with all 3 emails.
        link = page.locator(".group-directory-contact-link")
        expect(link).to_have_attribute("href", re.compile(r"^mailto:\?cc=.+&subject=Visual$"))

    def test_view_directory_row_action_navigates(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture, name="Row nav",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator(".groups-action-view").click()
        page.wait_for_url(lambda u: f"#/groups/{g['id']}/directory" in u, timeout=3000)
        expect(page.locator(".group-directory-grid")).to_be_visible()

    def test_portrait_click_opens_contact_modal(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        first = fellows[0]
        g = _create_group(
            base_url_fixture, name="Click test",
            fellow_record_ids=[first[0]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}/directory", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator(".group-directory-cell").first.click()
        # Modal appears with the fellow's name and a mailto: link to
        # their contact_email (members are filtered to with_email=True).
        modal = page.locator(".fellow-modal-card")
        expect(modal).to_be_visible()
        expect(modal.locator(".fellow-modal-name")).to_have_text(first[1])
        expect(modal.locator(f"a[href='mailto:{first[2]}']")).to_be_visible()
        # The "View full profile" link is what navigates — clicking the
        # cell itself no longer does.
        profile_link = modal.locator(".fellow-modal-profile-link")
        expect(profile_link).to_have_attribute("href", f"#/fellow/{first[3]}")
        profile_link.click()
        page.wait_for_url(lambda u: f"#/fellow/{first[3]}" in u, timeout=3000)
        # Modal is dismissed after navigation.
        expect(page.locator(".fellow-modal-overlay")).to_have_count(0)

    def test_portrait_modal_close_button_dismisses(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        first = fellows[0]
        g = _create_group(
            base_url_fixture, name="Close test",
            fellow_record_ids=[first[0]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}/directory", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator(".group-directory-cell").first.click()
        expect(page.locator(".fellow-modal-card")).to_be_visible()
        page.locator(".fellow-modal-close").click()
        expect(page.locator(".fellow-modal-overlay")).to_have_count(0)


class TestExportDownloads:
    def test_html_export_downloads_single_self_contained_file(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        chosen = fellows[:2]
        g = _create_group(
            base_url_fixture, name="HTML export test",
            fellow_record_ids=[f[0] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#group-action-export").click()
        page.locator("#export-format-html").check()
        with page.expect_download(timeout=20000) as dl_info:
            page.locator("#group-export-go").click()
        download = dl_info.value
        assert download.suggested_filename.endswith(".html")
        path = download.path()
        with open(path, "rb") as f:
            data = f.read()
        # Single-file HTML, with the member's name and an inlined <style>.
        assert data[:len(b"<!doctype html>")].lower() == b"<!doctype html>"
        text = data.decode("utf-8")
        assert "<style>" in text and "</style>" in text, "expected inlined CSS"
        assert chosen[0][1] in text, f"expected fellow name in HTML: {chosen[0][1]!r}"
        # Contact-the-whole-group bar references the first fellow's email.
        assert f"mailto:?cc=" in text and chosen[0][2] in text
        # Post-export result row is visible with the View link.
        result = page.locator("#group-export-result")
        expect(result).to_be_visible()
        view = page.locator("#group-export-view")
        expect(view).to_be_visible()
        # The .then() that wires up the blob: href runs ~100ms after the
        # download starts (downloadBlob's setTimeout), so wait for it.
        page.wait_for_function(
            "() => { const v = document.querySelector('#group-export-view');"
            " return v && (v.getAttribute('href') || '').startsWith('blob:'); }",
            timeout=5000,
        )
        href = view.get_attribute("href") or ""
        assert href.startswith("blob:"), f"expected blob: URL, got {href!r}"

    def test_pdf_export_downloads_with_pdf_magic_bytes(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture, name="PDF export test",
            fellow_record_ids=[f[0] for f in fellows[:2]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#group-action-export").click()
        page.locator("#export-format-pdf").check()
        with page.expect_download(timeout=20000) as dl_info:
            page.locator("#group-export-go").click()
        download = dl_info.value
        assert download.suggested_filename.endswith(".pdf")
        path = download.path()
        with open(path, "rb") as f:
            head = f.read(8)
        assert head[:5] == b"%PDF-", f"expected %PDF- magic, got {head!r}"

    def test_pdf_and_html_radios_are_mutually_exclusive(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture, name="Radio test",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#group-action-export").click()
        # Default: PDF selected, HTML not.
        expect(page.locator("#export-format-pdf")).to_be_checked()
        expect(page.locator("#export-format-html")).not_to_be_checked()
        # Pick HTML; PDF auto-deselects.
        page.locator("#export-format-html").check()
        expect(page.locator("#export-format-html")).to_be_checked()
        expect(page.locator("#export-format-pdf")).not_to_be_checked()

    def test_email_input_prefilled_from_settings_when_set(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        # Seed a self_email in settings before opening the page.
        c = _conn(base_url_fixture)
        payload = json.dumps({"value": "user@example.com"}).encode("utf-8")
        c.request(
            "PUT", "/api/settings/self_email", body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        c.getresponse().read()
        c.close()
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture, name="Prefill test",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#group-action-export").click()
        addr = page.locator("#export-self-email-addr")
        expect(addr).to_have_value("user@example.com")
        cue = page.locator("#export-self-email-cue")
        expect(cue).to_contain_text("override")

    def test_email_input_empty_with_cue_when_no_settings(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture, name="No-prefill test",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#group-action-export").click()
        addr = page.locator("#export-self-email-addr")
        expect(addr).to_have_value("")
        cue = page.locator("#export-self-email-cue")
        expect(cue).to_contain_text("enter your email")

    def test_email_button_appears_after_export(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture, name="Email button visible",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#group-action-export").click()
        # Email button lives inside the post-export result row, which
        # starts hidden. Export creates the file but does NOT navigate
        # to mailto: by itself; the result row reveals along with the
        # View link and the Email button.
        expect(page.locator("#group-export-result")).to_be_hidden()
        with page.expect_download(timeout=20000):
            page.locator("#group-export-go").click()
        expect(page.locator("#group-export-result")).to_be_visible()
        expect(page.locator("#group-export-email-btn")).to_be_visible()
