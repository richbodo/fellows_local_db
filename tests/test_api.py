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


def post(path, body=None, content_type="application/json"):
    conn = HTTPConnection("127.0.0.1", PORT, timeout=5)
    if body is None:
        payload = b""
    elif isinstance(body, (bytes, bytearray)):
        payload = bytes(body)
    else:
        payload = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": content_type, "Content-Length": str(len(payload))}
    conn.request("POST", path, body=payload, headers=headers)
    r = conn.getresponse()
    raw = r.read()
    conn.close()
    ctype = r.getheader("Content-Type") or ""
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
        assert set(first.keys()) <= {"record_id", "slug", "name", "has_contact_email"}
        assert "slug" in first and "name" in first
        assert "has_contact_email" in first
        assert isinstance(first["has_contact_email"], bool)

    def test_api_fellows_list_has_contact_email_flag_is_consistent(self):
        """has_contact_email in list should match the full record's contact_email presence."""
        _, _, list_body = get("/api/fellows")
        _, _, full_body = get("/api/fellows", query={"full": "1"})
        list_data = json.loads(list_body)
        full_data = json.loads(full_body)
        full_by_id = {f["record_id"]: f for f in full_data}
        mismatches = []
        for entry in list_data:
            full = full_by_id.get(entry["record_id"])
            if not full:
                continue
            has_email_full = bool((full.get("contact_email") or "").strip())
            if entry["has_contact_email"] != has_email_full:
                mismatches.append(entry["record_id"])
        assert not mismatches, f"has_contact_email mismatch for {mismatches[:5]}"

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

    def test_api_auth_status_shape_includes_install_recently_allowed(self):
        """Dev server stub must include installRecentlyAllowed=false so the
        client's decision tree stays on the local-dev passthrough path."""
        status, ctype, body = get("/api/auth/status")
        assert status == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert data.get("authEnabled") is False
        assert data.get("authenticated") is False
        assert "installRecentlyAllowed" in data
        assert data["installRecentlyAllowed"] is False

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

    def test_fellows_db_snapshot(self):
        conn = HTTPConnection("127.0.0.1", PORT, timeout=5)
        conn.request("GET", "/fellows.db")
        r = conn.getresponse()
        raw = r.read()
        conn.close()
        assert r.status == 200
        ctype = r.getheader("Content-Type") or ""
        assert "octet-stream" in ctype
        assert raw[:15] == b"SQLite format 3"
        assert len(raw) > 512

    def test_post_groups_returns_501_until_pr2(self):
        """The right-rail UI POSTs to /api/groups; PR 1 ships only the stub.
        The contract: 501 + JSON body with `error` and `message`. PR 2
        replaces this handler with the real create-group implementation."""
        status, ctype, body = post(
            "/api/groups",
            {"name": "smoke", "note": "", "fellow_record_ids": []},
        )
        assert status == 501
        assert "application/json" in ctype
        data = json.loads(body)
        assert data.get("error") == "Not Implemented"
        assert "PR 2" in (data.get("message") or "")
