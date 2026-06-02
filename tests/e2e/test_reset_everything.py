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


class TestResetEverythingBackupPrompt:
    """Issue #123: Reset Everything's destructive flow now opens a
    backup-first prompt before the existing window.confirm. Three paths
    out of the prompt — Download, Skip, Cancel — each pinned here so a
    future regression that flips back to "single confirm, no backup
    offer" or that breaks one branch is caught loudly.
    """

    def _open_app(self, context, base_url_fixture):
        page = context.new_page()
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        # Force downloadBlob's anchor-fallback path so page.expect_download
        # fires. See the matching stub in tests/e2e/conftest.py's
        # _STANDALONE_DISPLAY_INIT for the longer rationale.
        page.add_init_script(
            "try { delete window.showSaveFilePicker; }"
            " catch (e) { window.showSaveFilePicker = undefined; }"
        )
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.locator("#loading").wait_for(state="hidden", timeout=10000)
        return page

    def test_cancel_aborts_without_resetting(self, context, base_url_fixture):
        """Cancel must close the prompt and NOT trigger the destructive
        flow. Pre-fix the button went straight to a single confirm; this
        test pins the new "you can back out cleanly" affordance.

        We assert by side-effects (no /api/logout, no navigation to
        ?cache_reset=full) rather than by stubbing window.confirm —
        Playwright's UtilityScript evaluation context shows up in
        confirm-stub stacks regardless of user-side calls, making the
        stub-counter approach unreliable.
        """
        page = self._open_app(context, base_url_fixture)
        try:
            logout_calls = {"n": 0}
            def _count_logout(r):
                if r.url.endswith("/api/logout"):
                    logout_calls["n"] += 1
            page.on("request", _count_logout)

            url_before = page.url

            page.click("#reset-everything-button")
            page.locator("#reset-backup-prompt").wait_for(state="visible", timeout=2000)
            page.click("#reset-backup-cancel")
            page.locator("#reset-backup-prompt").wait_for(state="hidden", timeout=2000)

            # Wait a beat to give any leaked async work a chance to fire.
            page.wait_for_timeout(200)

            assert logout_calls["n"] == 0, "no /api/logout should fire on Cancel"
            assert page.url == url_before, (
                f"page should not have navigated on Cancel; was {url_before!r} → {page.url!r}"
            )
        finally:
            page.close()

    def test_skip_proceeds_to_destructive_confirm_and_resets(self, context, base_url_fixture):
        """Skip closes the prompt, surfaces the existing destructive
        confirm, and on accept fires the same clearEverything path the
        original button did. Mirrors test_reset_everything_posts_logout
        for the no-backup-needed user.
        """
        page = self._open_app(context, base_url_fixture)
        # Auto-accept the destructive confirm.
        page.evaluate("window.confirm = function () { return true; };")
        page.route(
            "**/api/logout",
            lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok": true}'),
        )
        try:
            page.click("#reset-everything-button")
            page.locator("#reset-backup-prompt").wait_for(state="visible", timeout=2000)
            with page.expect_request("**/api/logout") as req_info:
                page.click("#reset-backup-skip")
            assert req_info.value.method == "POST"
            page.wait_for_url("**/?cache_reset=full*", timeout=5000)
        finally:
            page.close()

    def test_download_triggers_export_then_proceeds_to_reset(self, context, base_url_fixture):
        """Download fires the same export pipeline as Settings → "Download
        my user data", then the prompt closes and the destructive
        confirm runs. The fresh-context relationships.db is small but
        non-empty (the worker bootstraps the schema at init), so the
        download fires a real Blob.
        """
        page = self._open_app(context, base_url_fixture)
        page.evaluate("window.confirm = function () { return true; };")
        page.route(
            "**/api/logout",
            lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok": true}'),
        )
        try:
            page.click("#reset-everything-button")
            page.locator("#reset-backup-prompt").wait_for(state="visible", timeout=2000)

            with page.expect_download(timeout=5000) as dl_info:
                page.click("#reset-backup-download")
            download = dl_info.value
            assert download.suggested_filename.startswith("ehf-fellows-private-data-")
            assert download.suggested_filename.endswith(".db")

            # After the download fires, the prompt closes and the
            # destructive flow proceeds to /api/logout.
            page.wait_for_url("**/?cache_reset=full*", timeout=5000)
        finally:
            page.close()
