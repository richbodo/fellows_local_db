# PNA Spec Changelog

## v0.1 (draft — in progress)

Initial release of the PNA Spec. Establishes:

- Vocabulary (Use case, Axis, Axis pick, Flavor, Composition model, MCP server, Universal vs flavor-derived AC).
- Goals (1-5: private data sovereignty, mirror centralized sources locally, secure communication options, portable/durable/recoverable user data, locally diagnosable).
- Use cases attested: Directory Archive (realized in fellows_local_db), Personal Relationship Manager [draft], Multi-PNA ecosystem [target v0.2+].
- Seven Axes: composition model, distribution, storage substrate, ingestion shape, workspace shell, comms transport set, MCP-exposure.
- Three attested compositional models: build-time-bundle (intra-bundle, browser), runtime-shell-pipeline (intra-PNA, CLI), runtime-MCP-RPC (inter-PNA, AI-orchestrated).
- Universal ACs: AC-1, AC-4, AC-6, AC-7, AC-9, AC-10, AC-11, AC-15, AC-16, AC-17, AC-18, AC-19, AC-PRM-A, AC-PRM-D, AC-MCP-A, AC-MCP-B (16 in v0.1).
- Flavor-derived ACs: AC-2, AC-3, AC-5, AC-8, AC-12, AC-13, AC-14 from the original set; AC-PRM-B and AC-PRM-C as [draft] PRM-flavor commitments.
- Slot map: three interfaces (Shared schema, Private schema, Debug contract) + five components (Ingestion, Storage, Workspace, Communications, Distribution).
- Four canonical MCP server contracts: Data operations, Ingestion, Communications, Diagnostics.

Working draft is in `docs/_pna_triage.md`. Substantive content migrates into this directory across the steps listed in that doc's Next Steps section, after which the triage doc is retired.

Items deliberately deferred to future versions: privacy reclassification migration mechanics, multi-source dedup migration (beyond AC-PRM-B's draft form), per-database transport requirements, cross-device sync, federated p2p, formal verification.
