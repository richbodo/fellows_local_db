"""E2E: browser-tab + install-landing routing on localhost.

After issue #58 LOW #2, localhost browser-tab visits act as the app
(directory) by default — the previous dev passthrough that forced every
fresh localhost session through the install landing was confusing every
time after Clear App Cache. The install landing still exists and is
reachable via `?gate=1` (forces the email gate UI).
"""
from playwright.sync_api import expect


class TestLocalhostBrowserTab:
    """Localhost browser-tab visits act as the app, not the install landing."""

    def test_browser_tab_on_localhost_loads_directory(self, page, base_url_fixture):
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        # Wait for boot to settle past the loading panel.
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        # Directory app shell should be visible; install landing should not.
        expect(page.locator("#app-wrap")).to_be_visible()
        expect(page.locator("#install-landing")).to_be_hidden()

    def test_gate_override_forces_email_gate_panel(self, page, base_url_fixture):
        """`?gate=1` is the dev escape hatch — must reach the email gate
        even on localhost where shouldActAsApp() otherwise returns true."""
        page.goto(base_url_fixture + "/?gate=1", wait_until="domcontentloaded")
        # The email gate panel renders inside #install-landing; the gate
        # form's email input is the load-bearing element.
        email_input = page.locator("input[type='email']").first
        expect(email_input).to_be_visible(timeout=5000)
        expect(page.locator("#app-wrap")).to_be_hidden()
