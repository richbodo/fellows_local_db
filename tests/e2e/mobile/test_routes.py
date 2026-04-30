"""Mobile screenshot smoke tests across the device matrix.

Captures a full-page PNG for every route on every device profile. Output
lands in ``tests/e2e/mobile/current_state/<route>--<device>.png``. These
are reference captures for the Phase 2 mobile redesign — NOT regression
baselines. Phase 3 will commit baselines to ``__snapshots__/`` after
the redesign lands.

Run with ``just test-mobile``.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

OUT_DIR = Path(__file__).parent / "current_state"
OUT_DIR.mkdir(exist_ok=True)


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


@pytest.fixture(scope="session")
def screenshot_group(base_url_fixture) -> int:
    """Create a single test group via the API; reused across all group routes."""
    body = json.dumps(
        {
            "name": "Mobile Screenshot Group",
            "note": "Created by tests/e2e/mobile/test_routes.py — safe to delete.",
            "fellow_record_ids": [],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base_url_fixture + "/api/groups",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        pytest.skip(f"dev server unreachable for group creation: {exc}")
    return int(payload["id"])


@pytest.mark.parametrize("hash_route,label", STATIC_ROUTES)
def test_screenshot_static_route(
    mobile_page, device_name, base_url_fixture, hash_route, label
):
    """Snap each static route on each device profile; assert PNG was written."""
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
    screenshot_group,
    template,
    label,
):
    """Snap each group-scoped route (uses the session-scoped test group)."""
    page = mobile_page
    hash_route = template.format(gid=screenshot_group)
    page.goto(base_url_fixture + "/" + hash_route, wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    out = OUT_DIR / f"{label}--{_device_slug(device_name)}.png"
    page.screenshot(path=str(out), full_page=True)
    assert out.is_file() and out.stat().st_size > 0
