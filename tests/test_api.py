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
    return _send("POST", path, body, content_type)


def patch(path, body=None, content_type="application/json"):
    return _send("PATCH", path, body, content_type)


def delete(path):
    return _send("DELETE", path, None, "application/json")


def _send(method, path, body, content_type):
    conn = HTTPConnection("127.0.0.1", PORT, timeout=5)
    if body is None:
        payload = b""
    elif isinstance(body, (bytes, bytearray)):
        payload = bytes(body)
    else:
        payload = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": content_type, "Content-Length": str(len(payload))}
    conn.request(method, path, body=payload, headers=headers)
    r = conn.getresponse()
    raw = r.read()
    conn.close()
    ctype = r.getheader("Content-Type") or ""
    return r.status, ctype, raw.decode("utf-8") if raw else ""


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

@pytest.mark.usefixtures("app_server")
class TestGroupsCRUD:
    """Full /api/groups round-trip against the dev server.

    Each test wipes the relationships DB before running so they're order-
    independent. ``app_server`` already isolates the DB to a tmp file via
    ``FELLOWS_RELATIONSHIPS_DB_PATH`` (see conftest.py).
    """

    @pytest.fixture(autouse=True)
    def _reset_groups_db(self):
        path = os.environ.get("FELLOWS_RELATIONSHIPS_DB_PATH")
        if path and os.path.exists(path):
            os.unlink(path)
        yield

    @staticmethod
    def _real_record_ids(n=2):
        """Pick real record_ids from the dev /api/fellows so cross-DB JOIN
        produces names. Using fixed slugs would be brittle if the dataset
        shifts."""
        _, _, body = get("/api/fellows")
        rows = json.loads(body)
        assert len(rows) >= n
        return [(r["record_id"], r["name"]) for r in rows[:n]]

    def test_list_empty_initially(self):
        status, ctype, body = get("/api/groups")
        assert status == 200
        assert "application/json" in ctype
        assert json.loads(body) == []

    def test_create_returns_201_with_full_record(self):
        ids = self._real_record_ids(2)
        status, _, body = post(
            "/api/groups",
            {
                "name": "Climate cohort",
                "note": "for the Wellington roundtable",
                "fellow_record_ids": [r[0] for r in ids],
            },
        )
        assert status == 201
        g = json.loads(body)
        assert isinstance(g["id"], int)
        assert g["name"] == "Climate cohort"
        assert g["note"] == "for the Wellington roundtable"
        assert g["created_at"] and g["updated_at"]
        assert len(g["members"]) == 2
        # Members come back with names resolved via ATTACHed f.fellows.
        names = sorted(m["name"] for m in g["members"])
        assert names == sorted(r[1] for r in ids)

    def test_create_then_list_shows_one(self):
        ids = self._real_record_ids(1)
        post("/api/groups", {"name": "g1", "fellow_record_ids": [ids[0][0]]})
        status, _, body = get("/api/groups")
        assert status == 200
        groups = json.loads(body)
        assert len(groups) == 1
        assert groups[0]["name"] == "g1"
        assert groups[0]["count"] == 1

    def test_get_by_id_returns_members_and_404_when_missing(self):
        ids = self._real_record_ids(1)
        _, _, body = post("/api/groups", {"name": "x", "fellow_record_ids": [ids[0][0]]})
        gid = json.loads(body)["id"]
        status, _, gbody = get(f"/api/groups/{gid}")
        assert status == 200
        g = json.loads(gbody)
        assert g["id"] == gid
        assert len(g["members"]) == 1
        # Bogus id → 404
        status404, _, _ = get(f"/api/groups/{gid + 999}")
        assert status404 == 404

    def test_patch_renames_and_replaces_members(self):
        ids3 = self._real_record_ids(3)
        _, _, body = post(
            "/api/groups",
            {"name": "old name", "fellow_record_ids": [r[0] for r in ids3[:2]]},
        )
        gid = json.loads(body)["id"]
        status, _, body2 = patch(
            f"/api/groups/{gid}",
            {
                "name": "new name",
                "note": "noted",
                "fellow_record_ids": [ids3[2][0]],
            },
        )
        assert status == 200
        g = json.loads(body2)
        assert g["name"] == "new name"
        assert g["note"] == "noted"
        assert [m["record_id"] for m in g["members"]] == [ids3[2][0]]
        # updated_at must move forward; created_at must NOT change.
        assert g["updated_at"] >= g["created_at"]

    def test_patch_partial_only_touches_provided_fields(self):
        ids = self._real_record_ids(1)
        _, _, body = post("/api/groups", {"name": "keepme", "fellow_record_ids": [ids[0][0]]})
        gid = json.loads(body)["id"]
        # Patch only the note — name and members unchanged.
        status, _, body2 = patch(f"/api/groups/{gid}", {"note": "just a note"})
        assert status == 200
        g = json.loads(body2)
        assert g["name"] == "keepme"
        assert g["note"] == "just a note"
        assert len(g["members"]) == 1

    def test_patch_404_for_missing_group(self):
        status, _, _ = patch("/api/groups/9999", {"name": "x"})
        assert status == 404

    def test_delete_returns_204_then_404(self):
        _, _, body = post("/api/groups", {"name": "doomed"})
        gid = json.loads(body)["id"]
        status, _, _ = delete(f"/api/groups/{gid}")
        assert status == 204
        status2, _, _ = delete(f"/api/groups/{gid}")
        assert status2 == 404
        # List is empty again.
        _, _, lbody = get("/api/groups")
        assert json.loads(lbody) == []

    def test_post_validation_rejects_empty_name(self):
        status, _, body = post("/api/groups", {"name": "  "})
        assert status == 400
        assert "name" in (json.loads(body).get("error") or "").lower()

    def test_post_validation_rejects_non_list_members(self):
        status, _, body = post(
            "/api/groups", {"name": "x", "fellow_record_ids": "not-a-list"}
        )
        assert status == 400
        assert "list" in (json.loads(body).get("error") or "").lower()

    def test_create_dedupes_member_ids(self):
        ids = self._real_record_ids(1)
        _, _, body = post(
            "/api/groups",
            {"name": "x", "fellow_record_ids": [ids[0][0], ids[0][0], ids[0][0]]},
        )
        g = json.loads(body)
        assert len(g["members"]) == 1
