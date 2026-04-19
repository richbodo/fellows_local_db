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

    def test_auth_status_503_falls_through_when_marker_set(self, context, base_url_fixture):
        """A transient /api/auth/status 503 must NOT show the 'Authentication
        check failed' panel when this origin has been authenticated before.
        The offline-resilience fallback (phase-1) demotes the failure to a
        quiet email gate with the build badge labelled 'server: unreachable'.
        """
        page = context.new_page()
        # Simulate "has been authed here before" (marker persisted via
        # localStorage), then 503 on auth-status.
        page.add_init_script(
            "window.localStorage.setItem('fellows_authenticated_once', '1');"
        )
        page.route(
            AUTH_STATUS_PATH,
            lambda r: r.fulfill(status=503, body="service unavailable"),
        )
        try:
            page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(300)
            # The error panel must NOT appear.
            assert page.locator("#auth-error-panel").is_hidden(), (
                "Auth-error panel surfaced despite marker being set — fallback failed."
            )
            # Email gate is the quiet fallback view.
            expect(page.locator("#install-gate-private")).to_be_visible()
            # Build badge reflects server unreachable.
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
