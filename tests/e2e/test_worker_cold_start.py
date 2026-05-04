"""E2E for the cold-start auth-gating contract (L4a).

Two cases:

1. Authenticated cold start: clean OPFS profile + valid session →
   page commits to directory mode → issues ensureFellowsDb → worker
   fetches /fellows.db → directory renders. Verified via the network log.

2. Unauthenticated cold start: clean profile + no session → page
   commits to gate → makes ZERO GET /fellows.db requests. Worker is
   spawned (init only) then terminated.

Uses the deploy_server session fixture (tests/conftest.py:113) — the
in-process production server with magic-link auth on port 8766. The dev
server can't model unauthenticated cold-start because it has no auth.
"""
from __future__ import annotations

import json
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest


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
def deploy_clean_page(context, deploy_server):
    """Fresh page against the deploy server with auth state cleared."""
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


def test_authenticated_cold_start_fetches_fellows_db(
    deploy_clean_page, deploy_server
):
    """Clean OPFS + valid session → directory commits → ensureFellowsDb
    fetches /fellows.db once. The L4a contract: cold-start fetch happens
    after directory-mode commit, never speculatively before."""
    page = deploy_clean_page
    fellows_db_requests = []
    page.on(
        "request",
        lambda req: fellows_db_requests.append(req.url) if req.url.endswith("/fellows.db") else None,
    )

    # 1. Issue a magic-link token + redeem to get an authenticated cookie.
    token = _issue_token(deploy_server)
    page.goto(
        f"{deploy_server['base_url']}/#/unlock/{token}", wait_until="load"
    )
    # Install landing should render (token redeemed → install window open).
    page.wait_for_selector("#install-landing:not(.hidden)", timeout=5000)

    # 2. Click "use in tab" to boot the directory in browser-tab mode.
    use_in_tab = page.locator("#install-use-in-tab")
    use_in_tab.click()

    # 3. Directory should render. ensureFellowsDb must have fired exactly
    #    one /fellows.db request.
    page.locator("#app-wrap").wait_for(state="visible", timeout=10000)
    # Wait an extra tick for the worker fetch to land in the request log.
    page.wait_for_timeout(500)
    assert len(fellows_db_requests) >= 1, (
        f"expected ≥1 /fellows.db fetch after directory commit; got "
        f"{fellows_db_requests}"
    )


def test_unauthenticated_cold_start_makes_zero_fellows_db_requests(
    deploy_clean_page, deploy_server
):
    """Clean profile + no session → page commits to email gate, makes
    ZERO GET /fellows.db requests. The L4a contract: the worker is
    spawned for warm-up but never dials out for protected bundle data
    until the gate decision tree resolves to directory mode."""
    page = deploy_clean_page
    fellows_db_requests = []
    page.on(
        "request",
        lambda req: fellows_db_requests.append(req.url) if req.url.endswith("/fellows.db") else None,
    )

    # No token redeemed — bare load → email gate.
    page.goto(deploy_server["base_url"] + "/", wait_until="load")

    # Wait long enough that any inflight fetch would have completed.
    # The page-side terminates the warm worker on initEmailGate().
    page.wait_for_timeout(2500)

    # The email gate's input lives inside #install-gate-private; assert
    # we're on the gate, not the directory.
    page.wait_for_selector(
        "#install-gate-private:not(.hidden)", timeout=5000
    )

    # Critical assertion: zero /fellows.db requests.
    assert fellows_db_requests == [], (
        f"expected zero /fellows.db requests on unauthenticated cold "
        f"start; got {fellows_db_requests}"
    )
