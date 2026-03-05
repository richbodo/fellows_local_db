"""
Shared fixtures for e2e tests: base URL. Server is started once per session by tests/conftest.py app_server.
Ensure port 8765 is free before running (stop the app server if needed, or use scripts/ensure_port_8765_free.sh).
"""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from app.server import PORT


@pytest.fixture(scope="session", autouse=True)
def _e2e_server(app_server):
    """Ensure app server is running for e2e tests (uses session app_server from tests/conftest.py)."""
    return app_server


def base_url():
    return f"http://127.0.0.1:{PORT}"
