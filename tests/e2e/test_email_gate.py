"""E2E tests: email-gate decision tree (Playwright + route-mock).

The dev server (``app/server.py``) returns ``authEnabled: false`` so the client
takes the local-dev passthrough branch. These tests use Playwright's
``page.route`` to return a synthetic ``/api/auth/status`` payload and exercise
each branch of ``startBrowserUx``'s decision tree as specified in
``docs/email_gate.md``.
"""
import json

import pytest
from playwright.sync_api import expect


AUTH_STATUS_PATH = "**/api/auth/status"


def _mock_auth_status(page, **overrides):
    payload = {
        "authEnabled": True,
        "authenticated": False,
        "hasSessionCookie": False,
        "installRecentlyAllowed": False,
    }
    payload.update(overrides)

    def _fulfill(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
            headers={"X-Fellows-Build": "e2e-mock"},
        )

    page.route(AUTH_STATUS_PATH, _fulfill)


class TestEmailGate:
    """Browser-mode decision tree per docs/email_gate.md."""

    def test_default_unauthenticated_shows_email_gate(self, context, base_url_fixture):
        page = context.new_page()
        try:
            _mock_auth_status(page, authEnabled=True, authenticated=False)
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            expect(page.locator("#install-gate-private")).to_be_visible()
            expect(page.locator("#install-landing")).to_be_hidden()
            expect(page.locator("#unlock-email-form")).to_be_visible()
        finally:
            page.close()

    def test_authenticated_without_recent_click_shows_email_gate(self, context, base_url_fixture):
        """Authenticated session alone does NOT grant install landing."""
        page = context.new_page()
        try:
            _mock_auth_status(
                page,
                authEnabled=True,
                authenticated=True,
                installRecentlyAllowed=False,
            )
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            expect(page.locator("#install-gate-private")).to_be_visible()
            expect(page.locator("#install-landing")).to_be_hidden()
        finally:
            page.close()

    def test_authenticated_with_recent_click_shows_install_landing(self, context, base_url_fixture):
        page = context.new_page()
        try:
            _mock_auth_status(
                page,
                authEnabled=True,
                authenticated=True,
                installRecentlyAllowed=True,
            )
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            expect(page.locator("#install-landing")).to_be_visible()
            expect(page.locator("#install-gate-private")).to_be_hidden()
        finally:
            page.close()

    def test_force_gate_query_overrides_authenticated_state(self, context, base_url_fixture):
        """?gate=1 always takes you to the gate, even with a valid session."""
        page = context.new_page()
        try:
            _mock_auth_status(
                page,
                authEnabled=True,
                authenticated=True,
                installRecentlyAllowed=True,
            )
            page.goto(base_url_fixture + "/?gate=1", wait_until="domcontentloaded")
            expect(page.locator("#install-gate-private")).to_be_visible()
            expect(page.locator("#install-landing")).to_be_hidden()
        finally:
            page.close()

    def test_expired_reason_shows_expired_banner(self, context, base_url_fixture):
        page = context.new_page()
        try:
            _mock_auth_status(page, authEnabled=True, authenticated=False)
            page.goto(
                base_url_fixture + "/?gate=1&reason=expired",
                wait_until="domcontentloaded",
            )
            banner = page.locator("#gate-reason-banner")
            expect(banner).to_be_visible()
            expect(banner).to_contain_text("expired")
        finally:
            page.close()

    def test_invalid_reason_shows_invalid_banner(self, context, base_url_fixture):
        page = context.new_page()
        try:
            _mock_auth_status(page, authEnabled=True, authenticated=False)
            page.goto(
                base_url_fixture + "/?gate=1&reason=invalid",
                wait_until="domcontentloaded",
            )
            banner = page.locator("#gate-reason-banner")
            expect(banner).to_be_visible()
            expect(banner).to_contain_text("isn't valid")
        finally:
            page.close()

    def test_marker_set_boots_directory_directly(self, context, base_url_fixture):
        """Browser-tab visits with the marker set skip the install landing and
        boot the directory via the API — "URL-just-works" (docs/email_gate.md).
        The marker is the signal that this browser has used the app before,
        so we act as the app rather than forcing install-landing again.
        """
        page = context.new_page()
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page.locator("#loading").wait_for(state="hidden", timeout=10000)
            # Directory visible, install landing and email gate both hidden.
            expect(page.locator("#directory")).to_be_visible()
            expect(page.locator("#install-landing")).to_be_hidden()
            expect(page.locator("#install-gate-private")).to_be_hidden()
        finally:
            page.close()

    def test_marker_set_with_gate_override_still_shows_gate(self, context, base_url_fixture):
        """?gate=1 always wins, even when the marker is set. Gives the user
        (or a dev) an explicit escape back to the email gate for a fresh
        session — e.g., when handing the app off to another fellow on a
        shared device.
        """
        page = context.new_page()
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        try:
            _mock_auth_status(page, authEnabled=True, authenticated=False)
            page.goto(base_url_fixture + "/?gate=1", wait_until="domcontentloaded")
            expect(page.locator("#install-gate-private")).to_be_visible()
            expect(page.locator("#directory")).to_be_hidden()
        finally:
            page.close()

    def test_marker_set_api_unreachable_falls_back_to_gate(self, context, base_url_fixture):
        """With marker set but the API is completely unreachable, the as-app
        boot fails and we hand off to startBrowserUx — which, finding auth
        status also down, shows the quiet email-gate fallback. No scary
        auth-error panel.
        """
        page = context.new_page()
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        # Nuke every endpoint the boot path could use: the worker-owned
        # fellows.db (post-cutover directory data source), the api+idb
        # fallback's /api/fellows, and the auth-status check. All must
        # fail for this test to exercise the "everything 5xx with
        # marker" safety net.
        #
        # /fellows.db is fetched by the dedicated worker (not the page),
        # so context.route is required — page.route does not intercept
        # Web Worker requests. The other two are page-fetched and would
        # also work with page.route, but using context.route for all
        # three keeps the mock setup uniform.
        context.route(
            "**/fellows.db",
            lambda r: r.fulfill(status=503, body="service unavailable"),
        )
        context.route(
            "**/api/fellows*",
            lambda r: r.fulfill(status=503, body="service unavailable"),
        )
        context.route(
            AUTH_STATUS_PATH,
            lambda r: r.fulfill(status=503, body="service unavailable"),
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            # Wait up to 15s for the boot path to chain through:
            #   worker spawn → ensureFellowsDb 503 →
            #   bootDirectoryAsApp.catch → startBrowserUx →
            #   /api/auth/status 503 → quiet email gate.
            # The chain is longer than the pre-cutover one (the worker
            # init + ensureFellowsDb fetch are extra steps); 15s is the
            # comfortable upper bound observed across the test matrix.
            page.locator("#install-gate-private").wait_for(state="visible", timeout=15000)
            # No scary error panel.
            assert page.locator("#auth-error-panel").is_hidden(), (
                "Auth-error panel surfaced despite marker being set."
            )
            server_line = page.locator("#build-badge-server")
            expect(server_line).to_contain_text("unreachable")
        finally:
            page.close()

    def test_auth_status_503_without_marker_still_shows_error_panel(self, context, base_url_fixture):
        """First-time visitor hitting a 503 still sees the loud error panel.
        The fallback is opt-in to "we have been here before" — a genuine
        first-time failure should not silently degrade.
        """
        page = context.new_page()
        # No marker — ensure clean storage.
        page.add_init_script(
            "window.localStorage.removeItem('fellows_authenticated_once');"
        )
        page.route(
            AUTH_STATUS_PATH,
            lambda r: r.fulfill(status=503, body="service unavailable"),
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(300)
            expect(page.locator("#auth-error-panel")).to_be_visible()
        finally:
            page.close()

    def test_gate_diag_block_renders_expected_fields(self, context, base_url_fixture):
        """The gate's auth-debug block carries enough environment info to triage
        an install/email-gate problem from a screenshot. Asserting the field
        labels (rather than full values) keeps the test stable across
        browsers/builds.
        """
        page = context.new_page()
        try:
            _mock_auth_status(page, authEnabled=True, authenticated=False)
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            block = page.locator("#auth-debug-private")
            expect(block).to_be_visible()
            pre = page.locator("#auth-debug-private-pre")
            text = pre.inner_text()
            assert "auth:" in text
            assert "GET /api/auth/status → HTTP 200" in text
            assert "authEnabled=True" in text or "authEnabled=true" in text
            assert "app:" in text
            assert "userAgent:" in text
            assert "platform:" in text
            assert "viewport:" in text
            assert "display:" in text
            # last_submit only appears after a Send link click — not yet.
            assert "last_submit:" not in text
            expect(page.locator("#auth-debug-private-copy")).to_be_visible()
        finally:
            page.close()

    def test_gate_diag_block_includes_last_submit_after_send(self, context, base_url_fixture):
        """Submitting the form populates a hash + ISO timestamp inside the diag
        block. The hash matches deploy/server.py's email_hash_prefix
        (sha256(email).slice(0,12)) so a maintainer can join a screenshot
        to a journald event without the user disclosing their address.
        """
        import json

        page = context.new_page()
        try:
            _mock_auth_status(page, authEnabled=True, authenticated=False)
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
            # Wait for the post-submit refresh to land in the pre block.
            pre = page.locator("#auth-debug-private-pre")
            page.wait_for_function(
                "el => el && el.textContent && el.textContent.indexOf('last_submit:') !== -1",
                arg=pre.element_handle(),
                timeout=3000,
            )
            text = pre.inner_text()
            assert "last_submit: hash=" in text
            # 12-hex prefix exactly.
            import re

            m = re.search(r"last_submit: hash=([0-9a-f]{12})\s+at\s+(\S+)", text)
            assert m, f"expected last_submit hash+ts, got: {text}"
        finally:
            page.close()

    def test_send_diagnostics_posts_sanitized_payload(self, context, base_url_fixture):
        """Clicking 'Send diagnostics' on the gate POSTs the ring buffer +
        diag block to /api/client-errors. We mock 204 here to assert the
        client-side wiring (payload shape, status feedback). The server
        sanitizer is verified separately in tests/test_client_error_sanitizer.py
        and tests/test_deploy_client_errors.py.
        """
        page = context.new_page()
        captured = {"body": None}

        def _capture(route):
            req = route.request
            try:
                captured["body"] = req.post_data_json
            except Exception:
                captured["body"] = json.loads(req.post_data or "{}")
            route.fulfill(status=204, body="")

        try:
            _mock_auth_status(page, authEnabled=True, authenticated=False)
            page.route("**/api/client-errors", _capture)
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            expect(page.locator("#auth-debug-private-send")).to_be_visible()
            with page.expect_request("**/api/client-errors"):
                page.locator("#auth-debug-private-send").click()
            page.wait_for_function(
                "el => el && el.textContent && el.textContent.indexOf('Sent') !== -1",
                arg=page.locator("#auth-debug-private-copy-status").element_handle(),
                timeout=3000,
            )
            body = captured["body"]
            assert isinstance(body, dict)
            assert isinstance(body.get("events"), list)
            assert "ua" in body and body["ua"]
            assert "displayMode" in body
            assert body["displayMode"] in ("standalone", "browser-tab")
            # No email in the payload — never. The hash prefix is opt-in
            # after a submit (this test doesn't submit, so it's absent).
            assert "lastSubmitHashPrefix" not in body
        finally:
            page.close()

    def test_send_diagnostics_shows_failure_on_non_204(self, context, base_url_fixture):
        page = context.new_page()
        try:
            _mock_auth_status(page, authEnabled=True, authenticated=False)
            page.route(
                "**/api/client-errors",
                lambda r: r.fulfill(status=503, body="oops"),
            )
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page.locator("#auth-debug-private-send").click()
            page.wait_for_function(
                "el => el && el.textContent && el.textContent.indexOf('Send failed') !== -1",
                arg=page.locator("#auth-debug-private-copy-status").element_handle(),
                timeout=3000,
            )
            text = page.locator("#auth-debug-private-copy-status").inner_text()
            assert "Send failed" in text
        finally:
            page.close()

    def test_send_diagnostics_after_submit_includes_correlation_handle(
        self, context, base_url_fixture
    ):
        """Submitting an email populates lastSubmitInfo.emailHashPrefix
        (PR #69). A subsequent Send diagnostics click must include that
        prefix in the POST body so the maintainer can join the report
        to the matching event=send_unlock_email journald entry."""
        page = context.new_page()
        try:
            _mock_auth_status(page, authEnabled=True, authenticated=False)
            page.route(
                "**/api/send-unlock",
                lambda r: r.fulfill(
                    status=200, content_type="application/json",
                    body=json.dumps({"sent": True}),
                ),
            )
            page.route(
                "**/api/client-errors",
                lambda r: r.fulfill(status=204, body=""),
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
            # Read the request via expect_request's return value to avoid
            # the route-handler-closure timing issue.
            with page.expect_request("**/api/client-errors") as req_info:
                page.locator("#auth-debug-private-send").click()
            req = req_info.value
            assert req.method == "POST"
            try:
                body = req.post_data_json
            except Exception:
                body = json.loads(req.post_data or "{}")
            assert isinstance(body, dict), f"expected dict body, got {body!r}"
            assert "lastSubmitHashPrefix" in body
            import re
            assert re.fullmatch(r"[0-9a-f]{12}", body["lastSubmitHashPrefix"])
        finally:
            page.close()

    def test_back_to_gate_link_posts_logout_and_navigates(self, context, base_url_fixture):
        page = context.new_page()

        def _fulfill_logout(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"ok": true}',
                headers={"Set-Cookie": "fellows_session=; Path=/; Max-Age=0"},
            )

        try:
            _mock_auth_status(
                page,
                authEnabled=True,
                authenticated=True,
                installRecentlyAllowed=True,
            )
            page.route("**/api/logout", _fulfill_logout)
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            expect(page.locator("#install-landing")).to_be_visible()

            # Re-arm auth mock to return a gate state after logout.
            _mock_auth_status(
                page,
                authEnabled=True,
                authenticated=False,
                installRecentlyAllowed=False,
            )
            # expect_request captures the POST even when the page navigates
            # via location.replace() immediately after. Avoids the race where
            # the client-side fetch is in flight but the navigation fires
            # before the route handler records the call.
            with page.expect_request("**/api/logout") as req_info:
                page.locator("#back-to-gate-link").click()
            assert req_info.value.method == "POST"
            page.wait_for_url("**/?gate=1", timeout=5000)
            expect(page.locator("#install-gate-private")).to_be_visible()
        finally:
            page.close()


class TestInstallTelemetry:
    """Install-funnel telemetry: every meaningful step in the install
    landing flow POSTs a `kind=install` event to /api/client-errors so
    the maintainer can grep journald for "what fraction of install
    visits actually saw beforeinstallprompt fire vs. timed out?" The
    /api/client-errors sink is the same one the existing client errors
    use; the kind allowlist was extended in deploy/client_error_sanitizer.py.
    """

    def test_landing_shown_posts_install_event(self, context, base_url_fixture):
        page = context.new_page()
        try:
            _mock_auth_status(
                page,
                authEnabled=True,
                authenticated=True,
                installRecentlyAllowed=True,
            )
            with page.expect_request(
                lambda r: "/api/client-errors" in r.url and r.method == "POST",
                timeout=5000,
            ) as req_info:
                page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
                expect(page.locator("#install-landing")).to_be_visible()
            body = req_info.value.post_data_json
            assert body["events"][0]["kind"] == "install"
            assert body["events"][0]["msg"] == "landing_shown"
            # Sanity: build line, route, and displayMode shape match the
            # rest of the /api/client-errors payloads (and survive the
            # server-side sanitizer).
            assert body["route"] == "#install-landing"
            assert body["displayMode"] in ("standalone", "browser-tab")
        finally:
            page.close()

    def test_use_in_tab_click_posts_install_event(self, context, base_url_fixture):
        """The 'Use the directory in this tab' escape hatch fires its own
        event so we can tell apart 'never saw the prompt' from 'saw it
        and decided to escape' in the funnel."""
        page = context.new_page()
        try:
            _mock_auth_status(
                page,
                authEnabled=True,
                authenticated=True,
                installRecentlyAllowed=True,
            )
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            expect(page.locator("#install-landing")).to_be_visible()
            # Wait for the landing_shown POST to land so the next
            # expect_request doesn't race-capture it instead of the click
            # event we care about.
            page.wait_for_timeout(200)
            with page.expect_request(
                lambda r: "/api/client-errors" in r.url
                and r.method == "POST"
                and (r.post_data or "").find("use_in_tab_clicked") >= 0,
                timeout=5000,
            ) as req_info:
                page.locator("#install-use-in-tab").click()
            body = req_info.value.post_data_json
            assert body["events"][0]["kind"] == "install"
            assert body["events"][0]["msg"] == "use_in_tab_clicked"
        finally:
            page.close()
