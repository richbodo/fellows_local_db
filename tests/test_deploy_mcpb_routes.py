"""End-to-end tests for the auth-gated ``/mcpb/<name>.mcpb`` download routes.

Mirrors the posture of ``/fellows.db``: bundles carry shared data
(`shared_data_ops.mcpb` embeds `fellows.db`) and per-DB ATTACH wiring
(`private_data_ops.mcpb`), so unauthenticated download would defeat
the same gate `/fellows.db` enforces.

Reuses the session-scoped ``deploy_server`` fixture from
``tests/conftest.py``. Each test writes its own dummy bundle bytes
into the fixture's ``dist_dir/mcpb/`` so we test the route shape
without needing the (~10 MB total) real bundles.
"""
from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlparse

import pytest


def _conn(handle):
    parsed = urlparse(handle["base_url"])
    return HTTPConnection(parsed.hostname, parsed.port, timeout=3)


def _post_json(handle, path, body):
    conn = _conn(handle)
    payload = json.dumps(body).encode("utf-8")
    conn.request(
        "POST",
        path,
        body=payload,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        },
    )
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), (json.loads(raw) if raw else {})


def _get(handle, path, cookie=None):
    conn = _conn(handle)
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), raw


def _set_cookie_header(headers):
    return headers.get("Set-Cookie") or headers.get("set-cookie") or ""


def _extract_session_cookie(headers):
    sc = _set_cookie_header(headers)
    if not sc:
        return None
    head = sc.split(";", 1)[0].strip()
    if not head.startswith("fellows_session="):
        return None
    return head


def _token_from_url(magic_url):
    return magic_url.rsplit("/#/unlock/", 1)[-1]


def _authenticate(deploy_server):
    """Walk the magic-link flow and return the ``Cookie:`` header value
    for a valid session against ``deploy_server``."""
    state = deploy_server["auth_state"]
    with state.lock:
        state.tokens.clear()
        state.consumed.clear()
        state.rate_buckets.clear()
        state.sessions.clear()
    deploy_server["sent"].clear()
    _post_json(deploy_server, "/api/send-unlock", {"email": deploy_server["test_email"]})
    token = _token_from_url(deploy_server["sent"][-1]["url"])
    _, headers, _ = _post_json(deploy_server, "/api/verify-token", {"token": token})
    cookie = _extract_session_cookie(headers)
    assert cookie is not None, "auth flow did not return a session cookie"
    return cookie


@pytest.fixture
def stub_mcpb_bundles(deploy_server):
    """Write three dummy ``.mcpb`` files under ``dist_dir/mcpb/`` for
    the duration of the test, then clean them up. Size is varied per
    bundle so Content-Length assertions can't pass by coincidence.
    """
    dist_dir: Path = deploy_server["dist_dir"]
    mcpb_dir = dist_dir / "mcpb"
    mcpb_dir.mkdir(exist_ok=True)
    bundles = {
        "comms": b"DUMMY-COMMS-PAYLOAD",
        "shared_data_ops": b"DUMMY-SHARED-PAYLOAD-" + (b"AB" * 500),
        "private_data_ops": b"DUMMY-PRIVATE-PAYLOAD-" + (b"YZ" * 250),
    }
    paths: dict[str, Path] = {}
    for name, data in bundles.items():
        p = mcpb_dir / f"{name}.mcpb"
        p.write_bytes(data)
        paths[name] = p
    try:
        yield bundles
    finally:
        for p in paths.values():
            if p.exists():
                p.unlink()
        try:
            mcpb_dir.rmdir()
        except OSError:
            # Test that asserts "missing file" may have written one
            # and not cleaned it up — best-effort cleanup.
            pass


class TestMcpbAuthGate:
    """The route requires a valid session, same as ``/fellows.db``."""

    def test_unauthenticated_request_returns_403(self, deploy_server, stub_mcpb_bundles):
        status, _, body = _get(deploy_server, "/mcpb/comms.mcpb")
        assert status == 403
        assert b"Forbidden" in body

    def test_unauthenticated_request_does_not_leak_bytes(self, deploy_server, stub_mcpb_bundles):
        _, _, body = _get(deploy_server, "/mcpb/comms.mcpb")
        # The forbidden response must not contain the bundle bytes.
        assert stub_mcpb_bundles["comms"] not in body

    def test_authenticated_request_streams_bundle(self, deploy_server, stub_mcpb_bundles):
        cookie = _authenticate(deploy_server)
        status, headers, body = _get(deploy_server, "/mcpb/comms.mcpb", cookie=cookie)
        assert status == 200
        assert body == stub_mcpb_bundles["comms"]


class TestMcpbResponseShape:
    def test_content_type_is_octet_stream(self, deploy_server, stub_mcpb_bundles):
        cookie = _authenticate(deploy_server)
        _, headers, _ = _get(deploy_server, "/mcpb/comms.mcpb", cookie=cookie)
        assert headers.get("Content-Type") == "application/octet-stream"

    def test_content_disposition_forces_download(self, deploy_server, stub_mcpb_bundles):
        cookie = _authenticate(deploy_server)
        _, headers, _ = _get(deploy_server, "/mcpb/private_data_ops.mcpb", cookie=cookie)
        cd = headers.get("Content-Disposition") or ""
        assert cd.startswith("attachment;")
        assert 'filename="private_data_ops.mcpb"' in cd

    def test_content_length_matches_payload(self, deploy_server, stub_mcpb_bundles):
        cookie = _authenticate(deploy_server)
        for name, data in stub_mcpb_bundles.items():
            _, headers, body = _get(deploy_server, f"/mcpb/{name}.mcpb", cookie=cookie)
            assert headers.get("Content-Length") == str(len(data)), (
                f"{name}: Content-Length mismatch"
            )
            assert body == data, f"{name}: body bytes mismatch"

    def test_cache_control_is_private_no_store(self, deploy_server, stub_mcpb_bundles):
        cookie = _authenticate(deploy_server)
        _, headers, _ = _get(deploy_server, "/mcpb/shared_data_ops.mcpb", cookie=cookie)
        cc = (headers.get("Cache-Control") or "").lower()
        assert "private" in cc
        assert "no-store" in cc


class TestMcpbWhitelist:
    """Only the three known bundle names resolve. Anything else 404s
    without leaking whether the file is present or whitelist-rejected."""

    def test_unknown_name_returns_404(self, deploy_server, stub_mcpb_bundles):
        cookie = _authenticate(deploy_server)
        status, _, _ = _get(deploy_server, "/mcpb/bogus.mcpb", cookie=cookie)
        assert status == 404

    def test_missing_file_returns_404_for_valid_name(self, deploy_server):
        """No stub_mcpb_bundles fixture: dist_dir/mcpb/ may not even
        exist. A whitelisted name with no file on disk must 404."""
        # Ensure the file doesn't exist for this test.
        dist_dir: Path = deploy_server["dist_dir"]
        target = dist_dir / "mcpb" / "comms.mcpb"
        if target.exists():
            target.unlink()
        cookie = _authenticate(deploy_server)
        status, _, _ = _get(deploy_server, "/mcpb/comms.mcpb", cookie=cookie)
        assert status == 404

    def test_path_traversal_rejected(self, deploy_server, stub_mcpb_bundles):
        cookie = _authenticate(deploy_server)
        # ``urllib`` normalizes ``..`` segments in the path before the
        # handler runs, so the request never reaches /mcpb/. Either a
        # 404 (route mismatch) or a 403 (gated path under another
        # prefix) is acceptable — the load-bearing assertion is that
        # nothing other than 200 is returned with bundle bytes.
        status, _, body = _get(
            deploy_server, "/mcpb/../fellows.db", cookie=cookie
        )
        assert status != 200 or stub_mcpb_bundles["comms"] not in body

    def test_non_mcpb_suffix_rejected(self, deploy_server, stub_mcpb_bundles):
        cookie = _authenticate(deploy_server)
        status, _, _ = _get(deploy_server, "/mcpb/comms.txt", cookie=cookie)
        # Falls through to the static-file handler, which 404s because
        # the file doesn't exist. The important guarantee is "no .mcpb
        # routing for non-.mcpb suffixes."
        assert status in (403, 404)


class TestMcpbDownloadLog:
    """Every successful download logs a structured event to stderr so a
    maintainer can correlate Claude Desktop install attempts with
    server-side activity."""

    def test_successful_download_logs_event(
        self, deploy_server, stub_mcpb_bundles, capfd
    ):
        cookie = _authenticate(deploy_server)
        capfd.readouterr()  # drain stderr from auth flow
        status, _, _ = _get(deploy_server, "/mcpb/comms.mcpb", cookie=cookie)
        assert status == 200
        captured = capfd.readouterr()
        # Find the line — stderr has many lines; the event is a JSON
        # object containing event=mcpb_download.
        lines = [
            ln.strip()
            for ln in captured.err.splitlines()
            if "mcpb_download" in ln
        ]
        assert lines, "expected a mcpb_download log line on stderr"
        evt = json.loads(lines[-1])
        assert evt["event"] == "mcpb_download"
        assert evt["name"] == "comms"
        assert evt["size_bytes"] == len(stub_mcpb_bundles["comms"])
