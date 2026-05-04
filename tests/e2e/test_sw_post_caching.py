"""Regression: the service worker must not try to cache POST responses.

Surfaced after PR #102 (Phase 1 cutover) hit prod: every 200-OK POST through
networkFirst (verify-token, send-unlock, logout) flooded the console with
`Uncaught (in promise) TypeError: Failed to execute 'put' on 'Cache':
Request method 'POST' is unsupported`. The response was still returned to
the page so functionality wasn't broken, but the noise made real errors
invisible in field-report screenshots.

Fix: gate `cache.put` on `request.method === 'GET'` and wrap in `.catch()`
so future cache failures (quota, private mode) also stay quiet. See sw.js's
`safeCachePut`.

Testing approach: instrument `Cache.prototype.put` inside the SW context
to record every put attempt with method + URL. Console-capture doesn't
work because Playwright's `page.on('console')` doesn't surface SW errors,
and the cache-state assertion alone can't distinguish the bug from the
fix (cache.put throws either way for POST — bug attempts it, fix skips
it). Recording attempts is the only way to see the difference from outside
the SW.

The bug only triggers when:
  (a) response status is 200 (not 204), AND
  (b) the SW is already installed and controlling the page.
On prod, condition (b) was met because the user had visited before. The
test reproduces (b) by warming the SW with a first navigation, then
issuing the magic-link redirect.
"""
from __future__ import annotations

import json
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest


# Patch installed into the SW's `self` to record every Cache.put attempt.
# `self.__cachePutAttempts__` is read back via Worker.evaluate after the test
# triggers the verify-token POST.
_SW_INSTRUMENT = """
() => {
    if (self.__cachePutAttempts__) return; // idempotent
    self.__cachePutAttempts__ = [];
    const original = Cache.prototype.put;
    Cache.prototype.put = function (req, res) {
        const url = (req && typeof req === 'object' && req.url) ? req.url : String(req);
        const method = (req && typeof req === 'object' && req.method) ? req.method : 'GET';
        self.__cachePutAttempts__.push({method, url});
        return original.call(this, req, res);
    };
}
"""


def _issue_token(deploy_server):
    """Drive POST /api/send-unlock and return the issued token."""
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
def deploy_clean_page_with_sw(context, deploy_server):
    """Fresh page with cookies cleared AND the SW pre-installed +
    instrumented to record cache.put attempts.

    Cookie clear: a leftover session would short-circuit the verify-token
    POST (auth_status returns authenticated:true and the page skips
    redemption).
    SW pre-install: an un-installed SW would let verify-token POST bypass
    the SW entirely (the bug only triggers when the SW intercepts).
    """
    context.clear_cookies()
    page = context.new_page()
    state = deploy_server["auth_state"]
    with state.lock:
        state.tokens.clear()
        state.rate_buckets.clear()
    deploy_server["sent"].clear()

    page.goto(deploy_server["base_url"] + "/?gate=1", wait_until="load")
    page.wait_for_function(
        "navigator.serviceWorker && navigator.serviceWorker.controller !== null",
        timeout=10000,
    )

    # Find the registered SW worker and install the cache.put recorder.
    sw_workers = [w for w in context.service_workers if "/sw.js" in w.url]
    assert sw_workers, f"no /sw.js worker registered; got {[w.url for w in context.service_workers]}"
    sw = sw_workers[-1]
    sw.evaluate(_SW_INSTRUMENT)

    try:
        yield {"page": page, "sw": sw}
    finally:
        page.close()


def _cache_put_attempts(sw):
    return sw.evaluate("self.__cachePutAttempts__ || []")


def test_sw_does_not_attempt_to_cache_post_responses(
    deploy_clean_page_with_sw, deploy_server
):
    """The exact path that broke in prod: returning user clicks a magic
    link, SW networkFirst intercepts the verify-token POST. Bug = SW
    calls Cache.put with the POST request → TypeError. Fix = SW skips
    the put for non-GET methods.
    """
    page = deploy_clean_page_with_sw["page"]
    sw = deploy_clean_page_with_sw["sw"]

    token = _issue_token(deploy_server)
    page.goto(
        f"{deploy_server['base_url']}/#/unlock/{token}", wait_until="load"
    )
    page.wait_for_selector("#install-landing:not(.hidden)", timeout=5000)
    # Tick so any in-flight cache.put completes (or fails to even start).
    page.wait_for_timeout(200)

    attempts = _cache_put_attempts(sw)
    post_attempts = [a for a in attempts if a.get("method") != "GET"]
    assert not post_attempts, (
        "SW called Cache.put with a non-GET request — the Cache API rejects "
        "this with TypeError. networkFirst must guard cache.put on "
        f"method=='GET'. Attempts: {post_attempts}"
    )


def test_verify_token_post_not_stored_in_any_cache(
    deploy_clean_page_with_sw, deploy_server
):
    """Defensive belt-and-braces: even if some future code path tries to
    cache a POST, no cache should contain a POST entry."""
    page = deploy_clean_page_with_sw["page"]

    token = _issue_token(deploy_server)
    page.goto(
        f"{deploy_server['base_url']}/#/unlock/{token}", wait_until="load"
    )
    page.wait_for_selector("#install-landing:not(.hidden)", timeout=5000)
    page.wait_for_timeout(200)

    cached_post_count = page.evaluate(
        """async () => {
            const names = await caches.keys();
            let n = 0;
            for (const name of names) {
                const cache = await caches.open(name);
                const reqs = await cache.keys();
                for (const r of reqs) {
                    if (r.url.indexOf('/api/verify-token') !== -1) n += 1;
                }
            }
            return n;
        }"""
    )
    assert cached_post_count == 0, (
        f"POST /api/verify-token must never land in any cache; "
        f"found {cached_post_count} entries"
    )
