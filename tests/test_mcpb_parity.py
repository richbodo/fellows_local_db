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
FELLOWS_DB = REPO_ROOT / "app" / "fellows.db"

PY_COMMS = REPO_ROOT / "mcp_servers" / "comms.py"
NODE_COMMS_JS = REPO_ROOT / "mcpb" / "node" / "dist" / "comms" / "index.js"

PY_SHARED = REPO_ROOT / "mcp_servers" / "shared_data_ops.py"
NODE_SHARED_JS = REPO_ROOT / "mcpb" / "node" / "dist" / "shared_data_ops" / "index.js"


def _have_python_venv() -> bool:
    return PY_VENV_PYTHON.is_file()


def _have_python(server: Path) -> bool:
    return _have_python_venv() and server.is_file()


def _have_node(server: Path) -> bool:
    return server.is_file()


needs_both_comms = pytest.mark.skipif(
    not (_have_python(PY_COMMS) and _have_node(NODE_COMMS_JS)),
    reason=(
        "comms parity needs both implementations. "
        "Run `just mcp-install-deps` and `just build-mcpb comms` first."
    ),
)


needs_both_shared = pytest.mark.skipif(
    not (
        _have_python(PY_SHARED)
        and _have_node(NODE_SHARED_JS)
        and FELLOWS_DB.is_file()
    ),
    reason=(
        "shared-data-ops parity needs both implementations + fellows.db. "
        "Run `just mcp-install-deps`, `just build-mcpb shared_data_ops`, "
        "and `just db-rebuild`."
    ),
)


def _call_tool(
    cmd: list[str], tool_name: str, arguments: dict, env: dict | None = None,
) -> dict:
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
    import os as _os
    run_env = dict(_os.environ)
    if env:
        run_env.update(env)
    proc = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        env=run_env,
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
    # Tolerant "no result" handling: Python's fastmcp returns an empty
    # content array when a tool returns None; the Node SDK serializes
    # null as content=[{"type":"text","text":"null"}]. Both mean
    # "tool returned nothing" — collapse to a single Python None so
    # parity callers can compare straightforwardly.
    if not content:
        return None
    if content[0].get("type") != "text":
        raise AssertionError(f"unexpected content shape: {content}")
    # Tool returns a JSON-encoded payload as text. Parse it so the parity
    # comparison doesn't trip on indent/whitespace differences between
    # Python's json.dumps(indent=2) (via fastmcp) and Node's compact
    # JSON.stringify.
    return json.loads(content[0]["text"])


def _call_both(tool_name: str, arguments: dict) -> tuple[dict, dict]:
    """Comms-flavored helper: spawns both comms servers and compares."""
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


def _call_both_shared(tool_name: str, arguments: dict) -> tuple[dict, dict]:
    """Shared-data-ops-flavored helper: spawns both shared servers against the
    repo's app/fellows.db. Uses FELLOWS_DB_PATH env so both implementations
    take the same code path for resolving the DB (Node would otherwise default
    to its bundled path inside the .mcpb staging dir).
    """
    env = {"FELLOWS_DB_PATH": str(FELLOWS_DB)}
    py = _call_tool(
        [str(PY_VENV_PYTHON), str(PY_SHARED), "--db", str(FELLOWS_DB)],
        tool_name,
        arguments,
        env=env,
    )
    node = _call_tool(
        ["node", str(NODE_SHARED_JS)],
        tool_name,
        arguments,
        env=env,
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


@needs_both_comms
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


@needs_both_shared
class TestSharedDataOps:
    """``shared-data-ops`` is the load-bearing read surface — divergence here
    means Claude tells fellows different things depending on which
    implementation runs. The full record shape (including extra_json merge)
    + the FTS5 query semantics are the things most likely to drift.
    """

    def test_search_fellows_returns_identical_summaries(self):
        """FTS5 query against the real fellows.db. Both implementations should
        rank, slice, and trim identically.
        """
        py, node = _call_both_shared(
            "search_fellows", {"query": "climate", "limit": 5}
        )
        assert py == node, (
            f"search divergence:\n  py.total={py.get('total')} node.total={node.get('total')}\n"
            f"  py.results[0]={py.get('results',[None])[0]}\n  node.results[0]={node.get('results',[None])[0]}"
        )

    def test_search_fellows_empty_query_returns_zero(self):
        py, node = _call_both_shared("search_fellows", {"query": "   "})
        assert py == node
        assert py["total"] == 0

    def test_get_fellow_by_slug_full_shape(self):
        """A real fellow's slug; assert the full shape matches including the
        extra_json overflow merge. Pick a known-stable slug — the search
        result above gave us ``andy_sack`` as a deterministic entry.
        """
        py, node = _call_both_shared("get_fellow", {"id": "andy_sack"})
        assert py == node, (
            f"get_fellow shape divergence:\n  diff keys:"
            f" py-only={set(py.keys()) - set(node.keys())}"
            f" node-only={set(node.keys()) - set(py.keys())}"
        )

    def test_get_fellow_missing_returns_null(self):
        py, node = _call_both_shared("get_fellow", {"id": "no-such-slug-xyz"})
        assert py is None
        assert node is None

    def test_list_fellows_minimal(self):
        """No filters, small page. Both implementations should return the
        same SummaryFellow ordering (ORDER BY name ASC + same OFFSET/LIMIT).
        """
        py, node = _call_both_shared(
            "list_fellows", {"limit": 10, "offset": 0}
        )
        # Reasonable structural assert; ordering should be deterministic.
        assert py == node, (
            "list_fellows divergence at minimal-filter case."
        )

    def test_list_fellows_with_filters(self):
        """Exercise the WHERE-clause assembly for a multi-filter call."""
        args = {
            "fellow_type": "International Investor",
            "has_contact_email": True,
            "limit": 5,
        }
        py, node = _call_both_shared("list_fellows", args)
        assert py == node, "list_fellows divergence under multi-filter."

    def test_get_directory_stats_aggregates_identical(self):
        """The biggest, most-likely-to-drift surface: 14 column completeness
        counts + 12 extra_json key counts + region splitting + group-by
        aggregates. Byte-identical means the SQL paths in both implementations
        agree on every aggregation rule.
        """
        py, node = _call_both_shared("get_directory_stats", {})
        # `total` should be a single integer — sanity check first.
        assert py["total"] == node["total"]
        # `by_fellow_type`, `by_cohort` should match exactly (Python's
        # ORDER BY COUNT(*) DESC + SQLite's tie behavior = deterministic).
        assert py["by_fellow_type"] == node["by_fellow_type"]
        assert py["by_cohort"] == node["by_cohort"]
        # Region splitting: order may differ on ties because Counter.most_common
        # preserves insertion order whereas JS Map iteration is also
        # insertion-order — should still match, but compare as sorted lists
        # as a safety net.
        py_regions = sorted(py["by_region"], key=lambda r: (-r["count"], r["label"]))
        node_regions = sorted(node["by_region"], key=lambda r: (-r["count"], r["label"]))
        assert py_regions == node_regions
        # `field_completeness` is sorted by count DESC; tie ordering depends
        # on dict-insertion stability. Compare as sorted lists.
        py_fc = sorted(py["field_completeness"], key=lambda r: (-r["count"], r["label"]))
        node_fc = sorted(node["field_completeness"], key=lambda r: (-r["count"], r["label"]))
        assert py_fc == node_fc
