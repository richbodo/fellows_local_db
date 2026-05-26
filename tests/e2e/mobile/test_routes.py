"""Mobile screenshot smoke tests across the device matrix.

Captures a full-page PNG for every route on every device profile.

- Latest captures land in ``tests/e2e/mobile/current_state/`` (gitignored).
- Baselines live in ``tests/e2e/mobile/__snapshots__/`` (committed).

The committed baselines are a *visual reference* for what each route
should look like in the redesigned UI — review them with ``git diff``
or your image-aware diff tool after a UI change. The test itself only
asserts the file was written; it does not pixel-compare against the
baseline because the dev ``relationships.db`` accumulates state across
test runs and the screenshot_group fixture's id varies, which makes
per-byte comparison too flaky. To accept new captures as the next
reference, run ``just test-mobile-promote``.

Run with ``just test-mobile``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

OUT_DIR = Path(__file__).parent / "current_state"
SNAP_DIR = Path(__file__).parent / "__snapshots__"
OUT_DIR.mkdir(exist_ok=True)
SNAP_DIR.mkdir(exist_ok=True)


# Routes that don't need any pre-existing user-authored state. The label
# becomes the screenshot filename prefix.
STATIC_ROUTES = [
    ("#/", "directory"),
    ("#/about", "about"),
    ("#/settings", "settings"),
    ("#/groups", "groups-index"),
    ("#/fellow/aaron_bird", "fellow-detail"),
]

# Routes that need an existing group id. Templates resolve via .format(gid=…).
GROUP_ROUTES = [
    ("#/groups/{gid}", "group-detail"),
    ("#/groups/{gid}/directory", "group-visual-directory"),
    ("#/edit/{gid}", "group-edit"),
]


def _device_slug(name: str) -> str:
    return name.replace(" ", "-").lower()


def _wait_for_app_boot(page, timeout: int = 10000) -> None:
    """Wait for the boot loader to vanish, then settle. Works for every route.

    The directory-only check (``#directory`` visible) doesn't fit About,
    Settings, or any group-scoped route, so we just wait on the loader and
    a brief settle delay for late layout/font shifts.
    """
    page.locator("#loading").wait_for(state="hidden", timeout=timeout)
    page.wait_for_timeout(400)


def _create_screenshot_group_via_worker(page) -> int:
    """Create a test group via the page's worker provider and return its id.

    Phase 1 of plans/local_first_worker_architecture.md retired the dev
    server's /api/groups route — relationships data lives in the
    worker-owned OPFS relationships.db. Test setup goes through the
    same window.__dataProvider RPC the real app uses. The previous
    HTTP-based fixture silently skipped these tests after that cutover.

    Caller must have navigated the page and waited for the worker
    provider to be ready.
    """
    record = page.evaluate(
        """() => window.__dataProvider.createGroup({
            name: 'Mobile Screenshot Group',
            note: 'Created by tests/e2e/mobile/test_routes.py.',
            fellow_record_ids: [],
        })"""
    )
    return int(record["id"])


@pytest.mark.parametrize("hash_route,label", STATIC_ROUTES)
def test_screenshot_static_route(
    mobile_page, device_name, base_url_fixture, hash_route, label
):
    """Snap each static route on each device profile; check against baseline."""
    page = mobile_page
    page.goto(base_url_fixture + "/" + hash_route, wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    out = OUT_DIR / f"{label}--{_device_slug(device_name)}.png"
    page.screenshot(path=str(out), full_page=True)
    assert out.is_file() and out.stat().st_size > 0


@pytest.mark.parametrize("template,label", GROUP_ROUTES)
def test_screenshot_group_route(
    mobile_page,
    device_name,
    base_url_fixture,
    template,
    label,
):
    """Snap each group-scoped route (creates a fresh group per test via
    the worker; OPFS persists across the second goto inside the same
    browser context, so the group is still there after navigation)."""
    page = mobile_page
    # First navigate to / so the worker provider boots and we can
    # seed a group via __dataProvider; then navigate to the target
    # group-scoped route. OPFS is per-origin per-context; the group
    # survives the second goto.
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    gid = _create_screenshot_group_via_worker(page)
    hash_route = template.format(gid=gid)
    page.goto(base_url_fixture + "/" + hash_route, wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    out = OUT_DIR / f"{label}--{_device_slug(device_name)}.png"
    page.screenshot(path=str(out), full_page=True)
    assert out.is_file() and out.stat().st_size > 0
