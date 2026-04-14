"""Shared fixtures for e2e tests."""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from app.server import PORT

# App treats non-standalone browser tabs as install-only (no directory). E2E that
# needs the directory must emulate installed PWA display mode before navigation.
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


@pytest.fixture(scope="session", autouse=True)
def _e2e_server(app_server):
    """Ensure app server is running for e2e tests (uses session app_server from tests/conftest.py)."""
    return app_server


@pytest.fixture(scope="session")
def base_url_fixture():
    """Local dev URL, or ``E2E_BASE_URL`` when set (no trailing slash)."""
    env = (os.environ.get("E2E_BASE_URL") or "").strip().rstrip("/")
    if env:
        return env
    return f"http://127.0.0.1:{PORT}"


@pytest.fixture
def standalone_page(context):
    """Playwright page with PWA standalone display mode faked for directory/detail tests."""
    page = context.new_page()
    page.add_init_script(_STANDALONE_DISPLAY_INIT)
    try:
        yield page
    finally:
        page.close()
