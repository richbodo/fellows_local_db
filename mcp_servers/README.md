# MCP servers for fellows_local_db

This directory holds MCP (Model Context Protocol) servers that **automate
fellows_local_db**, so an AI client — Claude Desktop, Cursor, an
Ollama-backed local agent — can act on the directory and on your saved
relationships on your behalf.

Concretely: ask Claude *"who in my fellowship works on climate in
Auckland?"* and get a grounded answer drawn from real records. Or, when
the other servers ship, *"draft a follow-up email to my Brisbane
meetup group"* and have Claude stage the outreach for you to confirm.

## What's here

The PNA architecture defines four canonical MCP servers, each
automating a different part of the app. Only Shared Data Ops ships
today; the other three are scoped here so you know what's coming.

| Server | Status | What it automates |
|---|---|---|
| **Shared Data Ops** (`shared_data_ops.py`) | v1 — ships now | Read-only access to the **Shared DB** (`fellows.db`). Search, filter, look up fellows, read directory stats. |
| **Private Data Ops** | not yet built | Access to the **Private DB** (`relationships.db`): your groups, tags, notes, settings. Reads + writes. Requires a workspace bridge because the Private DB lives in OPFS, owned by the browser tab. |
| **Communications** | not yet built | Drafts outreach (mailto, exports, etc.) and *stages* it. The MCP server never actually sends — the workspace launches transports only after you confirm. |
| **Diagnostics** | not yet built | Read-only access to build label, versions, boot timings, sanitized error events. Useful for AI-assisted bug triage. |

The architectural plan for all four is in `docs/_pna_triage.md` (search
for "four canonical MCP servers" and `AC-MCP-A` / `AC-MCP-B`).

## Privacy boundary in one paragraph

The app distinguishes **Shared data** (the fellows directory — name,
bio, region, contact email, mobile number) from **Private data**
(your groups, tags, notes — never on any server, never shared).
**Shared Data Ops returns Shared data.** It does not touch your
Private data; that's the future Private Data Ops server, which will
carry stronger consent gates (see *Cloud LLM caveat* below). Within
those bounds, any MCP client you wire up will see the same fellow
records you can see by opening the app.

## Shared Data Ops — install and run

### Prerequisites

- `fellows.db` built locally (`just db-rebuild` from the repo root, or
  `python build/restore_from_knack_scrapefile.py`).
- Python 3.10+.

### Install

From the repo root:

```bash
just mcp-install-deps
```

That creates `mcp_servers/.venv/` and installs the `mcp` Python SDK from
`mcp_servers/requirements.txt`. Manual equivalent:

```bash
python3 -m venv mcp_servers/.venv
mcp_servers/.venv/bin/pip install -r mcp_servers/requirements.txt
```

### Wire up Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS). Easiest path: open Claude Desktop → Settings → Developer →
*Edit Config*, which opens this same file. Create the file if it
doesn't exist; if it does already exist (Claude Desktop writes
`preferences` here in normal use), add the `mcpServers` block at the
top level alongside whatever's already there — don't nest it inside
`preferences`.

```json
{
  "mcpServers": {
    "shared-data-ops": {
      "command": "/absolute/path/to/fellows_local_db/mcp_servers/.venv/bin/python",
      "args": [
        "/absolute/path/to/fellows_local_db/mcp_servers/shared_data_ops.py",
        "--db",
        "/absolute/path/to/fellows_local_db/app/fellows.db"
      ]
    }
  }
}
```

**Fully quit Claude Desktop** (⌘Q — closing the window isn't enough;
the menu bar entry must disappear) and relaunch. Then:

1. Open Settings → Developer → *Local MCP servers*. `shared-data-ops`
   should appear there. If the panel still says "No servers added,"
   the config didn't parse — most likely a JSON syntax error or
   `mcpServers` was nested under `preferences`.
2. Start a new chat and try a sanity prompt:
   - *"How many fellows are in the directory?"* → fires `get_directory_stats`.
   - *"Find fellows working on climate."* → fires `search_fellows`.
   - *"Who is `<known name>`?"* → fires `get_fellow`.
   - *"List NZ Investor fellows."* → fires `list_fellows` with a `fellow_type` filter.

First-run UX: Claude Desktop prompts for approval the first time the
model invokes each tool, and the model may try a couple of generic
approaches before reaching for the MCP tool. That's normal — approve
the tool call and re-ask once it's allowed. Subsequent calls don't
re-prompt.

To verify a tool actually fired (vs. the model answering from
training), tail `~/Library/Logs/Claude/mcp*.log` — each invocation
writes a JSON-RPC frame. The clearest A/B test is to disable the
server in Settings → Developer, ask the same question, and compare
the answer.

### Run it standalone (without an MCP client)

```bash
just shared-data-ops
```

That runs `mcp_servers/shared_data_ops.py` against `app/fellows.db` over
stdio. On its own this just waits for JSON-RPC frames on stdin — useful
for piping into a protocol test harness, not for interactive use.

## Cloud LLM caveat

The four canonical servers' privacy posture is set by **architectural
commitment AC-MCP-A** (see `docs/_pna_triage.md`): MCP tools that
return *Private DB* rows must require explicit per-call consent when
the consuming AI client is a cloud-hosted LLM (Claude API direct,
OpenAI API, etc.). Local clients (Claude Desktop running a local
model, Cursor + Ollama) are the default green path.

**Shared Data Ops does not return Private DB rows, so AC-MCP-A doesn't
strictly apply.** But the practical concern remains: if you wire this
server up to a cloud-hosted AI client, fellow contact data (emails,
mobile numbers, bios) crosses the network to that provider when you
run queries. The data is data you already have access to as a fellow,
but you'd be choosing to disclose it to a third party.

For v1 the server does not detect or gate cloud clients. The MCP
transport is stdio-only, which usually means a local process is the
client — but Claude Desktop's stdio MCP server can still send
extracted text to Anthropic's API for the model to consume. Today's
position is: **document the boundary, trust the user's choice**,
revisit if the future Private Data Ops server lands. There's an open
issue tracking the proper consent UX once it's needed
(see `docs/_pna_triage.md` § AC-MCP-A and the issue tracker).

## Configuration

`shared_data_ops.py` resolves the DB path in this order:

1. `--db /path/to/fellows.db` CLI flag.
2. `FELLOWS_DB_PATH` environment variable.
3. `<repo>/app/fellows.db` relative to the script (works in-repo).

The DB is always opened with SQLite's `mode=ro` URI flag — even a
buggy tool can't mutate the snapshot.

Logs go to stderr (stdio is reserved for JSON-RPC frames). Use
`--verbose` for noisier output when debugging tool routing.

## Why a separate venv

`mcp_servers/` is the only Python code in this repo allowed
non-stdlib runtime dependencies. The main app (`app/server.py`,
`deploy/server.py`) is strictly stdlib-only per `CLAUDE.md`. Keeping
the MCP server's deps in `mcp_servers/.venv` preserves that
boundary.

## Tests

```bash
just test-shared-data-ops
```

Runs `tests/test_shared_data_ops.py` against the live `fellows.db`
using `mcp_servers/.venv/bin/pytest`. The same file lives in
`tests/`; when run via the project `.venv` (which doesn't have the
`mcp` SDK), it skips cleanly.
