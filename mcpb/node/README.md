# mcpb/node — TypeScript MCP servers, packaged as Desktop Extensions

This directory holds the **TypeScript** implementations of the Fellows
MCP servers, packaged as Anthropic Desktop Extensions (`.mcpb` files)
for one-click install in Claude Desktop. Claude Desktop bundles a
Node.js runtime, so a Node-based `.mcpb` installs with zero user
prerequisites — no Python, no Terminal, no JSON editing.

See [`plans/easy_mcp_install.md`](../../plans/easy_mcp_install.md) for
the plan this directory implements.

## Why two implementations?

`mcp_servers/` (Python) and `mcpb/node/` (TypeScript) implement the
**same MCP surface** for **different audiences**:

| | `mcp_servers/` (Python) | `mcpb/node/` (TS, in `.mcpb`) |
|---|---|---|
| Audience | Rich's own workflows, Cursor + uv power users, AI clients that want programmatic access, audit/test | End-user fellows installing into Claude Desktop |
| Install path | `pip install` + manual `claude_desktop_config.json` edits | Double-click a `.mcpb` file |
| Prerequisites | Python 3.10+, the `mcp` SDK | None (Claude Desktop bundles Node) |
| Dependency on system Python | Yes | No |

Both target the same PNA-spec contracts
(`mcp-shared-data-ops.schema.json`, `mcp-private-data-ops.schema.json`,
`mcp-comms.schema.json`). Behavioral parity is asserted by
`tests/test_mcpb_parity.py` — see
[`plans/easy_mcp_install.md` § 6](../../plans/easy_mcp_install.md)
for the dual-codebase governance.

## Why three bundles?

One `.mcpb` per MCP server: Shared, Private, Comms. Claude Desktop's
Extensions UI toggles whole bundles, so per-server enable/disable
requires per-server bundles. This preserves AC-MCP-A's exception
clause (a user can wire only Shared to a cloud client) at the
install layer. See
[`docs/acdecisionslog.md` § 2026-05-21](../../docs/acdecisionslog.md).

## Layout

```
mcpb/node/
├── src/
│   ├── comms/index.ts          # Stage-only mailto: composer (port of mcp_servers/comms.py)
│   ├── shared_data_ops/        # (planned) port of mcp_servers/shared_data_ops.py
│   ├── private_data_ops/       # (planned) port of mcp_servers/private_data_ops.py
│   └── _shared/                # (planned) shared helpers for SQLite, response shaping
├── manifests/
│   └── comms.json              # Anthropic MCPB manifest for the comms bundle
├── package.json
├── tsconfig.json
└── .gitignore
```

Build artifacts go to `deploy/dist/mcpb/<name>.mcpb`. See
`build/build_mcpb.py` and `just build-mcpb`.

## Building locally

From the repo root:

```bash
just build-mcpb       # builds all currently-implemented bundles
```

That installs node_modules in `mcpb/node/`, compiles TS to JS, and
runs `npx @anthropic-ai/mcpb pack` against each manifest.

## Testing

Behavioral parity with the Python servers is the merge gate:

```bash
just test-mcpb-parity # runs tests/test_mcpb_parity.py
```

The parity test seeds expand as more servers are ported. Don't merge
a change to either `mcp_servers/<name>.py` or `mcpb/node/src/<name>/`
without the parity test green.
