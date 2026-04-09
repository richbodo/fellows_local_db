"""API tests: HTTP endpoints served by app.server."""
import json
import os
import sys
from http.client import HTTPConnection
from urllib.parse import quote

import pytest

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
    raw = r.read()
    conn.close()
    ctype = r.getheader("Content-Type") or ""
    if "image/" in ctype:
        return r.status, ctype, raw
    return r.status, ctype, raw.decode("utf-8")


@pytest.mark.usefixtures("app_server")
class TestAPI:
    """API endpoint tests. Server started by session-scoped app_server fixture."""

    def test_root_returns_html(self):
        status, ctype, body = get("/")
        assert status == 200
        assert "text/html" in ctype
        assert "EHF Fellows" in body or "Directory" in body

    def test_api_fellows_full_returns_all(self):
        status, ctype, body = get("/api/fellows", query={"full": "1"})
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert isinstance(data, list)
        assert len(data) >= 1
        first = data[0]
        assert "slug" in first
        assert "name" in first
        assert "record_id" in first

    def test_api_fellows_list_returns_minimal_keys(self):
        status, ctype, body = get("/api/fellows")
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert isinstance(data, list)
        assert len(data) >= 1
        first = data[0]
        assert set(first.keys()) <= {"record_id", "slug", "name"}
        assert "slug" in first and "name" in first

    def test_api_fellows_list_and_full_counts_match(self):
        """List and full endpoints should return the same number of records."""
        _, _, list_body = get("/api/fellows")
        _, _, full_body = get("/api/fellows", query={"full": "1"})
        list_data = json.loads(list_body)
        full_data = json.loads(full_body)
        assert len(list_data) == len(full_data)

    def test_api_fellow_by_slug(self):
        status, ctype, body = get("/api/fellows/aaron_bird")
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert data.get("name") == "Aaron Bird"
        assert data.get("slug") == "aaron_bird"

    def test_api_search_returns_results(self):
        status, ctype, body = get("/api/search", query={"q": "Aaron"})
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert isinstance(data, list)
        assert len(data) >= 1
        names = [f.get("name") for f in data]
        assert "Aaron Bird" in names or "Aaron McDonald" in names

    def test_images_endpoint(self):
        status, ctype, body = get("/images/aaron_bird.jpg")
        assert status in (200, 404)
        if status == 200:
            assert "image/" in ctype

    def test_api_stats_returns_aggregates(self):
        status, ctype, body = get("/api/stats")
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert "total" in data
        assert isinstance(data["total"], int)
        assert data["total"] >= 1
        for key in ("by_fellow_type", "by_cohort", "by_region", "field_completeness"):
            assert key in data
            assert isinstance(data[key], list)
            assert len(data[key]) >= 1
            first = data[key][0]
            assert "label" in first
            assert "count" in first
            assert isinstance(first["count"], int)

    def test_static_js(self):
        status, ctype, body = get("/app.js")
        assert status == 200
        assert "javascript" in ctype or "application/javascript" in ctype
