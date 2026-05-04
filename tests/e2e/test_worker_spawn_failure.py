"""E2E for worker-spawn / worker-init failure handling.

If vendor/sqlite-worker.js fails to load (404, network error) or its
init throws, the page must surface the unsupported-browser panel for
relationships features. The directory-only browse path can still work
via the API+IDB fallback.

We force the failure with page.route — fulfilling the worker request
with a 404 so `new Worker('/vendor/sqlite-worker.js')` either fails to
construct or fails the init handshake.
"""
from __future__ import annotations

from playwright.sync_api import expect


def test_worker_404_falls_back_to_api_provider(standalone_page, base_url_fixture):
    """Worker bundle unavailable → API+IDB fallback. The directory still
    renders (data comes from /api/fellows + IDB), but the Settings page
    shows the local-data-unavailable panel."""
    page = standalone_page
    # Intercept the worker fetch and 404 it before the page can spawn it.
    page.route("**/vendor/sqlite-worker.js", lambda r: r.fulfill(status=404))
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    page.locator("#loading").wait_for(state="hidden", timeout=15000)

    # Provider should be the api+idb fallback, not the worker.
    kind = page.evaluate(
        "() => (window.__dataProvider && window.__dataProvider.kind) || null"
    )
    assert kind == "api+idb", f"expected api+idb fallback, got {kind!r}"

    # Directory should still render — directory data comes from the
    # API in the fallback, with IDB as a third-tier offline cache.
    expect(page.locator("#app-wrap")).to_be_visible(timeout=5000)

    # Settings page must surface the unsupported-browser panel for
    # backup/restore (groups + settings live in OPFS post-cutover).
    # The api+idb fallback replaces the whole #detail with the panel
    # (showUnsupportedAndDisable in app.js); the worker mode would
    # render the export section in-place. Either way, the panel is
    # present — that's the shipped invariant.
    page.goto(base_url_fixture + "/#/settings", wait_until="domcontentloaded")
    page.locator("#loading").wait_for(state="hidden", timeout=10000)
    panel = page.locator("#detail .local-data-unavailable")
    expect(panel).to_have_count(1, timeout=5000)
    headline = panel.locator("h3").inner_text()
    assert "settings" in headline.lower(), headline
