"""E2E for the copy-to-clipboard buttons next to mailto:/tel: links.

Pins:
- Fellow detail page: email row and mobile-number row each render a
  `.copy-btn` whose `data-copy` matches the value in the link.
- Visual-directory contact modal: same pattern.
- Group detail action bar: a permanent `#group-action-copy-emails` button
  is always rendered. Disabled when the group has no addresses; otherwise
  click → toast + addresses on the clipboard.
- The threshold banners no longer carry their own copy link (the action
  bar button is the canonical affordance).

Phase 1 (plans/local_first_worker_architecture.md): group setup that
previously went through the dev /api/groups HTTP route now drives the
worker via the worker_data fixture. Per-fellow lookups still go through
/api/fellows (which the dev server still serves) since they're
read-only and don't depend on the relationships data path.
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


def _fetch(base_url, path):
    """Read-only fetch against the dev server. Used for fellows lookups —
    /api/fellows still exists post-cutover (only relationships routes
    were retired)."""
    c = _conn(base_url)
    c.request("GET", path)
    r = c.getresponse()
    body = r.read()
    c.close()
    if r.status != 200:
        raise AssertionError(f"GET {path} → {r.status}")
    return json.loads(body)


def _wait_for_directory(page):
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    page.locator("#app-wrap").wait_for(state="visible", timeout=5000)


class TestFellowDetailCopyButtons:
    """Per-fellow copy icons next to mailto:/tel: links on the profile page."""

    def test_email_row_has_copy_button_with_correct_value(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        # aaron_bird is the canonical detail-view fixture and is known to
        # have both contact_email and mobile_number in the rebuilt DB.
        fellow = _fetch(base_url_fixture, "/api/fellows/aaron_bird")
        expected_email = fellow["contact_email"]
        page.goto(f"{base_url_fixture}/#/fellow/aaron_bird", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        # The button sits inside the "Contact Email" row, immediately
        # after the <a href="mailto:..."> link.
        btn = page.locator(
            f'#detail .copy-btn[data-copy="{expected_email}"]'
        )
        expect(btn).to_be_visible(timeout=5000)
        expect(btn).to_have_attribute("data-copy-label", "email")
        expect(btn).to_have_attribute("title", "Copy email")

    def test_phone_row_has_copy_button_and_tel_link(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        fellow = _fetch(base_url_fixture, "/api/fellows/aaron_bird")
        expected_phone = str(fellow["mobile_number"]).strip()
        page.goto(f"{base_url_fixture}/#/fellow/aaron_bird", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        # tel: link wraps the display form (added in this PR — previously
        # mobile_number was plain text).
        tel_link = page.locator('#detail a[href^="tel:"]')
        expect(tel_link).to_have_count(1, timeout=5000)
        # Copy button carries the *display* form, not the digits-only tel: form.
        btn = page.locator(
            f'#detail .copy-btn[data-copy="{expected_phone}"]'
        )
        expect(btn).to_be_visible()
        expect(btn).to_have_attribute("data-copy-label", "phone number")

    def test_clicking_copy_button_writes_to_clipboard_and_toasts(
        self, worker_data, base_url_fixture, context
    ):
        # writeText needs explicit permission in headless Chromium.
        context.grant_permissions(
            ["clipboard-read", "clipboard-write"], origin=base_url_fixture
        )
        page = worker_data.page
        fellow = _fetch(base_url_fixture, "/api/fellows/aaron_bird")
        expected_email = fellow["contact_email"]
        page.goto(f"{base_url_fixture}/#/fellow/aaron_bird", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        page.locator(f'#detail .copy-btn[data-copy="{expected_email}"]').click()
        toast = page.locator("#app-toast")
        expect(toast).to_be_visible(timeout=3000)
        expect(toast).to_have_text("Email copied")
        clipboard = page.evaluate("navigator.clipboard.readText()")
        assert clipboard == expected_email


class TestGroupActionBarCopyButton:
    """Permanent 'Copy email addresses' button next to CC/BCC."""

    def test_button_is_present_and_enabled_for_group_with_emails(
        self, worker_data, base_url_fixture
    ):
        page = worker_data.page
        # Pull two real fellows (every fellow has contact_email in the
        # canonical Knack rebuild).
        fellows = _fetch(base_url_fixture, "/api/fellows?full=1")
        chosen = [f for f in fellows if (f.get("contact_email") or "").strip()][:2]
        g = worker_data.create_group(
            "Copy button visible",
            fellow_record_ids=[f["record_id"] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        btn = page.locator("#group-action-copy-emails")
        expect(btn).to_be_visible(timeout=5000)
        expect(btn).to_be_enabled()
        expect(btn).to_contain_text("Copy email addresses")
        # Tooltip carries the recipient count.
        expect(btn).to_have_attribute("title", re.compile(r"Copy 2 email addresses"))

    def test_clicking_copies_all_addresses_and_toasts(
        self, worker_data, base_url_fixture, context
    ):
        context.grant_permissions(
            ["clipboard-read", "clipboard-write"], origin=base_url_fixture
        )
        page = worker_data.page
        fellows = _fetch(base_url_fixture, "/api/fellows?full=1")
        chosen = [f for f in fellows if (f.get("contact_email") or "").strip()][:5]
        emails = [f["contact_email"].strip() for f in chosen]
        g = worker_data.create_group(
            "Copy click test",
            fellow_record_ids=[f["record_id"] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        page.locator("#group-action-copy-emails").click()
        toast = page.locator("#app-toast")
        expect(toast).to_be_visible(timeout=3000)
        expect(toast).to_contain_text("addresses copied")
        clipboard = page.evaluate("navigator.clipboard.readText()")
        # All chosen emails must appear in the clipboard payload.
        for e in emails:
            assert e in clipboard, f"missing {e!r} in clipboard {clipboard!r}"

    def test_button_renders_below_warn_threshold(
        self, worker_data, base_url_fixture
    ):
        """The button is permanent — it shows up even on small groups
        where no threshold banner is present."""
        page = worker_data.page
        fellows = _fetch(base_url_fixture, "/api/fellows?full=1")
        chosen = [f for f in fellows if (f.get("contact_email") or "").strip()][:3]
        g = worker_data.create_group(
            "Three members",
            fellow_record_ids=[f["record_id"] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        # No threshold banner.
        expect(page.locator(".group-contact-banner--soft")).to_have_count(0)
        expect(page.locator(".group-contact-banner--hard")).to_have_count(0)
        # But the copy button is there.
        expect(page.locator("#group-action-copy-emails")).to_be_visible()

    def test_threshold_banners_no_longer_carry_inline_copy_link(
        self, worker_data, base_url_fixture
    ):
        """Soft and hard banners now point at the action-bar button
        instead of carrying their own copy link. Regression guard so
        the new permanent button doesn't end up duplicated."""
        page = worker_data.page
        fellows = _fetch(base_url_fixture, "/api/fellows?full=1")
        chosen = [f for f in fellows if (f.get("contact_email") or "").strip()][:60]
        assert len(chosen) == 60, "dev dataset must have ≥ 60 fellows with emails"
        g = worker_data.create_group(
            "Soft banner",
            fellow_record_ids=[f["record_id"] for f in chosen],
        )
        page.goto(f"{base_url_fixture}/#/groups/{g['id']}", wait_until="domcontentloaded")
        worker_data.wait()
        _wait_for_directory(page)
        soft = page.locator(".group-contact-banner--soft")
        expect(soft).to_be_visible(timeout=5000)
        # No <a> inside the soft banner anymore.
        expect(soft.locator("a")).to_have_count(0)
        # Banner refers users to the (one) permanent button.
        expect(soft).to_contain_text("Copy email addresses")
