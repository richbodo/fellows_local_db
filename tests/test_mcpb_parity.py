"""Dual-codebase parity tests for MCP servers.

Per ``plans/easy_mcp_install.md`` § 6 (dual-codebase governance): the
Python servers in ``mcp_servers/`` and the TypeScript servers compiled
under ``mcpb/node/dist/`` implement the **same** MCP surface for
**different** audiences (Python source for power users / AI audit; Node
bundles for end-user Claude Desktop install). The risk that makes that
arrangement dangerous is silent behavioral drift — a bug fix lands in
one implementation but not the other, or a privacy boundary tightens
in one but not the other.

This test is the structural backstop. For each tool defined in the PNA
spec contracts, we send a fixed input through both implementations'
stdio JSON-RPC surface and assert structurally-equal output (modulo
intentionally-variable fields like ``staging_id`` in
``comms.stage_email``).

When tests fail, the right reaction is to either reconcile the
divergence or — if the divergence is intentional — explicitly document
which implementation is the new source of truth and update the other.
Do not disable a test to ship faster. (If the test ever catches a
privacy-boundary drift, that's exactly what it's for.)

Tests are seeded incrementally as servers are ported. v1 covers
``comms.stage_email`` and ``comms.get_staged``; ``shared_data_ops`` and
``private_data_ops`` cases land in their respective port PRs.

Run via:

    just test-mcpb-parity

Skip cleanly when the Node bundle isn't built yet (e.g. on a fresh
checkout that hasn't run ``just build-mcpb``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_VENV_PYTHON = REPO_ROOT / "mcp_servers" / ".venv" / "bin" / "python"
NODE_COMMS_JS = REPO_ROOT / "mcpb" / "node" / "dist" / "comms" / "index.js"
PY_COMMS = REPO_ROOT / "mcp_servers" / "comms.py"


def _have_python_server() -> bool:
    return PY_VENV_PYTHON.is_file() and PY_COMMS.is_file()


def _have_node_server() -> bool:
    return NODE_COMMS_JS.is_file()


needs_both = pytest.mark.skipif(
    not (_have_python_server() and _have_node_server()),
    reason=(
        "Parity test needs both implementations available. "
        "Run `just mcp-install-deps` and `just build-mcpb comms` first."
    ),
)


def _call_tool(cmd: list[str], tool_name: str, arguments: dict) -> dict:
    """Spawn an MCP server, send the init handshake, call one tool, return the
    parsed JSON payload from the tool's text content. Raises on protocol
    error or non-zero exit.
    """
    frames = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "parity-test", "version": "0.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
    ]
    stdin = "\n".join(json.dumps(f) for f in frames) + "\n"
    proc = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"{cmd[0]} exited {proc.returncode}\nstderr:\n{proc.stderr}"
        )
    # Parse each response line; pick the one with id=2 (the tool call).
    response = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("id") == 2:
            response = obj
            break
    if response is None:
        raise AssertionError(
            f"no tools/call response from {cmd[0]}\nstdout:\n{proc.stdout}"
        )
    result = response.get("result")
    if not result:
        raise AssertionError(
            f"tools/call returned no result: {response}"
        )
    content = result.get("content", [])
    if not content or content[0].get("type") != "text":
        raise AssertionError(f"unexpected content shape: {content}")
    # Tool returns a JSON-encoded payload as text. Parse it so the parity
    # comparison doesn't trip on indent/whitespace differences between
    # Python's json.dumps(indent=2) (via fastmcp) and Node's compact
    # JSON.stringify.
    return json.loads(content[0]["text"])


def _call_both(tool_name: str, arguments: dict) -> tuple[dict, dict]:
    py = _call_tool(
        [str(PY_VENV_PYTHON), str(PY_COMMS)],
        tool_name,
        arguments,
    )
    node = _call_tool(
        ["node", str(NODE_COMMS_JS)],
        tool_name,
        arguments,
    )
    return py, node


def _scrub_volatile(payload: dict) -> dict:
    """Replace fields that are intentionally not stable across runs (random
    ids) with a sentinel so the structural comparison still asserts that
    both implementations PRODUCED such a field, just not its specific value.
    """
    out = dict(payload)
    if "staging_id" in out:
        assert isinstance(out["staging_id"], str) and out["staging_id"], (
            f"staging_id should be a non-empty string, got {out['staging_id']!r}"
        )
        # Both implementations produce 16-char URL-safe-base64 ids per
        # mcp_servers/comms.py:_new_staging_id and the Node port. Asserting
        # length here catches accidental divergence on id width.
        assert len(out["staging_id"]) == 16, (
            f"staging_id should be 16 chars, got {len(out['staging_id'])}: {out['staging_id']!r}"
        )
        out["staging_id"] = "<scrubbed>"
    return out


@needs_both
class TestCommsStageEmail:
    """``stage_email`` is the load-bearing tool — any drift here either
    breaks the flagship demo or, worse, lets the addresses-visible warning
    fire in one implementation and not the other, which would be a real
    privacy-UX regression.
    """

    def test_bcc_group_send_dedupes_case_insensitively(self):
        args = {
            "subject": "Hi there!",
            "body": "Hello\nworld — & stuff",
            "to": ["someone@example.com"],
            "bcc": ["a@example.com", "B@example.com", "a@example.com"],
        }
        py, node = _call_both("stage_email", args)
        assert _scrub_volatile(py) == _scrub_volatile(node)

    def test_empty_recipients_warning(self):
        args = {"subject": "Empty test", "body": "no one"}
        py, node = _call_both("stage_email", args)
        assert _scrub_volatile(py) == _scrub_volatile(node)
        # And confirm the warning IS present (both sides).
        assert any("No recipients" in w for w in py["warnings"])
        assert any("No recipients" in w for w in node["warnings"])

    def test_addresses_visible_nudge_fires_for_multi_to(self):
        args = {
            "subject": "Group",
            "body": "Hi",
            "to": ["a@example.com", "b@example.com"],
        }
        py, node = _call_both("stage_email", args)
        assert _scrub_volatile(py) == _scrub_volatile(node)
        assert any("`bcc`" in w for w in py["warnings"])
        assert any("`bcc`" in w for w in node["warnings"])

    def test_long_url_warning_fires(self):
        # A body big enough to push the mailto: URL past 2000 bytes.
        big_body = "x" * 2500
        args = {"subject": "Big", "body": big_body, "to": ["a@example.com"]}
        py, node = _call_both("stage_email", args)
        assert _scrub_volatile(py) == _scrub_volatile(node)
        assert any("2000 bytes" in w for w in py["warnings"])
        assert any("2000 bytes" in w for w in node["warnings"])

    def test_mailto_url_is_byte_identical(self):
        """The mailto: URL itself is the load-bearing output — it's what the
        user's mail client opens. Byte-identical URL = byte-identical mail
        composition across implementations.
        """
        args = {
            "subject": "Hi there!",
            "body": "Hello\nworld — & stuff",
            "to": ["someone@example.com"],
            "bcc": ["a@example.com", "B@example.com"],
        }
        py, node = _call_both("stage_email", args)
        assert py["mailto_url"] == node["mailto_url"], (
            f"mailto encoding diverged.\n  py:   {py['mailto_url']}\n  node: {node['mailto_url']}"
        )
        assert py["preview"]["url_byte_length"] == node["preview"]["url_byte_length"]
