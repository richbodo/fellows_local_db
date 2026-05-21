# Architectural Decisions Log

A log of decisions where an architectural constraint shaped an
implementation choice in a way that's worth remembering. Most
implementation choices live fine inside the code itself or a PR
description; this file is for the smaller set where:

- An architectural commitment (a PNA-spec AC, a `CLAUDE.md` rule, or
  a section of `docs/Architecture.md`) was the deciding factor,
- The constraint isn't visible at the point where the choice shows
  up in code, so a future contributor seeing only the artifact would
  reasonably make a different call,
- And the alternative would have been the natural default without
  the constraint.

Entries are append-only — superseded decisions stay, with a forward
link to the newer entry. Newest first.

---

## 2026-05-21 — `.mcpb` bundles do not ship native Node dependencies

**Why this is worth recording.** A future contributor adding the
`private-data-ops` port (or any new server in `mcpb/node/`) will be
tempted to reach for `better-sqlite3` (or `sharp`, or any other
N-API/native module). The existing Python `mcp_servers/` uses the
stdlib `sqlite3` module — there's no parallel "obvious" choice for
Node, and the better-sqlite3 ergonomics are excellent. The constraint
that forbids it isn't visible from the source side; it shows up only
when the bundle is installed in Claude Desktop and fails to load.

**Context.** Found during smoke test of #187. The first
`shared-data-ops.mcpb` build used `better-sqlite3`. It built cleanly,
passed all parity tests on the host, and the `.mcpb` validated. But
on install in Claude Desktop, the server process crashed 64ms after
the `initialize` message arrived — before the SDK could even respond.
Claude Desktop logged *"Server transport closed unexpectedly"*.

Direct reproduction (against the installed bundle):

```
$ node -e 'new (require("better-sqlite3"))("./fellows.db")'
Error: Could not locate the bindings file. Tried:
 → .../better-sqlite3/build/Release/better_sqlite3.node
 → ... [13 more paths]
```

The native `.node` binary wasn't in the bundle. Two compounding
reasons:

1. **`build/build_mcpb.py` ran `npm install --ignore-scripts`** so
   better-sqlite3's `install` hook (which downloads/compiles the
   native binding via `prebuild-install`) never ran.
2. **Even with that flag removed, the prebuilt would have been wrong:**
   the host machine runs Node 25 (modules ABI v141); Claude Desktop's
   Electron 41.6.1 bundles Node 24.15.0 (modules ABI v137).
   `prebuild-install` matches against the host's ABI, so a host-built
   bundle would have shipped a v141 binary that Claude Desktop's v137
   runtime couldn't load.

**Alternatives considered.**

1. **Remove `--ignore-scripts` and accept the ABI mismatch.**
   Doesn't actually work — the host-built binary would crash in
   Claude Desktop with a different error.

2. **Cross-build the binary against Claude Desktop's Node ABI.**
   Requires pinning a specific Node version in CI, running
   `prebuild-install --target=24.15.0`. Fragile to Electron's Node
   version changes (every Electron release updates the bundled Node
   version eventually). High maintenance cost.

3. **Use Node's built-in `node:sqlite` module.** Stable since
   Node 24.0. Zero native dependencies — it's compiled into Node
   itself, so it's *guaranteed* to work whatever Node version
   Claude Desktop bundles. **Chosen.**

**Decision.** `.mcpb` bundles do not ship native Node dependencies.
For SQLite specifically, `node:sqlite` is the path. For anything
else that would normally call for a native module (image processing,
crypto-with-fast-paths, etc.), the bundle either uses Node's
built-ins, falls back to a pure-JS implementation, or doesn't ship
that capability.

**Consequences.**

- Pro: zero ABI surface area between the bundle and Claude Desktop's
  Node runtime. Survives any Electron version change.
- Pro: smaller bundles — `shared_data_ops.mcpb` dropped from 6.7 MB
  to 3.8 MB after the better-sqlite3 removal.
- Pro: build pipeline can keep `--ignore-scripts` as a defense-in-depth
  measure against postinstall script supply-chain attacks.
- Con: gives up some performance-sensitive native libraries. Not
  relevant for our current surface; revisit if a future tool needs
  one (and address as a per-tool exception rather than a blanket
  policy change).

**Links.**

- Fix commit on `feat/mcpb-shared-data-ops`: `2807bba`
- [`plans/easy_mcp_install.md`](../plans/easy_mcp_install.md) — the parent plan
- [`mcpb/node/src/_shared/fellows_queries.ts`](../mcpb/node/src/_shared/fellows_queries.ts) — the actual `node:sqlite` import comment

---

## 2026-05-21 — MCP servers ship as three separate `.mcpb` files, not one consolidated bundle

**Why this is worth recording.** A future contributor looking at
`mcpb/node/` and seeing three nearly-identical bundles with the same
build pipeline would reasonably consolidate them into one — that's
strictly better from a UX standpoint (one install dialog instead of
three) and the `.mcpb` manifest format gives no hint that anything
forbids it. The constraint that forbids it lives a layer up, in the
PNA spec's `mcp-exposure:shared+private+comms` axis pick and
AC-MCP-A's exception clause. Without this entry, the connection is
invisible at the point of change.

**Context.** Planning easy MCP installation for non-tech Mac users
via Claude Desktop's `.mcpb` (Desktop Extensions) format. See
[`plans/easy_mcp_install.md`](../plans/easy_mcp_install.md). The
PNA spec axis pick for this repo is
`mcp-exposure:shared+private+comms` — three servers explicitly.
AC-MCP-A requires explicit per-call consent for Private DB rows
flowing to cloud-hosted LLMs. `docs/Architecture.md` § *MCP-related
ACs activated by `mcp-exposure:shared+private+comms`* names the
three-server split as the satisfying mechanism — specifically:

> *"The Shared / Private split at the MCP surface lets a user wire
> a cloud client to Shared Data Ops alone without triggering this
> AC."*

The user's ability to opt into the safer subset depends on the
three servers being **independently enableable**. Claude Desktop's
Extensions UI toggles whole `.mcpb` extensions, not individual
servers inside an extension, and not individual tools inside a
server. So the three-bundle split is what carries the architectural
mechanism through to the install layer.

**Alternatives considered.**

1. **One consolidated `.mcpb` exposing all nine tools from one
   server.** Simplest UX — one install dialog, one toggle, one
   config row. **Rejected**: collapses the user's ability to enable
   Shared without enabling Private, erasing AC-MCP-A's exception
   clause at the install layer.

2. **One `.mcpb` with three internal MCP servers sharing a
   process.** The MCP spec allows multiple servers in one process,
   but Claude Desktop's Extensions UI toggles whole extensions, not
   internal servers. **Rejected**: same UX-vs-architecture loss as
   option 1.

3. **Three separate `.mcpb` files, each independently installable
   and toggleable.** Three install dialogs. **Chosen.**

**Decision.** Option 3 — three separate `.mcpb` files
(`fellows-shared-data-ops.mcpb`, `fellows-private-data-ops.mcpb`,
`fellows-comms.mcpb`).

**Consequences.**

- Pro: AC-MCP-A's exception clause survives intact at the install
  layer; users keep a structural way to choose Shared-only.
- Pro: Aligns with the `mcp-exposure:shared+private+comms` axis
  pick. No re-attestation required.
- Pro: Per-server enable/disable inside Claude Desktop's Extensions
  panel, which mirrors the privacy boundary the PWA already
  documents.
- Con: Three install dialogs instead of one. Real UX cost.
- Mitigation: The PWA Settings UI ("Set up Claude Desktop
  integration") sequences the three downloads behind a single
  button click and shows a **preamble dialog** that names what each
  bundle exposes (Shared = directory data; Private = your groups;
  Comms = email staging) and what the privacy implications are. The
  preamble *is* the AC-MCP-A surfacing for the install moment — it
  gives the user a single informed choice point even though the
  install dialogs themselves are separate.

**Links.**

- [`plans/easy_mcp_install.md`](../plans/easy_mcp_install.md) — full plan
- [`docs/Architecture.md`](./Architecture.md) — AC-MCP-A and the axis pick
- [`mcp_servers/README.md`](../mcp_servers/README.md) — Cloud LLM caveat (the existing AC-MCP-A surfacing for the Python servers)
- [PNA Spec § Universal architectural commitments](https://github.com/richbodo/personal_network_toolkit/blob/main/PNA_Spec.md#universal-architectural-commitments)
- [PNA axes § mcp-exposure](https://github.com/richbodo/personal_network_toolkit/blob/main/axes.md#mcp-exposure)
