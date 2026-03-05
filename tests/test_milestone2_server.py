"""
Milestone 2 tests: Python server and API.
Server is started once per session by tests/conftest.py app_server fixture.
"""
import json
import os
import sys
from http.client import HTTPConnection
from urllib.parse import quote

import pytest

# Repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from app.server import PORT


def get(path, query=None):
    path_with_query = path
    if query:
        path_with_query = path + "?" + "&".join(f"{k}={quote(str(v))}" for k, v in query.items())
    conn = HTTPConnection("127.0.0.1", PORT, timeout=5)
    conn.request("GET", path_with_query)
    r = conn.getresponse()
    body = r.read().decode("utf-8")
    conn.close()
    return r.status, r.getheader("Content-Type") or "", body


@pytest.mark.usefixtures("app_server")
class TestMilestone2Server:
    """Run with server already started by session-scoped app_server fixture."""

    def test_get_root_returns_html(self):
        status, ctype, body = get("/")
        assert status == 200
        assert "text/html" in ctype
        assert "EHF Fellows" in body or "Directory" in body

    def test_api_fellows_full_returns_442(self):
        status, ctype, body = get("/api/fellows", query={"full": "1"})
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert isinstance(data, list)
        assert len(data) == 442
        first = data[0]
        assert "slug" in first
        assert "name" in first
        assert "record_id" in first

    def test_api_fellows_list_only_returns_minimal(self):
        """Without full=1, returns minimal list (record_id, slug, name) for instant directory."""
        status, ctype, body = get("/api/fellows")
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert isinstance(data, list)
        assert len(data) == 442
        first = data[0]
        assert set(first.keys()) <= {"record_id", "slug", "name"}
        assert "slug" in first and "name" in first

    def test_api_fellow_by_slug_aaron_bird(self):
        status, ctype, body = get("/api/fellows/aaron_bird")
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert data.get("name") == "Aaron Bird"
        assert data.get("slug") == "aaron_bird"

    def test_api_search_aaron_returns_results(self):
        status, ctype, body = get("/api/search", query={"q": "Aaron"})
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert isinstance(data, list)
        assert len(data) >= 1
        names = [f.get("name") for f in data]
        assert "Aaron Bird" in names or "Aaron McDonald" in names

    def test_images_slug_returns_200_or_404(self):
        # If images dir exists and has aaron_bird.jpg -> 200, else 404
        status, ctype, body = get("/images/aaron_bird.jpg")
        assert status in (200, 404)
        if status == 200:
            assert "image/" in ctype

    def test_static_app_js_returns_js(self):
        status, ctype, body = get("/app.js")
        assert status == 200
        assert "javascript" in ctype or "application/javascript" in ctype
