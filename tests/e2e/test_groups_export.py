"""E2E for PR 5 visual directory + HTML/ZIP export + PDF export.

Pins:
- #/groups/<id>/directory renders a portrait grid + Contact bar.
- "visual directory" row action on /#/groups goes there.
- Clicking a portrait opens a contact-info modal (name, mailto:, tel:,
  links, "View full profile" link).
- The Export panel's Export button:
  - generates a PDF (downloads, magic bytes %PDF-);
  - generates an HTML zip (downloads, ZIP magic PK\x03\x04, contains
    index.html + at least one fellow-*.html);
  - opens a mailto:?to=<self> when "email it to me" is checked AND
    the user has a self_email saved (otherwise toasts a hint).
"""
from __future__ import annotations

import io
import json
import re
import zipfile
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
    page.locator("#directory").wait_for(state="visible", timeout=5000)


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
    def test_html_zip_export_downloads_with_expected_structure(
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
        # Open the export panel; uncheck PDF + email-it-to-me; check HTML.
        page.locator("#group-action-export").click()
        page.locator("#export-pdf").uncheck()
        page.locator("#export-self-email").uncheck()
        page.locator("#export-html").check()
        with page.expect_download(timeout=15000) as dl_info:
            page.locator("#group-export-go").click()
        download = dl_info.value
        assert download.suggested_filename.endswith(".zip")
        path = download.path()
        with open(path, "rb") as f:
            data = f.read()
        # ZIP magic bytes.
        assert data[:4] == b"PK\x03\x04", "expected zip magic PK\\x03\\x04"
        # Inspect the archive: index.html + at least one fellow-*.html + styles.css.
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        assert "index.html" in names
        assert "styles.css" in names
        fellow_pages = [n for n in names if n.startswith("fellow-") and n.endswith(".html")]
        assert len(fellow_pages) >= 1, f"expected fellow-*.html files; got {names}"
        # index.html should reference one of the fellow pages.
        index_html = zf.read("index.html").decode("utf-8")
        assert any(p in index_html for p in fellow_pages), (
            "index.html should link to a fellow page"
        )

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
        page.locator("#export-html").uncheck()
        page.locator("#export-self-email").uncheck()
        page.locator("#export-pdf").check()
        with page.expect_download(timeout=20000) as dl_info:
            page.locator("#group-export-go").click()
        download = dl_info.value
        assert download.suggested_filename.endswith(".pdf")
        path = download.path()
        with open(path, "rb") as f:
            head = f.read(8)
        assert head[:5] == b"%PDF-", f"expected %PDF- magic, got {head!r}"

    def test_export_email_it_to_me_with_no_self_email_toasts_hint(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        fellows = _real_fellows(base_url_fixture)
        g = _create_group(
            base_url_fixture, name="Hint test",
            fellow_record_ids=[f[0] for f in fellows[:1]],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        _wait_for_directory(page)
        page.locator("#group-action-export").click()
        # Uncheck both files; only "email it to me" remains.
        page.locator("#export-pdf").uncheck()
        page.locator("#export-html").uncheck()
        # No self_email is saved (the autouse fixture wipes settings).
        page.locator("#group-export-go").click()
        toast = page.locator("#app-toast")
        expect(toast).to_be_visible(timeout=3000)
        expect(toast).to_contain_text("Set your email in Settings")
