"""E2E: kind=boot beacon fires once per successful cold boot.

Phase B of install-version telemetry (plans/install_version_telemetry.md).
This is the operator-visible signal `just installed-versions` will join
against to answer "what build is each installed PWA currently running?".

The privacy boundary is server-side
(deploy/client_error_sanitizer.py — tested in
tests/test_client_error_sanitizer.py). What this test pins is the
client-side firing contract: one POST per page load, after
`bootMark('get_list_done')`, with the running build_label in the
`build` field. Without this test a refactor of `bootDirectoryAsApp`
could silently stop firing the beacon and the maintainer wouldn't
notice until `just installed-versions` started returning stale data.
"""
from playwright.sync_api import expect

from conftest import _STANDALONE_DISPLAY_INIT


def _boot_as_app(context):
    """Page that boots straight into directory mode.

    Two preconditions reproduced from tests/e2e/test_offline_only_mode.py:
      * matchMedia('(display-mode: standalone)') returns matches=true so
        the boot path enters `bootDirectoryAsApp` rather than the gate.
      * fellows_authenticated_once='1' so the URL-just-works marker is
        set even when we don't go through the magic-link flow (the dev
        server returns authEnabled=false; that's the existing dev
        passthrough used by the rest of the e2e suite).
    """
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    page.add_init_script(
        "window.localStorage.setItem('fellows_authenticated_once', '1');"
    )
    return page


def test_boot_beacon_fires_once_after_get_list_done(context, base_url_fixture):
    """Cold boot triggers exactly one /api/client-errors POST with
    kind=boot. The payload carries the running build label (top-level
    `build`), displayMode, and UA — the three fields `just
    installed-versions` reads. lastSubmitHashPrefix is absent here
    because we didn't go through the magic-link gate (the dev server
    has no real gate); production boots that did will include it."""
    page = _boot_as_app(context)
    try:
        boot_posts = []
        page.on(
            "request",
            lambda r: (
                boot_posts.append(r)
                if (
                    "/api/client-errors" in r.url
                    and r.method == "POST"
                    and (r.post_data or "").find('"kind":"boot"') >= 0
                )
                else None
            ),
        )
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        # Wait for the directory to render — that confirms
        # bootMark('get_list_done') ran, which is the firing point.
        expect(page.locator("#directory-list")).to_be_visible(timeout=15000)
        # Give the keepalive fetch a tick to be observed by the request
        # listener (fire-and-forget doesn't block render).
        page.wait_for_timeout(300)

        assert len(boot_posts) >= 1, (
            "expected at least one kind=boot POST after directory render; "
            "got zero — reportBootEvent did not fire"
        )
        # Cardinality: bootBeaconFired guard means exactly one even if
        # the boot path re-enters or the SW retries.
        assert len(boot_posts) == 1, (
            f"expected exactly one kind=boot POST, got {len(boot_posts)} — "
            "the fire-once guard regressed"
        )

        body = boot_posts[0].post_data_json
        assert body["events"][0]["kind"] == "boot"
        assert body["events"][0]["msg"] == "cold_start"
        # Build label is what the operator reads — it MUST be in the
        # payload, not just in `extra`.
        assert isinstance(body.get("build"), str) and body["build"], (
            f"build label missing from boot payload: {body}"
        )
        assert body["displayMode"] == "standalone"
        # Provider kind threaded through `extra` is what tells us
        # whether this boot used the worker vs api+idb fallback.
        assert "provider=" in body["events"][0].get("extra", "")
    finally:
        page.close()
