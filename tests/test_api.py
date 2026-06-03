"""API tests: HTTP endpoints served by app.server.

The dev server's /api/groups and /api/settings handlers were retired in
Phase 1 of plans/local_first_worker_architecture.md — relationships data
lives in the worker-owned OPFS-stored relationships.db. The matching
TestGroupsCRUD and TestSettingsAPI test classes moved to
tests/e2e/test_worker_rpc.py, which drives the same code path the real
app uses (window.__dataProvider RPC into vendor/sqlite-worker.js).
"""
import json
import os
import sys
from http.client import HTTPConnection
from urllib.parse import quote

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from app.server import PORT


# --- CSP / Permissions-Policy parsing (for the egress-wall assertions) ------
# The CSP `connect-src 'self'` is the wall between an XSS and full OPFS
# exfiltration (see app/server.py:Handler.end_headers). The private-data
# capability gate is a DURABILITY control, not a confidentiality boundary
# (plans/private_data_capability_gate.md), so on-device confidentiality
# actually lives here — pin it exactly so any widening is a deliberate,
# reviewed change rather than an accident.
_EXPECTED_CSP_DIRECTIVES = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "'wasm-unsafe-eval'"],
    "worker-src": ["'self'"],
    "connect-src": ["'self'"],
    "img-src": ["'self'", "data:"],
    "style-src": ["'self'"],
    "font-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "frame-ancestors": ["'none'"],
}


def _parse_csp(csp):
    """Parse a CSP header into {directive: [values...]} (order-tolerant)."""
    out = {}
    for part in csp.split(";"):
        toks = part.split()
        if toks:
            out[toks[0]] = toks[1:]
    return out


def _parse_permissions_policy(pp):
    """Return the set of features locked to `()` in a Permissions-Policy."""
    locked = set()
    for part in pp.split(","):
        part = part.strip()
        if "=" in part:
            feat, val = part.split("=", 1)
            if val.strip() == "()":
                locked.add(feat.strip())
    return locked


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


def get_headers(path):
    """Return (status, {header: value}) for a GET, lowercasing header names."""
    conn = HTTPConnection("127.0.0.1", PORT, timeout=5)
    conn.request("GET", path)
    r = conn.getresponse()
    r.read()
    headers = {k.lower(): v for k, v in r.getheaders()}
    conn.close()
    return r.status, headers


@pytest.mark.usefixtures("app_server")
class TestSecurityHeaders:
    """Verifies the cross-origin isolation + CSP headers the app depends on.

    AC-13 (COOP/COEP required) and the strict-CSP commitment: OPFS-SAH-Pool
    gates SharedArrayBuffer/Atomics on crossOriginIsolated, so COOP/COEP must
    be present on every response; the CSP is the XSS-exfil backstop. These are
    set in app/server.py:Handler.end_headers and mirrored in deploy/server.py.
    This test makes the AC test-backed rather than code-only, so a refactor
    that drops a header fails loudly.
    """

    def test_coop_coep_present(self):
        status, h = get_headers("/")
        assert status == 200
        assert h.get("cross-origin-opener-policy") == "same-origin"
        assert h.get("cross-origin-embedder-policy") == "require-corp"

    def test_strict_csp_present(self):
        _, h = get_headers("/")
        csp = h.get("content-security-policy", "")
        assert "default-src 'self'" in csp
        assert "script-src 'self' 'wasm-unsafe-eval'" in csp
        assert "object-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_other_hardening_headers_present(self):
        _, h = get_headers("/")
        assert h.get("cross-origin-resource-policy") == "same-origin"
        assert h.get("x-content-type-options") == "nosniff"
        assert h.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_csp_directives_exact_and_egress_locked(self):
        """Pin the full CSP and assert the egress wall specifically.

        The exact-directive pin fails loudly on ANY drift (added/renamed/
        widened directive). The sharpened assertions below restate the
        load-bearing properties independently, so they survive a benign
        reorder but still catch the dangerous changes: an external
        connect-src target (exfil path) or an 'unsafe-inline' /
        'unsafe-eval' relaxation (XSS execution path).
        """
        _, h = get_headers("/")
        parsed = _parse_csp(h.get("content-security-policy", ""))
        assert parsed == _EXPECTED_CSP_DIRECTIVES, (
            "CSP drifted from the pinned policy — this is the OPFS-exfil "
            "wall. If you widened it on purpose, update "
            "_EXPECTED_CSP_DIRECTIVES and justify it in review.\n"
            f"expected={_EXPECTED_CSP_DIRECTIVES}\nactual={parsed}"
        )
        # Egress: nothing but same-origin may be a connect target.
        assert parsed.get("connect-src") == ["'self'"], (
            "connect-src must be exactly 'self' — any external target is an "
            "XSS exfiltration path for the OPFS-resident DBs"
        )
        # Execution: no inline/eval script (only the wasm carve-out).
        script_src = parsed.get("script-src", [])
        assert "'unsafe-inline'" not in script_src, "script-src must not allow 'unsafe-inline'"
        assert "'unsafe-eval'" not in script_src, (
            "script-src must not allow 'unsafe-eval' (only 'wasm-unsafe-eval')"
        )
        # No external/wildcard origin anywhere in the policy.
        for name, vals in parsed.items():
            for v in vals:
                assert not v.startswith(
                    ("http://", "https://", "ws://", "wss://", "//", "*")
                ), f"external/wildcard origin {v!r} in directive {name!r}"

    def test_permissions_policy_locks_sensitive_features(self):
        """Powerful device APIs the app never uses must be disabled, so an
        XSS that lands has less leverage. Set in app/server.py and mirrored
        in deploy/server.py."""
        _, h = get_headers("/")
        pp = h.get("permissions-policy", "")
        assert pp, "Permissions-Policy header is missing"
        locked = _parse_permissions_policy(pp)
        for feat in (
            "geolocation", "camera", "microphone", "payment", "usb",
            "bluetooth", "serial", "midi", "accelerometer", "gyroscope",
            "magnetometer",
        ):
            assert feat in locked, f"{feat!r} must be locked to () in Permissions-Policy"


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

    def test_api_search_first_name_richard(self):
        """Whole-token first-name search hits both Richards."""
        status, _, body = get("/api/search", query={"q": "Richard"})
        assert status == 200
        names = [f.get("name") for f in json.loads(body)]
        assert "Richard Bodo" in names
        assert "Richard Graves" in names

    def test_api_search_last_name_bodo(self):
        """Whole-token last-name search hits Richard Bodo."""
        status, _, body = get("/api/search", query={"q": "Bodo"})
        assert status == 200
        names = [f.get("name") for f in json.loads(body)]
        assert "Richard Bodo" in names

    def test_api_search_partial_token_returns_empty(self):
        """As-you-type 'Ric' / 'Bod' return [] under raw FTS5 MATCH.

        Documents the real-time-search regression: the client sends the
        in-progress input straight to fellows_fts MATCH, which requires
        whole tokens. Until the client appends '*' for prefix matching,
        every keystroke before a complete token shows 'no results'.
        Pair with test_fts5_partial_token_without_prefix_glob_returns_nothing
        in tests/test_database.py.
        """
        for partial in ("Ric", "Bod"):
            status, _, body = get("/api/search", query={"q": partial})
            assert status == 200, f"q={partial!r}"
            assert json.loads(body) == [], f"q={partial!r}"

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

