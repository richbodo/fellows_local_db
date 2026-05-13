# PNA Spec

> **Spec-Version:** 0.1 (draft)
> **Status:** Skeleton — substantive content to be migrated from `../_pna_triage.md` per the triage doc's Next Steps.
>
> This document is the universal specification for personal network applications. Reference designs (e.g. `fellows_local_db`) declare conformance to a specific spec version and to a specific flavor (constellation of axis picks).
>
> When the `personal_network_toolkit` repo is created, this file moves there. fellows-specific content lives in `../Architecture.md`.

---

## Vocabulary

The spec uses a small, deliberate set of terms. Worked examples below cite `fellows_local_db` as the first reference design — its concrete choices live in [`../Architecture.md`](../Architecture.md).

- **Personal network application (PNA).** A PNA is an application that helps a user view contact data and work on relationship data over it as a firewalled data layer with higher security needs than the contact data. The PNA runs local-only, never as SaaS. It bridges SaaS data (which should never contain private relationship data) into a much more functional, customizable work environment suitable for viewing personal networks, updating private data about them, and interacting with them.

  fellows_local_db is one PNA reference design — making a directory archive useful and fast. Another PNA reference design would be an app that aggregates personal contact data ingested from the big SaaS providers and lets the user operate privately on that data, adding privacy-sensitive notes, searching, and launching tasks from the app. PNAs bridge the old world of SaaS and offer private, custom tools to operate on contact data.

- **Workspace.** One *component* of a PNA: the viewer + editor. The thing the user looks at and clicks. fellows_local_db's workspace is a vanilla-JS SPA in the browser; another PNA's might be a native shell, a Tauri app, a TUI, or a separately-distributed mini-app sharing the same data layer.

- **Shared data.** In the context of a PNA, shared data is data that exists in more than one place — typically, a copy held by an external system the user uses (Google Contacts, Apple Contacts, Facebook friends, a fellowship's directory, a school's roster). The user is OK with that external system continuing to hold it, and often has no say in the matter. *Examples:* name, email, photo, organizational membership. The PNA mirrors this data locally so the user can browse and search it without depending on the external system being reachable.

  > "Shared" is the key word — not "public" in the everyday sense. Shared data can be data that the user publicly shared, or shared with Apple Contacts and exported, and is typically maintained outside the user's systems. The contact data in your Google account isn't *publicly visible*; it just isn't *exclusively yours* — it is shared with Google and any controlling governments or Google partners it is sold to. In all cases, some external system has a copy, or once did.

- **Private data.** Data that exists only on the user's device(s). The user is *not* OK with any external system holding a copy. *Examples:* notes the user keeps about a contact, tags they apply, groups they assemble, communication history. The PNA's central architectural job is to keep this layer protected, durable, and exclusively local. This data must never be sent across insecure channels, and must only be explicitly sent by the user's command in any form.

- **Shared DB / Private DB.** The two databases that a PNA stores. The Shared DB holds shared data (read-only inside the PNA — written only by the Ingestion component). The Private DB holds private data (read-write from the workspace). Further decomposition and isolation of data according to privacy constraints is reasonable but unnecessary for the first PNAs envisioned.

  In fellows_local_db, the shared DB is `fellows.db` and the private DB is `relationships.db`. The spec uses the generic names; specializations may rename for ergonomics, or change database engines for practical reasons, as long as the data stays local.

- **Mirroring.** The act of producing a fresh shared DB from an external source of shared data. A snapshot is created by the Ingestion component. Re-mirrors are atomic from the workspace's view (stage, validate, swap) and never silently orphan private references.

- **Plugin / extension.** Anything that adds a capability to a composed PNA without modifying its core. A memory-assistant view, a calendar overlay, a federated portrait pull, a community-statistics survey tool — all plugins. PNAs themselves will expose MCP server interfaces as well.

- **Reference design / thematic example.** A working, deployed PNA that demonstrates one valid combination of slot-fills against the spec. fellows_local_db is the first reference design — its load-bearing adjectives are *magic-link distributed PWA* (Distribution choice) + *static network DB archive* (Ingestion choice — the directory is mirrored once with opt-in updates, not linked to a live contact manager) + *single shared directory* (Source choice). New reference designs accumulate adjectives as their slot-fills land. AIs adapting a thematic example start from one of these and ask the user which slot-fills to keep, swap, or extend.

- **Use case.** A user-facing class of PNA — "Directory Archive," "Personal Relationship Manager." A use case names what kind of app this is *from the user's perspective*. v0.1 attests two; future versions will add more. Use case is *not* one of the Axes (defined next); it's the parent category that a flavor instantiates. A use case typically suggests default axis picks (Directory Archives gravitate toward web-bundle distribution; PRMs toward never-distributed-single-user) but the axes remain independent — a hypothetical Directory Archive shipped as a Tauri shell + native SQLite is conceivable. Full catalog in [`use_cases.md`](use_cases.md).

- **Axes.** Axes are areas of functionality that need to be defined when building a PNA. Each Axis offers a pre-defined, limited number of choices to the builder — internally we call these the builder's "Axis picks", and they are the first set of decisions that need to be made before building.

  An example of an Axis is the **distribution** axis, which offers the Axis picks `web-bundle-with-magic-link` (fellows_local_db's pick), `never-distributed-single-user` (PRM's likely pick), `web-bundle-open`, `app-store-native`, `sideloaded-native` — the builder picks one.

  v0.1 names seven Axes: composition model, distribution, storage substrate, ingestion shape, workspace shell, comms transport set, MCP-exposure. The full catalog of attested picks per Axis lives in [`axes.md`](axes.md).

- **Axis pick.** One value on one Axis. Written `axis:value` — for instance `storage:opfs-sqlite-wasm`, `distribution:web-bundle-with-magic-link`. The set of attested picks per Axis is enumerated in [`axes.md`](axes.md).

- **Flavor.** The full constellation of axis picks for a specific PNA. fellows_local_db's flavor: `composition:build-time-bundle + distribution:web-bundle-with-magic-link + storage:opfs-sqlite-wasm + ingestion:single-source-static-mirror + workspace-shell:vanilla-js-spa + comms:mailto-only + mcp-exposure:none`. Two PNAs of the same use case can have different flavors (a TUI PRM vs. a Tauri-wrapped GUI PRM share the use case but differ on workspace shell and storage). A flavor + a use case together fully identify a PNA's shape.

- **Composition model.** One of the seven Axes, called out here because its picks shape several other Axes. Two attested in v0.1: `build-time-bundle` (browser PNAs; slots are JS modules; bundler is the seam) and `runtime-shell-pipeline` (CLI PNAs; slots are OS processes; shell pipeline is the seam). A third, `runtime-MCP-RPC`, applies *across* PNAs in the ecosystem composition pattern (see [§ Composition](#composition) below). Browser distribution typically forces build-time-bundle; CLI distribution typically forces runtime-shell-pipeline.

- **MCP server.** A process exposing PNA capabilities as MCP tools (Anthropic's Model Context Protocol — JSON-RPC over stdio or socket). The spec defines four canonical MCP servers per PNA — Data operations (the Storage slot's read/write surface), Ingestion (drive imports + dedup + orphan preview), Communications (with workspace-mediated user consent), and Diagnostics (read-only access to the Debug contract). An AI client (Claude Desktop, Cursor, a local-Ollama-backed agent, etc.) consumes these servers to drive the PNA. MCP servers are the basis of the `runtime-MCP-RPC` composition model: a PNA exposing MCP becomes externally composable so an AI agent can wire multiple PNAs together at runtime even though each is its own bundle.

- **Universal AC vs flavor-derived AC.** Universal ACs derive from goals alone and apply to every PNA. Flavor-derived ACs are triggered by specific axis picks (e.g., `[storage:opfs-sqlite-wasm]`) and apply only when the flavor matches. [§ Universal architectural commitments](#universal-architectural-commitments) lists the universal set; flavor-derived ACs live in [`axes.md`](axes.md), grouped under the axis-pick that triggers them.

---

## Goals

<!-- TODO (step 2): migrate Preamble + Goals 1-5 from _pna_triage.md § Goals. -->

---

## Use cases

A use case names a coherent class of PNA from the user's perspective. A use case typically suggests default axis picks but does not determine them.

See [`use_cases.md`](use_cases.md) for the attested use case catalog.

---

## Axes

A PNA's *flavor* is the full constellation of axis picks the builder makes. v0.1 names seven Axes: composition model, distribution, storage substrate, ingestion shape, workspace shell, comms transport set, MCP-exposure.

See [`axes.md`](axes.md) for the attested picks per Axis and the flavor-derived ACs each pick triggers.

---

## Composition

<!-- TODO (step 2): migrate from _pna_triage.md § Composition. Three attested compositional models: build-time-bundle, runtime-shell-pipeline, runtime-MCP-RPC. -->

---

## Universal architectural commitments

<!-- TODO (step 2): migrate the Universal ACs table from _pna_triage.md § Architectural commitments § Universal ACs. Flavor-derived ACs live in axes.md, grouped under the axis-pick that triggers them. -->

---

## Slot map

<!-- TODO (step 2): migrate from _pna_triage.md § Slot map. -->

---

## Scope and versioning

<!-- TODO (step 2): migrate from _pna_triage.md § Scope and versioning. -->

See [`CHANGELOG.md`](CHANGELOG.md) for the version history.
