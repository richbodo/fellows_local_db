# MCP servers for fellows_local_db

This directory holds MCP (Model Context Protocol) servers that **automate
fellows_local_db**, so an AI client — Claude Desktop, Cursor, an
Ollama-backed local agent — can act on the directory and on your saved
relationships on your behalf.

Flagship demo: ask Claude Desktop *"compose an email to the climate
group in my fellows database, invite them to meet Thursday NZ time at
1pm — don't send, just stage it for review"* and have it find the
group, look up everyone's email, draft the body, and hand you back a
`mailto:` URL that opens in your mail client with the composition
pre-populated. You review and click send.

## What's here

The PNA architecture defines four canonical MCP servers. Three ship
today; Diagnostics is scoped here so you know what's coming.

| Server | Status | What it automates |
|---|---|---|
| **Shared Data Ops** (`shared_data_ops.py`) | v1 — ships now | Read-only access to the **Shared DB** (`fellows.db`). Search, filter, look up fellows, read directory stats. |
| **Private Data Ops** (`private_data_ops.py`) | v1 — ships now | Read-only access to **groups** in the **Private DB** (`relationships.db`). List groups, find by name, fetch members joined to `fellows.db`. Tags/notes deferred — users aren't writing those at scale yet. |
| **Communications** (`comms.py`) | v1 — ships now | Stage outreach as a `mailto:` URL. **Server stages; mail client launches.** No transports fired from inside the MCP process (per AC-MCP-B). |
| **Diagnostics** | not yet built | Read-only access to build label, versions, boot timings, sanitized error events. Useful for AI-assisted bug triage. |

The architectural plan for all four is in `docs/_pna_triage.md` (search
for "four canonical MCP servers" and `AC-MCP-A` / `AC-MCP-B`).

## Privacy boundary in one paragraph

The app distinguishes **Shared data** (the fellows directory — name,
bio, region, contact email, mobile number) from **Private data**
(your groups, tags, notes — never on any server, never shared).
**Shared Data Ops returns Shared data.** **Private Data Ops returns
Private data.** **Communications returns neither — it operates on
recipients/text you (or the AI) hand it.** All three are read-only or
stage-only — no MCP tool in this directory writes to the Private DB
or fires a transport. Any MCP client you wire up will see the same
fellow records and the same groups you can see by opening the app.

Important — Cloud LLMs touching Private data: see *Cloud LLM caveat*
below. The short version is **wire these up to a local model** when
possible.

## Prerequisites

- `fellows.db` built locally (`just db-rebuild` from the repo root, or
  `python build/restore_from_knack_scrapefile.py`).
- `relationships.db` — automatically created on first dev-server boot,
  but for the demo to be interesting you want **fresh data from your
  installed PWA**: open the app → Settings → *Download a backup* →
  save the file as `app/relationships.db` (overwrite any existing
  one). The dev-server's on-disk DB diverges from your PWA's OPFS DB
  over time; the backup is the bridge.
- Python 3.10+.

## Install (one venv covers all three servers)

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

## Wire up Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS). Easiest path: open Claude Desktop → Settings → Developer →
*Edit Config*, which opens this same file. Create the file if it
doesn't exist; if it does already exist (Claude Desktop writes
`preferences` here in normal use), add the `mcpServers` block at the
top level alongside whatever's already there — don't nest it inside
`preferences`.

Paste **all three entries together** — same venv, same install
ceremony, three independent stdio servers:

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
    },
    "private-data-ops": {
      "command": "/absolute/path/to/fellows_local_db/mcp_servers/.venv/bin/python",
      "args": [
        "/absolute/path/to/fellows_local_db/mcp_servers/private_data_ops.py",
        "--db",
        "/absolute/path/to/fellows_local_db/app/relationships.db",
        "--fellows-db",
        "/absolute/path/to/fellows_local_db/app/fellows.db"
      ]
    },
    "comms": {
      "command": "/absolute/path/to/fellows_local_db/mcp_servers/.venv/bin/python",
      "args": [
        "/absolute/path/to/fellows_local_db/mcp_servers/comms.py"
      ]
    }
  }
}
```

**Fully quit Claude Desktop** (⌘Q — closing the window isn't enough;
the menu bar entry must disappear) and relaunch. Then:

1. Open Settings → Developer → *Local MCP servers*. All three should
   appear. If the panel still says "No servers added," the config
   didn't parse — most likely a JSON syntax error or `mcpServers` was
   nested under `preferences`.
2. Start a new chat and try sanity prompts:
   - *"How many fellows are in the directory?"* → fires `shared-data-ops` `get_directory_stats`.
   - *"List my groups."* → fires `private-data-ops` `list_groups`.
   - *"Find the climate group."* → fires `private-data-ops` `find_group`.
   - *"Who's in the climate action group?"* → fires `private-data-ops` `get_group_members`, which joins to `fellows.db` for names + emails in one round-trip.
   - **Flagship**: *"Compose an email to the climate action group inviting them to meet Thursday NZ time at 1pm. Don't send — stage it."* → fires all three servers in turn (find_group → get_group_members → stage_email).

First-run UX: Claude Desktop prompts for approval the first time the
model invokes each tool, and the model may try a couple of generic
approaches before reaching for the MCP tool. That's normal — approve
the tool call and re-ask once it's allowed. Subsequent calls don't
re-prompt.

To verify a tool actually fired (vs. the model answering from
training), tail `~/Library/Logs/Claude/mcp*.log` — each invocation
writes a JSON-RPC frame. The clearest A/B test is to disable a
server in Settings → Developer, ask the same question, and compare
the answer.

### Run a server standalone (without an MCP client)

```bash
just shared-data-ops      # against app/fellows.db
just private-data-ops     # against app/relationships.db + app/fellows.db
just comms                # no DB; pure stdio staging server
```

Each just blocks waiting for JSON-RPC frames on stdin — useful for
piping into a protocol test harness, not for interactive use.

## Cloud LLM caveat (read this if your MCP client is hosted)

The four canonical servers' privacy posture is set by **architectural
commitment AC-MCP-A** (see `docs/_pna_triage.md`): MCP tools that
return *Private DB* rows must require explicit per-call consent when
the consuming AI client is a cloud-hosted LLM (Claude API direct,
OpenAI API, etc.). Local clients (Claude Desktop running a local
model, Cursor + Ollama) are the default green path.

**Private Data Ops returns Private DB rows.** Anytime an MCP client
calls `list_groups`, `find_group`, or `get_group_members`, the
contents of your `relationships.db` (group names, member record_ids,
and joined fellow details) flow to that client. If the client is
hosted (Claude Desktop with the Anthropic-hosted model, ChatGPT
desktop, etc.), the data crosses the network to the provider.

**Shared Data Ops** and **Communications** don't return Private DB
rows, so AC-MCP-A doesn't strictly apply to them — but Shared Data
Ops still exposes fellow contact info, and Communications stages
text the AI client composed (which already saw the underlying data
to compose it). The full data flow matters more than the per-server
posture.

For v1, none of the three servers detects or gates cloud clients.
The MCP transport is stdio-only, which usually means a *local
process* is the client — but a stdio MCP client (Claude Desktop in
its default config) still sends extracted tool output to its
upstream model. Today's position is: **document the boundary,
trust the user's choice**. Wire the servers up to a local model
(Claude Desktop + a locally-served model, Cursor + Ollama) for the
green-path posture. The proper consent UX lands when the spec's
typed contracts land (`docs/pna_toolkit/spec/contracts/mcp-*.schema.json`).

## Per-server configuration

### Shared Data Ops

Path resolution:

1. `--db /path/to/fellows.db` CLI flag.
2. `FELLOWS_DB_PATH` environment variable.
3. `<repo>/app/fellows.db` relative to the script (works in-repo).

DB opened with `mode=ro` — even a buggy tool can't mutate the snapshot.

### Private Data Ops

Path resolution (two DBs, both opened RO):

| Source | Relationships DB | Fellows DB |
|---|---|---|
| CLI flag | `--db` | `--fellows-db` |
| Env var | `FELLOWS_RELATIONSHIPS_DB_PATH` | `FELLOWS_DB_PATH` |
| Default | `<repo>/app/relationships.db` | `<repo>/app/fellows.db` |

Both DBs opened with `mode=ro`. `fellows.db` is `ATTACH`ed as `f` once
per connection so a single SQL query gets group_members + fellow
display fields in one round-trip.

### Communications

No DB, no config beyond `--verbose`. Staged compositions live in
process memory only; nothing on disk. Process restart clears them.

All three servers log to stderr (stdio is reserved for JSON-RPC
frames). Use `--verbose` for noisier output when debugging tool
routing.

## Why a separate venv

`mcp_servers/` is the only Python code in this repo allowed
non-stdlib runtime dependencies. The main app (`app/server.py`,
`deploy/server.py`) is strictly stdlib-only per `CLAUDE.md`. Keeping
the MCP server deps in `mcp_servers/.venv` preserves that boundary —
and one venv covers all three servers.

## Tests

```bash
just test-mcp                 # all three servers
just test-shared-data-ops     # individually
just test-private-data-ops
just test-comms
```

Each runs via `mcp_servers/.venv/bin/pytest`. The same files live in
`tests/`; when run via the project `.venv` (which doesn't have the
`mcp` SDK), they skip cleanly.
