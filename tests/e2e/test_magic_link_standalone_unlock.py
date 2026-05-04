"""E2E: standalone PWA unlock round-trip against deploy/server.py.

Issue #18, item 5. Regression guard for PR #16: a real browser running in
PWA standalone display mode must follow the SPA hash-route handler from
``#/unlock/<token>`` through ``POST /api/verify-token``, land the
``fellows_session`` cookie, and transition into the directory (not the
install landing — that path is only reached in browser-tab mode).

The other items in issue #18 (1-4, 6) are HTTP-only and live in
``tests/test_deploy_auth_round_trip.py``; this file is the one piece that
genuinely needs a browser to drive the SPA's standalone code path.
"""

from __future__ import annotations

import json
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest


_STANDALONE_DISPLAY_INIT = """
(function () {
  var orig = window.matchMedia.bind(window);
  window.matchMedia = function (q) {
    q = String(q);
    if (q.indexOf('display-mode: standalone') !== -1) {
      return {
        matches: true,
        media: q,
        addEventListener: function () {},
        removeEventListener: function () {}
      };
    }
    return orig(q);
  };
})();
"""


@pytest.fixture
def deploy_page(context, deploy_server):
    """Playwright page faking PWA standalone display mode against the deploy server.

    Auth state is reset per test (rate-limit and token dicts cleared) so a
    test that issues a token starts from a known-clean ``AuthState``.
    """
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    state = deploy_server["auth_state"]
    with state.lock:
        state.tokens.clear()
        state.consumed.clear()
        state.rate_buckets.clear()
    deploy_server["sent"].clear()
    try:
        yield page
    finally:
        page.close()


def _issue_token(deploy_server):
    """Drive ``POST /api/send-unlock`` and return the token from the recorder."""
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


def test_standalone_unlock_lands_session_cookie_and_loads_directory(
    deploy_page, deploy_server
):
    """PR #16 regression guard.

    In standalone mode the SPA's PWA decision tree is just::

        1. authStatus.authenticated?  → DIRECTORY
        2. otherwise                  → EMAIL GATE

    So the success signal for unlock is: verify-token POST succeeds, the
    HttpOnly session cookie appears in the jar, and the directory mounts
    (we wait for ``#directory-list`` to render, i.e. ``app-wrap`` no longer
    hidden — the same DOM that ``app/static/index.html`` defines).
    """
    token = _issue_token(deploy_server)

    # 1. Wrap the navigation so we deterministically capture the SPA's
    #    POST /api/verify-token. ``expect_response`` is the sync-API primitive
    #    for "do this action, then wait for a matching response".
    with deploy_page.expect_response(
        lambda r: "/api/verify-token" in r.url and r.request.method == "POST",
        timeout=8000,
    ) as verify_info:
        deploy_page.goto(
            f"{deploy_server['base_url']}/#/unlock/{token}", wait_until="load"
        )
    assert verify_info.value.status == 200

    # 2. Session cookie landed. ``fellows_session`` is HttpOnly so
    #    ``document.cookie`` cannot see it; read the context jar instead.
    cookies = deploy_page.context.cookies(deploy_server["base_url"])
    sessions = [c for c in cookies if c["name"] == "fellows_session"]
    assert len(sessions) == 1, f"expected one fellows_session cookie, got {cookies!r}"
    sc = sessions[0]
    assert sc["httpOnly"] is True
    # Playwright reports SameSite as "Strict" / "Lax" / "None" / unset.
    assert sc.get("sameSite", "").lower() == "strict"
    assert sc["value"]

    # 3. The hash was rewritten by tryUnlockFromHash() so a refresh wouldn't
    #    re-submit the (now-consumed) token.
    assert "/unlock/" not in deploy_page.evaluate("location.hash")

    # 4. Directory mounted (not the gate). #app-wrap drops `hidden` once the
    #    directory route renders; wait on the visibility flip explicitly
    #    (rather than just on #directory-list being attached, which is
    #    static markup and resolves before bootDirectoryAsApp runs).
    deploy_page.wait_for_function(
        "() => { var el = document.getElementById('app-wrap'); return el && !el.classList.contains('hidden'); }",
        timeout=8000,
    )
    app_wrap_hidden = deploy_page.evaluate(
        "document.getElementById('app-wrap')?.classList.contains('hidden')"
    )
    assert app_wrap_hidden is False, "#app-wrap should be visible after unlock"
