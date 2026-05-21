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
