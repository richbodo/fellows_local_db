# PNA Spec Changelog

## v0.1 (draft — in progress)

Initial release of the PNA Spec. Establishes:

- Vocabulary (Use case, Axis, Axis pick, Flavor, Composition model, MCP server, Universal vs flavor-derived AC).
- Goals (1-5: private data sovereignty, mirror centralized sources locally, secure communication options, portable/durable/recoverable user data, locally diagnosable).
- Use cases attested: Directory Archive (realized in fellows_local_db), Personal Relationship Manager [draft], Multi-PNA ecosystem [target v0.2+].
- Six Axes: distribution, storage substrate, ingestion shape, workspace shell, comms transport set, MCP-exposure.
- Two target environments for a single PNA (Browser PNAs and CLI / native PNAs) plus one runtime cooperation pattern across PNAs (the ecosystem reference design, mediated by canonical MCP servers).
- Universal ACs: AC-1, AC-4, AC-6, AC-7, AC-9, AC-10, AC-11, AC-15, AC-16, AC-17, AC-18, AC-19, AC-PRM-A, AC-PRM-D, AC-MCP-A, AC-MCP-B (16 in v0.1).
- Flavor-derived ACs: AC-2, AC-3, AC-5, AC-8, AC-12, AC-13, AC-14 from the original set; AC-PRM-B and AC-PRM-C as [draft] PRM-flavor commitments.
- Slot map: five slots (Ingestion, Storage, Workspace, Communications, Distribution) + three interfaces (Shared schema, Private schema, Debug contract).
- Sub-contract decomposition: each slot and interface decomposes into named sub-contracts under a per-slot two-letter prefix — `WS-` (10), `ST-` (11), `IN-` (4), `CO-` (6), `DI-` (6), `SH-` (6), `PR-` (5), `DB-` (9). 57 sub-contracts total in v0.1. Cross-slot threads (build-label discipline, opt-in directory update, restore data flow, capability-failure surfacing, …) are formalized in the same section. The spec is now self-contained: builders can cite sub-contracts by ID without consulting the working triage.
- Five canonical MCP server contracts: Shared Data Ops, Private Data Ops, Ingestion, Communications, Diagnostics. The original "Data operations" server was split along the Shared / Private privacy boundary so AC-MCP-A's cloud-client consent rule targets exactly the Private Data Ops surface — a user can wire a cloud client to Shared Data Ops alone without crossing the boundary. v1 reference implementations of Shared Data Ops, Private Data Ops, and Comms ship in `fellows_local_db/mcp_servers/`; spec/contracts JSON Schemas live alongside this CHANGELOG in `spec/contracts/mcp-shared-data-ops.schema.json`, `mcp-private-data-ops.schema.json`, and `mcp-comms.schema.json`. Ingestion and Diagnostics remain spec stubs (no reference implementation yet).
- MCP-exposure axis picks restructured from {`none`, `data-ops-only`, `data-ops+comms`, `full`} to {`none`, `shared-only`, `shared+private`, `shared+private+comms`, `full`} to reflect the split; fellows_local_db's attested pick is `shared+private+comms`.

Working draft is in `docs/_pna_triage.md`. Substantive content has now migrated into this directory across the steps listed in that doc's Next Steps section (sub-contract decomposition was the last spec-side step); the triage doc retires once the remaining repo-side annex demotion lands.

Items deliberately deferred to future versions: privacy reclassification migration mechanics, multi-source dedup migration (beyond AC-PRM-B's draft form), per-database transport requirements, cross-device sync, federated p2p, formal verification.
