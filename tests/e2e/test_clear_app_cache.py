"""E2E test: Clear App Cache also clears the HttpOnly session cookie.

The session cookie is HttpOnly so JS can't see or unset it directly.
``clearAllAppData()`` POSTs ``/api/logout`` first so the server sends a
clearing ``Set-Cookie`` header — without that, the prod button leaves
the user "logged in" even though their cache is gone.

This test asserts the POST happens. We don't validate the actual
``Set-Cookie`` header here because the dev server has no
``/api/logout`` endpoint; the deploy server's behaviour is covered in
``tests/test_deploy_auth_round_trip.py``.
"""
from playwright.sync_api import expect


class TestClearAppCache:
    def test_clear_app_cache_posts_logout(self, context, base_url_fixture):
        """Clicking the red Clear App Cache button triggers ``POST /api/logout``
        before tearing down local caches and reloading. Without this the
        HttpOnly ``fellows_session`` cookie survives the clear and the
        user stays signed in despite the visible reset.
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

            # expect_request captures the POST even when the page navigates
            # via location.replace() in clearAllAppData immediately after.
            with page.expect_request("**/api/logout") as req_info:
                page.evaluate("window.clearAllAppData()")
            assert req_info.value.method == "POST"
        finally:
            page.close()
