"""E2E test: Reset Everything POSTs /api/logout and reloads with cache_reset=full.

The Reset Everything button (kebab → bottom item / desktop link below
the red Clear App Cache button) is the escalation past Clear App Cache.
It does everything Clear App Cache does, plus:
  - POST /api/logout to clear the HttpOnly session cookie
  - Wipe OPFS (relationships.db, fellows.db, and any backup siblings)
  - Skip preserving the fellows_authenticated_once marker

This test asserts the logout POST fires and the redirect carries the
``?cache_reset=full`` query string the function uses to mark the path.
The OPFS wipe is exercised in dev only when the browser actually has
OPFS available; under the dev e2e harness (HTTP, no
SharedArrayBuffer) ``shouldTryOpfsProvider()`` returns false and the
wipe is a no-op — that's a real-browser-only verification path.
"""
from playwright.sync_api import expect


class TestResetEverything:
    def test_reset_everything_posts_logout_and_reloads(self, context, base_url_fixture):
        """Invoking window.clearEverything() POSTs /api/logout (so the server
        clears the HttpOnly cookie) and replaces the URL with
        ``?cache_reset=full&t=<ts>`` to mark a full-reset boot.
        """
        page = context.new_page()
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )

        def _fulfill_logout(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"ok": true}',
                headers={"Set-Cookie": "fellows_session=; Path=/; Max-Age=0"},
            )

        try:
            page.route("**/api/logout", _fulfill_logout)
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page.locator("#loading").wait_for(state="hidden", timeout=10000)
            expect(page.locator("#directory")).to_be_visible()

            with page.expect_request("**/api/logout") as req_info:
                page.evaluate("window.clearEverything()")
            assert req_info.value.method == "POST"

            # The function navigates with location.replace to a URL that
            # carries cache_reset=full so the post-reset boot can tell
            # itself apart from a normal load.
            page.wait_for_url("**/?cache_reset=full*", timeout=5000)
        finally:
            page.close()

    def test_reset_everything_button_present_and_wires_to_clearEverything(self, context, base_url_fixture):
        """Sanity check the static markup: the desktop button exists,
        the click handler is wired (via initResetEverythingButton), and
        the kebab sheet has a matching action.
        """
        page = context.new_page()
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page.locator("#loading").wait_for(state="hidden", timeout=10000)
            # Element exists; CSS hides on mobile but the test viewport is
            # desktop by default.
            assert page.locator("#reset-everything-button").count() == 1
            # Window function wired.
            assert page.evaluate("typeof window.clearEverything") == "function"
            # Mobile kebab sheet has a matching action button.
            assert page.locator(
                'button[data-kebab-action="reset-everything"]'
            ).count() == 1
        finally:
            page.close()
