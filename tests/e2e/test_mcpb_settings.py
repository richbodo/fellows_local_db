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
    """Boot to the directory, wait for the two-phase load to *complete*,
    then navigate to Settings via hash. Waiting only for the worker
    provider isn't enough: the boot's getList and getFull completions
    each call route() (app.js lines ~10640 and ~10671), and the late
    getFull-triggered route() re-renders the settings page if we've
    navigated there in the meantime. That re-render tears down the
    preamble <dialog> DOM mid-test and surfaces as flaky
    "element was detached from the DOM" / "element is not visible"
    errors on whichever dialog control the test was about to click.
    """
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    # Boot phase mark `get_full_done` is set after the phase-2 route()
    # call fires; once it's present we know no further boot-driven
    # re-render will land on the settings page we're about to open.
    page.wait_for_function(
        "() => window.__bootMarks && window.__bootMarks.get_full_done != null",
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

    # The directory-update affordance moved from Settings → Claude
    # Desktop integration to the About page's update box in PR #205
    # (issue #202). Coverage for "Re-install Claude Desktop bundles
    # when fellows_db_sha drifts" now lives in test_directory_data_update_flow.py
    # (paintDataRow's mcpStaleVsServer branch).


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
        """The Chrome-only platform note at the top of the dialog links
        to the manual walkthrough. Previously this link lived at the
        bottom; moved up after maintainer feedback on dialog ordering.
        """
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        platform_note = page.locator(
            "#settings-mcpb-preamble-dialog .settings-mcpb-platform-note"
        )
        expect(platform_note).to_be_visible()
        expect(platform_note).to_contain_text("Chrome and Chrome-derived")
        link = platform_note.locator("a")
        expect(link).to_have_attribute(
            "href",
            re.compile(r"use_with_claude_desktop\.md$"),
        )

    def test_preamble_lists_step_by_step_actions(self, standalone_page, base_url_fixture):
        """The "What happens next" steps appear above the action
        buttons so users know what to expect before clicking Continue.
        """
        page = standalone_page
        _boot_to_settings(page, base_url_fixture)
        page.click("#settings-mcpb-setup")
        steps = page.locator(
            "#settings-mcpb-preamble-dialog .settings-mcpb-steps li"
        )
        expect(steps).to_have_count(6)
        # Sanity-check a couple of step substrings — full copy lives in
        # the markup; we just want to know the section rendered with the
        # expected count and the key install-cue is present.
        all_text = steps.evaluate_all("(els) => els.map((e) => e.textContent).join(' | ')")
        assert "Continue" in all_text
        assert "Claude Desktop" in all_text
        assert "private_data_ops" in all_text
        assert "relationships.db" in all_text


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

    # test_directory_update_row_shows_when_sha_changes was removed in
    # PR #205 (issue #202). The Re-install Claude Desktop bundles
    # affordance migrated from the Settings → Claude Desktop integration
    # section to the About page (paintDataRow surfaces it inline with
    # the directory-data check result). New coverage lives in
    # test_directory_data_update_flow.py.
