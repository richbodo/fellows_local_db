"""E2E: boot-error panel surfaces actionable copy + recovery affordances.

Issue #124. The previous panel led with a debugger-flavored hint
("If you are debugging: use the report below…") and pointed users at
a *Reload on the update banner* that doesn't exist in this state.
After PR #126 (the standalone-PWA auth-trap fix), the auth-failure
case no longer reaches this panel — it routes to the email gate. So
the panel is now strictly for genuinely-unknown failures (network
errors, 5xx, unexpected exceptions). The new copy + buttons reflect
that scope.

To force the panel to render in tests we need:
  - Standalone PWA mode (so bootDirectoryAsApp runs and PR #126's
    auth handoff is bypassed for non-auth errors).
  - /fellows.db AND /api/fellows returning 500 (non-auth error so
    the catch falls through to showBootFailure rather than handing
    off to startBrowserUx).
  - Empty IDB cache (default for fresh test contexts) so the
    api+idb fallback can't recover.
"""
from __future__ import annotations

from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


FELLOWS_DB = "**/fellows.db"
API_FELLOWS = "**/api/fellows**"


class TestBootErrorPanel:
    def test_panel_renders_actionable_copy_and_buttons(self, context, base_url_fixture):
        """Force a 500 boot failure and verify the new structure: lead
        copy, three action buttons, and a default-collapsed details
        block. Pre-#124 the panel led with debugger copy and offered
        only the Send-report button.
        """
        page = context.new_page()
        page.add_init_script(_STANDALONE_DISPLAY_INIT)
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        # Server-error (non-auth) on both critical fetches: forces the
        # boot chain into the showBootFailure branch rather than the
        # auth-handoff branch (PR #126) or the boot-stuck watchdog
        # branch (PR #119, fires only when getList never resolves).
        context.route(
            FELLOWS_DB,
            lambda r: r.fulfill(status=500, body="server error"),
        )
        context.route(
            API_FELLOWS,
            lambda r: r.fulfill(status=500, body="server error"),
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page.locator("#boot-error-panel").wait_for(state="visible", timeout=10000)

            # Lead copy is user-facing, not debugger-flavored. Scoped to
            # this panel — `.boot-error-lead` is also used by the
            # boot-stuck and auth-error panels.
            panel = page.locator("#boot-error-panel")
            lead = panel.locator(".boot-error-lead").inner_text()
            assert "couldn't load the directory" in lead.lower(), (
                f"lead should be user-facing copy; got: {lead!r}"
            )

            # The misleading "Reload on the update banner" hint is gone.
            hint = panel.locator(".boot-error-hint").inner_text()
            assert "update banner" not in hint.lower(), (
                f"old debugger hint about the update banner should be gone; got: {hint!r}"
            )

            # Three action buttons present.
            expect(page.locator("#boot-error-reload-button")).to_be_visible()
            expect(page.locator("#boot-error-clear-cache-button")).to_be_visible()
            expect(page.locator("#bug-report-button-boot-error")).to_be_visible()

            # Diagnostic dump is wrapped in a <details> and default-closed.
            details = page.locator(".boot-error-details")
            expect(details).to_be_visible()
            is_open = page.evaluate(
                "() => document.querySelector('.boot-error-details').open"
            )
            assert is_open is False, "details should be default-collapsed"

            # The pre still renders inside the details (so the dump is
            # there, just hidden by default). Use text_content (DOM
            # textContent) rather than inner_text, since collapsed
            # details content is display:none and inner_text returns "".
            pre_text = page.locator("#boot-error-pre").text_content()
            assert pre_text, "diagnostic pre should be populated"
        finally:
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)
            page.close()

    def test_reload_button_triggers_navigation(self, context, base_url_fixture):
        """The new in-panel Reload button must actually reload the page
        (delegates to window.location.reload). Pre-fix the panel had
        no in-panel reload affordance — the user had to find the red
        button at the bottom of the page or restart the PWA.
        """
        page = context.new_page()
        page.add_init_script(_STANDALONE_DISPLAY_INIT)
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        context.route(
            FELLOWS_DB,
            lambda r: r.fulfill(status=500, body="server error"),
        )
        context.route(
            API_FELLOWS,
            lambda r: r.fulfill(status=500, body="server error"),
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page.locator("#boot-error-panel").wait_for(state="visible", timeout=10000)

            # Drop the route blocks so the reload can settle (otherwise
            # it boots straight back into the same panel and the
            # navigation event behavior gets noisy).
            context.unroute(FELLOWS_DB)
            context.unroute(API_FELLOWS)

            with page.expect_navigation(timeout=10000):
                page.click("#boot-error-reload-button")
        finally:
            page.close()
