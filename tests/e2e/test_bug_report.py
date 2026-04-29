"""E2E: bug-report dialog (in-app + install-landing surfaces)."""
import pytest
from playwright.sync_api import expect


class TestBugReportInApp:
    """In-app surface: floating "Report bug" button opens the dialog."""

    def test_button_opens_dialog_with_diagnostics(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)

        button = page.locator("#bug-report-button")
        expect(button).to_be_visible()
        button.click()

        dialog = page.locator("#bug-report-dialog")
        expect(dialog).to_be_visible()
        expect(dialog).to_have_attribute("aria-hidden", "false")

        body = page.locator("#bug-report-textarea").input_value()
        # User question template is present
        assert "What were you trying to do?" in body
        assert "What did you expect to happen?" in body
        assert "What actually happened?" in body
        # Sync diagnostics block populated with expected fields
        assert "diagnostics" in body
        assert "app: diag-" in body         # FELLOWS_UI_DIAG marker
        assert "userAgent:" in body          # browser fingerprint
        assert "display: standalone" in body  # standalone fixture in use
        assert "url: " in body
        # Destination is in the dialog UI
        expect(page.locator("#bug-report-dialog")).to_contain_text("richbodo@gmail.com")

    def test_cancel_closes_dialog(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)

        page.locator("#bug-report-button").click()
        dialog = page.locator("#bug-report-dialog")
        expect(dialog).to_be_visible()

        page.locator("#bug-report-close").click()
        expect(dialog).to_be_hidden()
        expect(dialog).to_have_attribute("aria-hidden", "true")

    def test_escape_closes_dialog(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        page.locator("#directory").wait_for(state="visible", timeout=5000)

        page.locator("#bug-report-button").click()
        dialog = page.locator("#bug-report-dialog")
        expect(dialog).to_be_visible()

        page.keyboard.press("Escape")
        expect(dialog).to_be_hidden()


class TestBugReportInstallLanding:
    """Pre-app surface: install landing exposes an inline 'report a problem' button."""

    def test_install_landing_inline_button_opens_dialog(self, page, base_url_fixture):
        # Mock prod-shaped auth status so the install landing renders even
        # on the localhost dev server. Without this, issue #58 LOW #2's
        # localhost passthrough boots straight into the directory and the
        # install landing is never shown.
        import json

        def _fulfill(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "authEnabled": True,
                    "authenticated": True,
                    "hasSessionCookie": True,
                    "installRecentlyAllowed": True,
                }),
                headers={"X-Fellows-Build": "e2e-mock"},
            )
        page.route("**/api/auth/status", _fulfill)
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        expect(page.locator("#install-landing")).to_be_visible()

        inline_btn = page.locator("#bug-report-button-install")
        expect(inline_btn).to_be_visible()
        inline_btn.click()

        dialog = page.locator("#bug-report-dialog")
        expect(dialog).to_be_visible()

        body = page.locator("#bug-report-textarea").input_value()
        assert "userAgent:" in body
        # Pre-app surface: browser-tab mode, not standalone
        assert "display: browser-tab" in body
        # Sync-only path means the in-app extra block is NOT appended
        assert "additional diagnostics" not in body
