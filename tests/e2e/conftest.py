"""Shared fixtures for e2e tests."""
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


@pytest.fixture(scope="session")
def base_url_fixture():
    return f"http://127.0.0.1:{PORT}"
