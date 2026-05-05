"""E2E: bug-report dialog (in-app + install-landing + gate surfaces)."""
import json
import pytest
from playwright.sync_api import expect


def _mock_auth_status_for_gate(page):
    page.route(
        "**/api/auth/status",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "authEnabled": True,
                "authenticated": False,
                "hasSessionCookie": False,
                "installRecentlyAllowed": False,
            }),
            headers={"X-Fellows-Build": "e2e-mock"},
        ),
    )


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
        # FELLOWS_UI_DIAG format is <YYYY-MM-DD>-<short-sha>[-<label>]
        # since PR #80; assert structure, not a specific tag.
        import re
        assert re.search(r"app: \d{4}-\d{2}-\d{2}-[0-9a-f]+", body), \
            "diagnostics should include 'app: <YYYY-MM-DD>-<sha>' line, got: " + repr(body)
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


class TestBugReportGate:
    """Pre-app surface: email gate exposes the same inline 'report a problem' button."""

    def test_gate_inline_button_includes_browser_and_no_submit_yet(
        self, page, base_url_fixture
    ):
        _mock_auth_status_for_gate(page)
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        expect(page.locator("#install-gate-private")).to_be_visible()

        page.locator("#bug-report-button-gate").click()
        dialog = page.locator("#bug-report-dialog")
        expect(dialog).to_be_visible()

        body = page.locator("#bug-report-textarea").input_value()
        assert "userAgent:" in body
        assert "platform:" in body
        assert "display: browser-tab" in body
        assert "last_submit:" not in body  # nothing submitted yet

    def test_gate_bug_report_includes_last_submit_correlation_handle(
        self, page, base_url_fixture
    ):
        """Submit on the gate, then open the bug report — body must carry the
        same hash+timestamp the server's event=send_unlock_email logs.
        """
        _mock_auth_status_for_gate(page)
        page.route(
            "**/api/send-unlock",
            lambda r: r.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"sent": True}),
            ),
        )
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#unlock-email").fill("foo@bar.com")
        with page.expect_request("**/api/send-unlock"):
            page.locator("#unlock-submit").click()
        # Wait for the async sha256 to populate lastSubmitInfo.
        page.wait_for_function(
            "el => el && el.textContent && el.textContent.indexOf('last_submit:') !== -1",
            arg=page.locator("#auth-debug-private-pre").element_handle(),
            timeout=3000,
        )

        page.locator("#bug-report-button-gate").click()
        body = page.locator("#bug-report-textarea").input_value()
        assert "last_submit: hash=" in body

        import re
        # foo@bar.com → sha256 → 'b19d...' — assert the 12-hex shape, not value.
        m = re.search(r"last_submit: hash=([0-9a-f]{12})\s+at\s+(\S+)", body)
        assert m, f"expected last_submit line, got: {body[-400:]}"


class TestBugReportHttpCapture:
    """Boot-path non-2xx fetches push into the bug-report ring buffer so the
    body shows users the server returned an error code (e.g. 404) — without
    making them play journald-grep with the maintainer.
    """

    def test_404_on_api_fellows_appears_in_bug_report_body(
        self, context, base_url_fixture
    ):
        page = context.new_page()
        # Marker set: shouldActAsApp() returns true → bootDirectoryAsApp.
        # Post-P1 cutover, /api/fellows is only fetched on the api+idb
        # fallback path — which is triggered when the worker's
        # ensureFellowsDb gets a 401/403. So:
        #   /fellows.db → 401 (worker fetch; needs context.route since
        #     page.route doesn't intercept Web Worker requests)
        #   /api/fellows* → 404 (the error captured for the bug report)
        #   /api/auth/status → 503 (so startBrowserUx falls through to
        #     the quiet email-gate fallback where the bug-report button
        #     on the gate is reachable)
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        context.route(
            "**/fellows.db",
            lambda r: r.fulfill(status=401, body="unauthorized"),
        )
        context.route(
            "**/api/fellows*",
            lambda r: r.fulfill(status=404, body="Not Found"),
        )
        context.route(
            "**/api/auth/status",
            lambda r: r.fulfill(status=503, body="auth check unavailable"),
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            # Boot will fail; surfaces will switch to email gate fallback.
            # The chain is longer post-cutover (worker spawn + ensureFellowsDb
            # before falling through), so wait up to 15s.
            page.locator("#install-gate-private").wait_for(
                state="visible", timeout=15000
            )
            page.locator("#bug-report-button-gate").click()
            body = page.locator("#bug-report-textarea").input_value()
            assert "GET /api/fellows" in body and "→ 404" in body
        finally:
            page.close()
