"""E2E for the Claude Desktop integration Settings UI.

The Settings page gains a "Claude Desktop integration (beta)" section
with a primary button that opens a preamble dialog. On preamble
Continue, the page sequentially triggers downloads of the three
``.mcpb`` files from the auth-gated routes added in
``deploy/server.py``. State is tracked in
``localStorage[fellows_mcpb_setup]`` so subsequent visits flip the
button to a refresh flow and reveal a "Directory data update
available" affordance when ``/build-meta.json``'s
``fellows_db_sha`` has changed since the last setup.

Plan: ``plans/easy_mcp_install.md`` § 4 + § 7.
"""
from __future__ import annotations

import re

from playwright.sync_api import expect


EXPECTED_BUNDLES = ["shared_data_ops", "private_data_ops", "comms"]


def _boot_to_settings(page, base_url: str) -> None:
    """Boot to the directory, wait for the worker, then navigate to
    Settings via hash. Mirrors the pattern used in the other Settings
    E2Es — initial boot from the directory route avoids a race where
    settings renders before the worker is ready."""
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    page.evaluate("location.hash = '#/settings'")
    page.wait_for_selector("#settings-mcpb-section", timeout=10000)


_MCPB_CLICK_INTERCEPT = """
// Install before the IIFE runs: capture every <a download> click on
// any anchor whose href starts with /mcpb/, and *prevent* the actual
// download navigation. This is more reliable than page.route for
// anchor-initiated downloads — Chromium routes anchor-with-download
// clicks through its internal downloads dispatcher, which page.route
// does not always intercept. The interception preserves order so the
// test can assert sequential dispatch.
window.__capturedMcpbClicks = [];
(function () {
  const origClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    const href = this.getAttribute('href') || '';
    if (href.indexOf('/mcpb/') !== -1) {
      window.__capturedMcpbClicks.push(href);
      return;
    }
    return origClick.call(this);
  };
})();
"""


def _install_anchor_intercept(page):
    """Patch HTMLAnchorElement.prototype.click to capture (and swallow)
    any anchor click whose href targets ``/mcpb/``. Returns nothing —
    captured hrefs accumulate in ``window.__capturedMcpbClicks`` and
    are read via ``page.evaluate``.
    """
    page.add_init_script(_MCPB_CLICK_INTERCEPT)


def _captured_clicks(page) -> list[str]:
    return page.evaluate("window.__capturedMcpbClicks || []")


class TestMcpbSection:
    def test_section_renders_with_intro_and_setup_button(self, standalone_page, base_url_fixture):
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        section = page.locator("#settings-mcpb-section")
        expect(section).to_be_visible()
        expect(section.locator("#settings-mcpb-intro")).to_contain_text(
            "Plug the directory into Claude Desktop"
        )
        btn = page.locator("#settings-mcpb-setup")
        expect(btn).to_be_visible()
        expect(btn).to_have_text("Set up Claude Desktop integration")

    def test_post_install_section_is_hidden_initially(self, standalone_page, base_url_fixture):
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        post = page.locator("#settings-mcpb-post-install")
        expect(post).to_be_hidden()

    def test_directory_update_row_is_hidden_initially(self, standalone_page, base_url_fixture):
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        row = page.locator("#settings-mcpb-update-row")
        expect(row).to_be_hidden()


class TestPreambleDialog:
    def test_setup_button_opens_preamble(self, standalone_page, base_url_fixture):
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        dialog = page.locator("#settings-mcpb-preamble-dialog")
        expect(dialog).to_be_visible()

    def test_preamble_describes_three_bundles(self, standalone_page, base_url_fixture):
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        bundles = page.locator(
            "#settings-mcpb-preamble-dialog .settings-mcpb-bundles li"
        )
        expect(bundles).to_have_count(3)
        # Each bundle's bold heading must be present.
        expect(bundles.nth(0)).to_contain_text("Fellows directory (Shared)")
        expect(bundles.nth(1)).to_contain_text("Your saved groups (Private)")
        expect(bundles.nth(2)).to_contain_text("Email staging (Communications)")

    def test_preamble_previews_install_warning_banner(self, standalone_page, base_url_fixture):
        """Issue #186 — the preamble previews Claude Desktop's red
        "unverified" banner so users aren't surprised."""
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        banner = page.locator(".settings-mcpb-warning--banner")
        expect(banner).to_be_visible()
        expect(banner).to_contain_text(
            "Installing will grant this extension access to everything on your computer"
        )

    def test_preamble_has_manual_setup_link(self, standalone_page, base_url_fixture):
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        link = page.locator(".settings-mcpb-manual-link a")
        expect(link).to_be_visible()
        expect(link).to_have_attribute(
            "href",
            re.compile(r"use_with_claude_desktop\.md$"),
        )


class TestPreambleActions:
    def test_cancel_closes_dialog_without_downloads(self, standalone_page, base_url_fixture):
        page = standalone_page
        _install_anchor_intercept(page)
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        dialog = page.locator("#settings-mcpb-preamble-dialog")
        expect(dialog).to_be_visible()
        page.locator(
            "#settings-mcpb-preamble-dialog .settings-folder-dialog-cancel"
        ).click()
        expect(dialog).not_to_be_visible()
        # Wait briefly to confirm no late downloads fire.
        page.wait_for_timeout(500)
        clicks = _captured_clicks(page)
        assert clicks == [], f"unexpected downloads fired on cancel: {clicks}"

    def test_continue_triggers_three_downloads_in_order(self, standalone_page, base_url_fixture):
        page = standalone_page
        _install_anchor_intercept(page)
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        page.click("#settings-mcpb-preamble-continue")

        # downloadFromUrl uses a 250ms inter-anchor delay; three downloads
        # need ~750ms. Wait for the status to flip past "Downloading" so
        # we know the chain completed.
        page.wait_for_function(
            """() => {
              const s = document.getElementById('settings-mcpb-status');
              return s && s.textContent && /Downloads triggered/.test(s.textContent);
            }""",
            timeout=5000,
        )
        clicks = _captured_clicks(page)
        assert len(clicks) == 3, f"expected 3 downloads, got: {clicks}"
        for url, name in zip(clicks, EXPECTED_BUNDLES):
            assert url.endswith(f"/mcpb/{name}.mcpb"), (
                f"expected {name}.mcpb URL, got: {url}"
            )


class TestPostSetupState:
    def test_button_relabels_after_first_setup(self, standalone_page, base_url_fixture):
        page = standalone_page
        _install_anchor_intercept(page)
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        page.click("#settings-mcpb-preamble-continue")
        page.wait_for_function(
            """() => {
              const s = document.getElementById('settings-mcpb-status');
              return s && /Downloads triggered/.test(s.textContent || '');
            }""",
            timeout=5000,
        )
        expect(page.locator("#settings-mcpb-setup")).to_have_text(
            "Re-download all extensions"
        )
        expect(page.locator("#settings-mcpb-post-install")).to_be_visible()
        expect(page.locator("#settings-mcpb-setup-meta")).to_be_visible()

    def test_setup_state_persists_in_localstorage(self, standalone_page, base_url_fixture):
        page = standalone_page
        _install_anchor_intercept(page)
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        page.click("#settings-mcpb-preamble-continue")
        page.wait_for_function(
            """() => {
              const s = document.getElementById('settings-mcpb-status');
              return s && /Downloads triggered/.test(s.textContent || '');
            }""",
            timeout=5000,
        )
        raw = page.evaluate("localStorage.getItem('fellows_mcpb_setup')")
        assert raw is not None
        import json as _json
        record = _json.loads(raw)
        assert record["setupAt"]
        assert record["refreshedAt"]

    def test_directory_update_row_shows_when_sha_changes(self, standalone_page, base_url_fixture):
        """If the user has set up before but the server now reports a
        different ``fellows_db_sha``, the Settings UI exposes the
        re-install-directory button."""
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        # Seed localStorage with a setup record that pins a stale sha,
        # then re-render the settings page (via hash bounce) so
        # refreshUiFromState runs.
        page.evaluate(
            """() => {
              localStorage.setItem('fellows_mcpb_setup', JSON.stringify({
                setupAt: new Date().toISOString(),
                refreshedAt: new Date().toISOString(),
                fellowsDbSha: 'stale-sha-not-on-server'
              }));
              window.bootBuildMeta = window.bootBuildMeta || {};
              window.bootBuildMeta.fellows_db_sha = 'fresh-server-sha';
            }"""
        )
        # Bounce off then back to trigger re-render.
        page.evaluate("location.hash = '#/about'")
        page.wait_for_function(
            "() => !document.getElementById('settings-mcpb-section')",
            timeout=5000,
        )
        page.evaluate("location.hash = '#/settings'")
        page.wait_for_selector("#settings-mcpb-section", timeout=5000)
        expect(page.locator("#settings-mcpb-update-row")).to_be_visible()
        expect(page.locator("#settings-mcpb-refresh-directory")).to_be_visible()
