"""E2E for the worker version-skew compatibility gate (L7).

Page declares EXPECTED_WORKER_RPC_VERSION + EXPECTED_RELATIONSHIPS_SCHEMA_VERSION;
worker reports its own values in the init handshake. On mismatch:
- Reads still execute against the worker.
- Mutating ops throw VersionMismatchError.

We induce a skew by intercepting the worker bundle fetch and rewriting
WORKER_RPC_VERSION to a bumped value before serving it. The page sees
the mismatch on init and refuses mutations.

Uses a serviceWorkers='block' context so page.route on the worker
bundle isn't bypassed by the SW's APP_SHELL_ASSETS precache.
"""
from __future__ import annotations

from urllib.parse import urlparse

import pytest

from tests.e2e.conftest import _FOLDER_PICKER_STUB_MIN, attach_verified_folder


def _rewrite_worker_version(route, base_url):
    """Fulfill the worker bundle with WORKER_RPC_VERSION bumped to 99.

    COOP/COEP headers must be on the response, otherwise Chromium
    refuses to spawn the Worker in the page's cross-origin-isolated
    context (the page itself is COOP=same-origin / COEP=require-corp,
    so its children must declare embedder-policy too).
    """
    import urllib.request
    parsed = urlparse(base_url)
    raw = urllib.request.urlopen(
        f"{parsed.scheme}://{parsed.hostname}:{parsed.port}/vendor/sqlite-worker.js"
    ).read().decode("utf-8")
    # Bump the constant. Match the exact line so a copy-paste regression
    # (renaming the constant) trips the test instead of silently passing.
    # The current value is checked dynamically so a future RPC-version
    # bump doesn't require a fixture edit; we only assert the substring.
    import re as _re
    m = _re.search(r"var WORKER_RPC_VERSION = (\d+);", raw)
    assert m, "could not find WORKER_RPC_VERSION assignment in worker bundle"
    target = m.group(0)
    replacement = "var WORKER_RPC_VERSION = 99;"
    rewritten = raw.replace(target, replacement, 1)
    route.fulfill(
        status=200,
        headers={
            "Content-Type": "application/javascript; charset=utf-8",
            "Cross-Origin-Embedder-Policy": "require-corp",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
        body=rewritten,
    )


_STANDALONE_DISPLAY_INIT = """
(function () {
  var orig = window.matchMedia.bind(window);
  window.matchMedia = function (q) {
    q = String(q);
    if (q.indexOf('display-mode: standalone') !== -1) {
      return { matches: true, media: q, addEventListener: function () {}, removeEventListener: function () {} };
    }
    return orig(q);
  };
})();
"""


@pytest.fixture
def no_sw_page(browser):
    """Playwright page in a context that blocks ServiceWorker entirely.

    The SW precaches /vendor/sqlite-worker.js, so a plain page.route on
    the worker URL gets bypassed by the SW's cached copy. Blocking the
    SW at the context level keeps page.route in charge.
    """
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    try:
        yield page
    finally:
        page.close()
        context.close()


def test_version_skew_refuses_mutations_but_allows_reads(
    no_sw_page, base_url_fixture
):
    page = no_sw_page
    # Attach a verified folder BEFORE inducing the skew. createGroup is guarded
    # refuseIfBrowseOnly-first (app.js), so off-folder a skewed mutation throws
    # BrowseOnlyError, masking the version gate this test exists to prove (#260).
    # Attaching goes through setFolderHandle, itself version-gated — so do it on
    # a clean (un-skewed) boot, then route the bumped worker and re-boot. The
    # folder handle persists in IndexedDB across the reboot.
    page.add_init_script(_FOLDER_PICKER_STUB_MIN)
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    page.locator("#loading").wait_for(state="hidden", timeout=15000)
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    attach_verified_folder(page, base_url_fixture)

    # Now induce the skew: serve the worker bundle with WORKER_RPC_VERSION
    # bumped, then re-boot. The page sees the mismatch on init.
    page.route(
        "**/vendor/sqlite-worker.js",
        lambda r: _rewrite_worker_version(r, base_url_fixture),
    )
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    page.locator("#loading").wait_for(state="hidden", timeout=15000)

    # Provider is still the worker (only version constant skewed; init succeeded).
    kind = page.evaluate(
        "() => (window.__dataProvider && window.__dataProvider.kind) || null"
    )
    assert kind == "worker", f"expected worker provider, got {kind!r}"
    version_ok = page.evaluate("() => window.__dataProvider._versionOk")
    assert version_ok is False, "expected _versionOk=false on skew"
    init_blob = page.evaluate("() => window.__dataProvider._init")
    assert init_blob["workerRpcVersion"] == 99, (
        f"worker should report bumped version 99, got {init_blob}"
    )

    # Reads still work — listGroups must not throw on version skew.
    groups = page.evaluate("() => window.__dataProvider.listGroups()")
    assert isinstance(groups, list), f"listGroups should return list, got {groups!r}"

    # Mutations are refused with VersionMismatchError. Capture the thrown
    # error name so the assertion is precise even if the message changes.
    err = page.evaluate(
        """
        async () => {
          try {
            await window.__dataProvider.createGroup({ name: 'should refuse', fellow_record_ids: [] });
            return null;
          } catch (e) {
            return { name: e.name, message: String(e.message || '').slice(0, 200) };
          }
        }
        """
    )
    assert err is not None, (
        "createGroup should have thrown on version skew, but resolved"
    )
    assert err["name"] == "VersionMismatchError", (
        f"expected VersionMismatchError, got {err}"
    )
    assert "rpc=99" in err["message"] or "version skew" in err["message"].lower(), err
