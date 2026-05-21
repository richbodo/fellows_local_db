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

PY_PRIVATE = REPO_ROOT / "mcp_servers" / "private_data_ops.py"
NODE_PRIVATE_JS = REPO_ROOT / "mcpb" / "node" / "dist" / "private_data_ops" / "index.js"
REL_DB = REPO_ROOT / "app" / "relationships.db"

# Staged-bundle paths — these point at the layout build_mcpb.py
# produces inside mcpb/node/.staging/. Running the parity test against
# the staged layout (with no env vars or extra args) is what would have
# caught the path bugs from #187 (missing _shared/ + missing data/
# resolution under the bundle root). Per plans/easy_mcp_install.md
# § 13 polish-checklist.
STAGED_SHARED_JS = (
    REPO_ROOT / "mcpb" / "node" / ".staging" / "shared_data_ops" / "server" / "index.js"
)
STAGED_PRIVATE_JS = (
    REPO_ROOT / "mcpb" / "node" / ".staging" / "private_data_ops" / "server" / "index.js"
)


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


needs_both_private = pytest.mark.skipif(
    not (
        _have_python(PY_PRIVATE)
        and _have_node(NODE_PRIVATE_JS)
        and FELLOWS_DB.is_file()
        and REL_DB.is_file()
    ),
    reason=(
        "private-data-ops parity needs both implementations + fellows.db + "
        "relationships.db. Run `just mcp-install-deps`, "
        "`just build-mcpb private_data_ops`, `just db-rebuild`, and ensure "
        "app/relationships.db exists (open the PWA at least once)."
    ),
)


needs_staged_shared = pytest.mark.skipif(
    not STAGED_SHARED_JS.is_file(),
    reason="staged shared_data_ops layout needs `just build-mcpb shared_data_ops`.",
)


needs_staged_private = pytest.mark.skipif(
    not (STAGED_PRIVATE_JS.is_file() and REL_DB.is_file()),
    reason=(
        "staged private_data_ops layout needs `just build-mcpb private_data_ops` "
        "and app/relationships.db."
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


def _call_both_private(tool_name: str, arguments: dict) -> tuple[dict, dict]:
    """private-data-ops parity helper. Both servers run against the same
    relationships.db (RW for the user, but both implementations open it
    RO) with the same fellows.db ATTACHed."""
    py = _call_tool(
        [
            str(PY_VENV_PYTHON),
            str(PY_PRIVATE),
            "--db",
            str(REL_DB),
            "--fellows-db",
            str(FELLOWS_DB),
        ],
        tool_name,
        arguments,
    )
    node = _call_tool(
        [
            "node",
            str(NODE_PRIVATE_JS),
            "--db",
            str(REL_DB),
            "--fellows-db",
            str(FELLOWS_DB),
        ],
        tool_name,
        arguments,
    )
    return py, node


@needs_both_private
class TestPrivateDataOps:
    """``private-data-ops`` returns Private DB rows + joins to the Shared
    DB. Divergence here is more sensitive than shared-data-ops: it would
    mean Claude shows different group contents depending on which
    implementation runs, and the cross-DB ATTACH join is where SQL
    semantics most easily drift between Python's sqlite3 and Node's
    node:sqlite.
    """

    def test_list_groups_total_and_first_few(self):
        """The total count + the first few groups (ordered by
        updated_at DESC, id DESC). Both implementations should agree
        on row counts and ordering.
        """
        py, node = _call_both_private("list_groups", {"limit": 50})
        assert py == node, (
            "list_groups divergence: "
            f"py.total={py.get('total')} node.total={node.get('total')}; "
            f"first names: py={[g.get('name') for g in py.get('results', [])[:3]]} "
            f"node={[g.get('name') for g in node.get('results', [])[:3]]}"
        )

    def test_find_group_case_insensitive_substring(self):
        """Python uses ``LIKE ? COLLATE NOCASE`` and so does the Node
        port. Pick a substring that's likely to match at least one
        group in any well-developed relationships.db.
        """
        py, node = _call_both_private("find_group", {"name": "a"})
        assert py == node

    def test_find_group_empty_query_returns_zero(self):
        py, node = _call_both_private("find_group", {"name": "   "})
        assert py == node
        assert py["total"] == 0

    def test_find_group_no_match(self):
        py, node = _call_both_private(
            "find_group", {"name": "zzz-no-such-group-xyz"}
        )
        assert py == node
        assert py["total"] == 0

    def test_get_group_members_first_existing_group(self):
        """Pick the first group from list_groups and pull its members.
        Exercises the load-bearing cross-DB ATTACH join: fellow names +
        emails come from f.fellows. The COALESCE(name, record_id) sort
        order is where Python and Node's sqlite ATTACH semantics could
        diverge on locale collation; ensure they match exactly.
        """
        listing = _call_both_private("list_groups", {"limit": 1})
        py_list, node_list = listing
        # Pre-check the listing matches; otherwise this test is testing
        # the wrong group on each side.
        assert py_list == node_list
        if not py_list.get("results"):
            pytest.skip("relationships.db has no groups; can't test members")
        gid = py_list["results"][0]["group_id"]
        py, node = _call_both_private(
            "get_group_members", {"group_id": gid}
        )
        assert py == node, (
            f"member-join divergence on group_id={gid}: "
            f"py member count={len((py or {}).get('members', []))} "
            f"node member count={len((node or {}).get('members', []))}"
        )

    def test_get_group_members_missing_returns_null(self):
        # 999999 is highly unlikely to exist as a real group id.
        py, node = _call_both_private(
            "get_group_members", {"group_id": 999999}
        )
        assert py is None
        assert node is None


# ----- Staged-bundle smoke tests ------------------------------------------
#
# Per plans/easy_mcp_install.md § 13: the parity tests above run against
# ``mcpb/node/dist/<name>/index.js`` where ``_shared/`` IS a sibling and
# (for shared-data-ops) ``FELLOWS_DB_PATH`` is set explicitly. That's
# two unrealistic conditions stacked — neither holds inside an installed
# .mcpb. The staged bundle layout (``mcpb/node/.staging/<name>/server/
# index.js`` with ``_shared/`` and ``data/`` as siblings of ``server/``)
# IS what gets packed into the .mcpb. Smoking it without env-var help
# would have caught both #187 bugs (missing better-sqlite3 native binding;
# missing path-resolution under bundle root).


def _staged_call(cmd: list[str], tool_name: str, arguments: dict) -> dict | None:
    """Like _call_tool but no env-var override — we want the staged
    bundle's default path resolution to do its work.
    """
    return _call_tool(cmd, tool_name, arguments)


@needs_staged_shared
def test_staged_shared_bundle_default_resolution():
    """Spawn the staged shared_data_ops bundle with no env vars and no
    --db arg. Its default path resolution should find the bundled
    fellows.db at ``../data/fellows.db`` relative to server/index.js.
    Asserts only that the call returns a sane stats payload — the byte-
    level parity is already covered by TestSharedDataOps.
    """
    result = _staged_call(
        ["node", str(STAGED_SHARED_JS)], "get_directory_stats", {}
    )
    assert result is not None
    assert isinstance(result.get("total"), int)
    assert result["total"] > 0, "bundled fellows.db should have rows"


@needs_staged_private
def test_staged_private_bundle_default_resolution():
    """Spawn the staged private_data_ops bundle, passing relationships.db
    via --db (the .mcpb's user_config does this at install time too),
    but NOT --fellows-db. The bundled fellows.db must be found via
    default path resolution at ``../data/fellows.db``.
    """
    result = _staged_call(
        [
            "node",
            str(STAGED_PRIVATE_JS),
            "--db",
            str(REL_DB),
        ],
        "list_groups",
        {"limit": 1},
    )
    assert result is not None
    assert isinstance(result.get("total"), int)
