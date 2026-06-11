"""E2E: browser-tab + install-landing routing on localhost.

After issue #58 LOW #2, localhost browser-tab visits act as the app
(directory) by default — the previous dev passthrough that forced every
fresh localhost session through the install landing was confusing every
time after Clear App Cache. The install landing still exists and is
reachable via `?gate=1` (forces the email gate UI).

The deploy_server-backed test classes at the bottom of this file cover:

- TestInstallLandingEscape (M1): the "use the directory in this tab"
  link rescues testers whose browser never fires `beforeinstallprompt`
  (Todd's MacBook Pro Chrome case).
- TestRedeemDoubleFireGuard (M2): tryUnlockFromHash's sessionStorage
  guard prevents bfcache / back-button replay from re-POSTing a
  single-use token (Anne-Marie iOS-class case).
"""
from __future__ import annotations

import json
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest
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

    def test_install_unsupported_hint_uses_plain_language(self, page, base_url_fixture):
        """#219: the on-click install-fallback hint must lead with the action,
        not browser-vendor jargon. The element is static markup (hidden until
        an Install click with no `beforeinstallprompt`), so its text is in the
        DOM regardless of route — we assert on it directly."""
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        text = (page.locator("#install-unsupported-hint").text_content() or "").lower()
        assert "open the existing install" in text
        assert "use the directory in this tab" in text
        # Regression guard: the jargon lead ("install prompt", "yet",
        # "two ways forward") must not creep back in.
        assert "install prompt" not in text
        assert "two ways forward" not in text


def _issue_token(deploy_server):
    """Drive POST /api/send-unlock and return the token from the recorder."""
    parsed = urlparse(deploy_server["base_url"])
    body = json.dumps({"email": deploy_server["test_email"]}).encode("utf-8")
    conn = HTTPConnection(parsed.hostname, parsed.port, timeout=3)
    conn.request(
        "POST",
        "/api/send-unlock",
        body=body,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        },
    )
    conn.getresponse().read()
    conn.close()
    assert deploy_server["sent"], "stubbed Postmark recorder never fired"
    return deploy_server["sent"][-1]["url"].rsplit("/#/unlock/", 1)[-1]


@pytest.fixture
def deploy_browser_page(context, deploy_server):
    """Browser-tab Playwright page against the deploy server (no PWA standalone fake).

    Auth state and recorder are reset per test so each starts clean.
    """
    page = context.new_page()
    state = deploy_server["auth_state"]
    with state.lock:
        state.tokens.clear()
        state.rate_buckets.clear()
    deploy_server["sent"].clear()
    try:
        yield page
    finally:
        page.close()


class TestInstallLandingEscape:
    """M1: when the install landing renders for a verify-token success in a
    browser tab, the 'use the directory in this tab' link must boot the
    directory directly. Covers the case (Todd, MacBook Pro Chrome) where
    `beforeinstallprompt` never fires — Chrome's engagement heuristic, an
    already-installed PWA on the profile, or a SW that hasn't activated yet.
    """

    def test_use_in_tab_link_boots_directory(self, deploy_browser_page, deploy_server):
        page = deploy_browser_page
        token = _issue_token(deploy_server)

        # 1. Land on the install landing by clicking the email link in a
        #    browser tab. tryUnlockFromHash POSTs verify-token, the cookie
        #    lands, startBrowserUx renders the install landing.
        with page.expect_response(
            lambda r: "/api/verify-token" in r.url and r.request.method == "POST",
            timeout=8000,
        ) as verify_info:
            page.goto(
                f"{deploy_server['base_url']}/#/unlock/{token}", wait_until="load"
            )
        assert verify_info.value.status == 200

        # 2. Install landing visible; the use-in-tab link is the affordance
        #    we're about to exercise.
        page.wait_for_selector("#install-landing:not(.hidden)", timeout=4000)
        use_in_tab = page.locator("#install-use-in-tab")
        expect(use_in_tab).to_be_visible(timeout=2000)

        # #218: the folder-push "save your data to a folder" banner must NOT
        # show on the install landing — the user has no groups/notes to lose
        # yet and its CTA mismatches the Settings button. It's gated on
        # window.__dataProvider, which is only assigned once bootDirectoryAsApp
        # has run. (The in-process deploy_server has no Caddy COOP/COEP, so the
        # SQLite worker can't fully init here either; this pins the user-facing
        # invariant. The worker-available-on-landing path that originally
        # surfaced the bug is covered by Phase 1 manual QA — see
        # plans/pre_ship_ui_fixes_2026-05-29.md.)
        expect(page.locator("#folder-push-banner")).to_be_hidden()
        assert page.evaluate("window.__dataProvider == null"), (
            "boot must not have run while on the install landing"
        )

        # 3. Click it. Should: (a) hide the install landing, (b) boot the
        #    directory (renderDirectory reveals #app-wrap once data lands),
        #    (c) leave fellows_authenticated_once set so future bare-URL
        #    visits skip the install landing automatically.
        use_in_tab.click()
        # #directory-list is static markup so we can't gate on its presence;
        # wait on the visibility flip of #app-wrap which renderDirectory
        # toggles only after data has actually rendered.
        expect(page.locator("#app-wrap")).to_be_visible(timeout=8000)
        expect(page.locator("#install-landing")).to_be_hidden()

        marker = page.evaluate("localStorage.getItem('fellows_authenticated_once')")
        assert marker == "1", "fellows_authenticated_once must be set so future visits skip the landing"

        # Regression: the warm worker eagerly spawned at boot must survive
        # the install-landing transition. Pre-emptively terminating it
        # (the historic behavior) forced pickDataProvider to re-spawn,
        # racing OPFS SAH-pool handle-release from the just-killed worker
        # and surfacing as an indefinite 'Loading…' on use-in-tab.
        #
        # bootDirectoryAsApp clears bootDebugLines at entry, so the warm
        # spawn's own trace lines are gone by the time we read here. The
        # load-bearing signal is the *absence* of the re-spawn breadcrumb
        # that pickDataProvider would log if warmWorkerConsumed had been
        # set by initBrowserInstallMode. See initBrowserInstallMode and
        # pickDataProvider in app/static/app.js.
        boot_trace = page.evaluate("(window.__bootDebugLines || []).slice()")
        assert isinstance(boot_trace, list)
        respawn_events = [line for line in boot_trace if "warm worker was terminated" in line]
        assert not respawn_events, (
            "pickDataProvider hit the re-spawn path; install-landing must "
            f"keep the warm worker alive. Re-spawn lines: {respawn_events}\n"
            f"Full post-boot trace ({len(boot_trace)} lines):\n  "
            + "\n  ".join(boot_trace)
        )


class TestRedeemDoubleFireGuard:
    """M2: a second tryUnlockFromHash invocation with the same token in the
    same tab must skip the POST entirely. Covers iOS Safari bfcache restore
    and back-button replay. (The server now re-consumes a token for its full
    TTL — see deploy/magic_link_auth.py — so a redundant second POST would
    succeed rather than return 401; this per-tab guard still avoids the
    needless re-POST and keeps the hash stripped so a navigation event can't
    re-arm the loop.)
    """

    def test_second_invocation_skips_verify_token_post(self, context, deploy_server):
        page = context.new_page()
        state = deploy_server["auth_state"]
        with state.lock:
            state.tokens.clear()
            state.rate_buckets.clear()
        deploy_server["sent"].clear()
        try:
            # Pre-seed the per-tab guard. The guard's contract: if
            # sessionStorage['redeeming:<token>'] is already set when
            # tryUnlockFromHash runs, skip the POST and strip the hash.
            # add_init_script runs before app.js on every navigation, so the
            # key is present by the time the IIFE evaluates.
            page.add_init_script(
                "sessionStorage.setItem('redeeming:double-fire-test-token', '1');"
            )
            verify_post_count = {"n": 0}

            def _count(req):
                if "/api/verify-token" in req.url and req.method == "POST":
                    verify_post_count["n"] += 1

            page.on("request", _count)

            page.goto(
                f"{deploy_server['base_url']}/#/unlock/double-fire-test-token",
                wait_until="load",
            )
            # Give the boot path long enough to either fire or skip the POST.
            page.wait_for_timeout(1000)

            assert verify_post_count["n"] == 0, (
                "Guard failed: tryUnlockFromHash POSTed even though the per-tab "
                "redeeming marker was set"
            )
            # The hash must have been stripped — otherwise a subsequent
            # navigation event could re-arm the loop.
            assert "/unlock/" not in page.evaluate("location.hash")
        finally:
            page.close()

    def test_first_invocation_still_posts_when_guard_absent(
        self, deploy_browser_page, deploy_server
    ):
        """Sanity check: the guard only fires on second invocations. A fresh
        tab with no pre-existing marker must still hit verify-token, otherwise
        the guard would lock everyone out on first click."""
        page = deploy_browser_page
        token = _issue_token(deploy_server)

        with page.expect_response(
            lambda r: "/api/verify-token" in r.url and r.request.method == "POST",
            timeout=8000,
        ) as verify_info:
            page.goto(
                f"{deploy_server['base_url']}/#/unlock/{token}", wait_until="load"
            )
        assert verify_info.value.status == 200

        # The guard should now have set the key for this token.
        marker = page.evaluate(
            "sessionStorage.getItem('redeeming:" + token + "')"
        )
        assert marker, "guard did not record the in-flight redeem"
