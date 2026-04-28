"""E2E for the PR 2 groups index, detail page, and create-flow navigation.

Pins:
- Create from the rail navigates to #/groups/<id> and renders the detail.
- The /groups page lists saved groups with name, member count, created date.
- Empty state appears when there are no groups.
- Inline rename persists across reload.
- Delete with confirm() removes the row; cancel keeps it.
- Top-nav "Groups" link is wired.

Each test wipes the relationships DB via the API before running, so they're
order-independent within the session-scoped dev server.
"""
from __future__ import annotations

import json
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect


def _wait_for_directory(page):
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    page.locator("#directory").wait_for(state="visible", timeout=5000)


def _wipe_groups(base_url):
    """Delete all groups via the dev API. Idempotent."""
    parsed = urlparse(base_url)
    host, port = parsed.hostname, parsed.port
    conn = HTTPConnection(host, port, timeout=5)
    conn.request("GET", "/api/groups")
    r = conn.getresponse()
    body = r.read()
    conn.close()
    if r.status != 200:
        return
    try:
        groups = json.loads(body)
    except ValueError:
        return
    for g in groups:
        c2 = HTTPConnection(host, port, timeout=5)
        c2.request("DELETE", f"/api/groups/{g['id']}")
        c2.getresponse().read()
        c2.close()


def _aaron_row(page):
    link = page.locator("#directory a.dir-link", has_text="Aaron Bird").first
    expect(link).to_be_visible()
    return link.locator("xpath=..")


@pytest.fixture(autouse=True)
def _reset_relationships_db(base_url_fixture):
    _wipe_groups(base_url_fixture)
    yield


class TestGroupsIndex:
    def test_top_nav_groups_link_exists(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        nav_link = page.locator("#nav-groups-link")
        expect(nav_link).to_be_visible()
        expect(nav_link).to_have_attribute("href", "#/groups")

    def test_groups_page_empty_state(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/#/groups", wait_until="domcontentloaded")
        _wait_for_directory(page)
        empty = page.locator(".groups-empty")
        expect(empty).to_be_visible(timeout=5000)
        expect(empty).to_contain_text("No groups yet")

    def test_create_from_rail_navigates_to_detail_page(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        _aaron_row(page).locator(".dir-mark").click()
        page.locator("#group-rail-title").fill("Smoke group")
        page.locator("#group-rail-create").click()
        # Hash changes to #/groups/<n>; detail page renders.
        page.wait_for_url(lambda u: "#/groups/" in u, timeout=5000)
        title = page.locator(".group-detail-title")
        expect(title).to_have_text("Smoke group", timeout=3000)
        # Member count + name resolved via cross-DB JOIN on the dev server.
        expect(page.locator(".group-detail-meta")).to_contain_text("1 fellow")
        member_link = page.locator(".group-detail-members a")
        expect(member_link).to_have_text("Aaron Bird")
        # Draft is cleared after save.
        expect(page.locator("#group-rail-create")).to_be_disabled()
        expect(page.locator("#group-rail-members .group-rail-member-name")).to_have_count(0)

    def test_groups_index_lists_created_group(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        _aaron_row(page).locator(".dir-mark").click()
        page.locator("#group-rail-title").fill("Listed group")
        page.locator("#group-rail-create").click()
        page.wait_for_url(lambda u: "#/groups/" in u, timeout=5000)
        # Now navigate to the index.
        page.locator("#nav-groups-link").click()
        page.wait_for_url(lambda u: u.endswith("#/groups"), timeout=3000)
        row = page.locator(".groups-table tbody tr")
        expect(row).to_have_count(1)
        expect(page.locator(".groups-name-link")).to_have_text("Listed group")
        expect(page.locator(".groups-cell-num")).to_have_text("1")

    def test_inline_rename_persists_across_reload(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        _aaron_row(page).locator(".dir-mark").click()
        page.locator("#group-rail-title").fill("old name")
        page.locator("#group-rail-create").click()
        page.wait_for_url(lambda u: "#/groups/" in u, timeout=5000)
        page.locator("#nav-groups-link").click()
        # Click rename; input appears.
        page.locator(".groups-action-rename").click()
        rename = page.locator(".groups-rename-input")
        expect(rename).to_be_visible()
        rename.fill("new name")
        rename.press("Enter")
        # Wait for the saving... → resolved name link.
        expect(page.locator(".groups-name-link")).to_have_text("new name", timeout=3000)
        # Reload — name persists.
        page.reload(wait_until="domcontentloaded")
        _wait_for_directory(page)
        expect(page.locator(".groups-name-link")).to_have_text("new name")

    def test_delete_with_confirm_removes_row_and_shows_empty_state(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.on("dialog", lambda d: d.accept())
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        _aaron_row(page).locator(".dir-mark").click()
        page.locator("#group-rail-title").fill("doomed")
        page.locator("#group-rail-create").click()
        page.wait_for_url(lambda u: "#/groups/" in u, timeout=5000)
        page.locator("#nav-groups-link").click()
        page.locator(".groups-action-delete").click()
        # Empty state replaces the table.
        expect(page.locator(".groups-empty")).to_be_visible(timeout=3000)
        expect(page.locator(".groups-table")).to_have_count(0)

    def test_delete_cancel_keeps_row(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.on("dialog", lambda d: d.dismiss())
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        _aaron_row(page).locator(".dir-mark").click()
        page.locator("#group-rail-title").fill("survivor")
        page.locator("#group-rail-create").click()
        page.wait_for_url(lambda u: "#/groups/" in u, timeout=5000)
        page.locator("#nav-groups-link").click()
        page.locator(".groups-action-delete").click()
        # Row stays.
        expect(page.locator(".groups-name-link")).to_have_text("survivor")

    def test_detail_member_link_navigates_to_fellow(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        _wait_for_directory(page)
        _aaron_row(page).locator(".dir-mark").click()
        page.locator("#group-rail-title").fill("nav test")
        page.locator("#group-rail-create").click()
        page.wait_for_url(lambda u: "#/groups/" in u, timeout=5000)
        page.locator(".group-detail-members a", has_text="Aaron Bird").click()
        page.wait_for_url(lambda u: "#/fellow/aaron_bird" in u, timeout=3000)
        expect(page.locator(".detail-name")).to_contain_text("Aaron Bird")
