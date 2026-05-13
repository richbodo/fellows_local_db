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

### Preamble

We are at an inflection point. Two shifts are arriving at the same time. Personal data is withdrawing from centralized systems: users are increasingly unwilling to trust Facebook with who they talk to about politics or mental health. At the same time, edge compute and AI agents capable of running serious work locally are arriving fast. The first shift creates demand for tools that keep user data sovereign; the second makes such tools practical to build, run, and recompose at the user's own pace.

A personal network application is a tool for users to manage and use contact and relationship data that makes up their personal networks. A PNA handles a user's contact data and personal-relationship data with strong, declared contracts about how that data is treated. The PNA separates the concerns of editing data shared with other systems from data created and held locally as private.

v0.1 PNAs all operate downstream of SaaS systems of record — they do not modify contact data, although a contact manager might well exist as a plugin to a PNA, or vice-versa. What distinguishes the niche is the architectural promise: shared data is local-first and replaceable; private data is sovereign and protected; the user can reclassify a record's privacy at any time, and the PNA honors it durably; communication transports are user-chosen to meet the user's privacy and other requirements; the user can reason about where their data lives without trusting a vendor.

Specs are foundational because users will increasingly compose software by prompting AI agents. The Personal Network Toolkit project is an attempt to offer the foundational specs for PNAs, production-ready reference applications, and MCP servers (the composability layer of Software 3.0), to ensure that both the humans and the AIs in modern human-AI builder teams can build PNAs that they understand fully and behave as expected. The Personal Network Toolkit augments the human-AI builder teams; it doesn't automatically build applications itself.

So we expect most PNAs to be built and rebuilt by AIs — adapting a thematic reference design like fellows_local_db, or building fresh against this spec. When an AI is asked to build a PNA, it is required to follow the contracts of the PNA on the user's behalf, and those contracts are written so the AI can pick them up and check its own work. The user's confidence comes from the spec being clear enough that both they and the AI can read it; as long as the contracts hold, an AI can rewrite a PNA from scratch while the user is still talking to it without changing the user's sovereignty, durability, or privacy posture. The goals below are user-facing needs; the architectural commitments after them are the choices that make those needs achievable.

The longer-arc target is an ecosystem of cooperating PNAs on a single user's device — a Personal Relationship Manager (where private relationship data lives) running alongside one or more Directory Archives, a Contact Manager, and a Calendar app, each in its own bundle. The PRM acts as the meta-workspace: relationship data layered on top of a deduplicated read-only meta-view composed from the other apps' shared stores (Bob's cell from Google + work history from a fellowship directory + email from a Facebook export, resolved into one coherent contact view; the PRM's private overlay attached through stable IDs). The user can also work in clean per-app workspaces when they want a single context. Composing the meta-view requires per-source connectors, dedup with conflict resolution, and disciplined provenance — work for later spec versions. The eventual *ecosystem reference design* is the goal; v0.1 ships one PNA (fellows_local_db) and the spec it conforms to, with the architectural seams sized to let the ecosystem grow into place.

PNAs that participate in such an ecosystem need to be reachable not just to humans but to AI agents acting on the user's behalf. The spec therefore defines MCP server interfaces at four canonical connection points: a **Data operations server** (the Storage slot's read/write surface), an **Ingestion server** (drive imports, dedup, orphan preview), a **Communications server** (with workspace-mediated user consent per AC-19), and a **Diagnostics server** (read-only access to the Debug contract). An AI client (Claude Desktop, Cursor, a local-Ollama-backed agent, or any MCP-capable runtime) can drive a PNA through these servers without modifying its core; canonical implementations will ship with the personal_network_toolkit. Cloud AI clients (anything that sends Private DB rows off-device) require explicit per-call consent — see AC-MCP-A in [§ Universal architectural commitments](#universal-architectural-commitments).

### Goal 1 — Private data sovereignty

The PNA stores two databases: a Shared DB (data the user is OK with external systems mirroring) and a Private DB (data that must stay only on the user's device). The Private DB is protected forever — it never leaves the device, never lands on any server, and is durable across app updates and routine cache clears. The Shared DB doesn't need that lifetime protection. Further decomposition and isolation of data according to privacy constraints is reasonable but unnecessary for the first PNAs envisioned.

> **Why it matters:** Private data — who you confide in, your private notes on people, your communication history — is what most exposes you to surveillance, social-graph mining, and platform abuse. Keeping it on the user's device is the only durable defense. The architectural job of the PNA is to keep the line between shared and private data unmistakably bright.

### Goal 2 — Mirror centralized data sources locally

v0.1 PNAs all operate downstream of SaaS systems of record. This goal exists due to the transitional period we are in — where it is not possible to take back data from centralized SaaS over time, but necessary to continue to interact with those platforms for some time. Users keep contacts in centralized platforms — Google, Apple, Facebook, work directories, organizational directories. A PNA mirrors those locally, producing a Shared DB the workspace can browse offline. Mirroring runs from exports today and may grow to richer pipelines (federated reads, multi-source dedup wizards) as the toolkit matures.

> **Why it matters:** We're in a transitional period. Users won't migrate cold. The bridge from "my contacts are scattered across Google + Apple + Facebook + my fellowship's directory" to "my contacts are local-first" runs through ingesting their existing data, not asking them to maintain a parallel master list. The toolkit makes that ingestion a swappable component so a PNA can mirror one source or many.

### Goal 3 — Secure communication options from inside workspaces

When the user wants to reach out to a contact, the workspace offers a choice of transports — including more secure / decentralized options like Signal, not just `mailto:` and `tel:`.

> **Why it matters:** A user who demands sovereignty of their local data has the same high bar for the private transfer of that data. Defaulting every outreach to email — routed through whoever runs their mail server — is inconsistent with Goal 1. The architectural commitment is that transports are pluggable and the user picks per outreach.

### Goal 4 — Portable, durable, recoverable user data

Private data travels with the user across devices, browsers, and PNA versions. Auto-backup, restore-from-file, and explicit opt-in update flows ensure no silent data loss.

> **Why it matters:** Local-first only delivers on Goal 1 if "local" doesn't mean "trapped on this exact installation forever." Users replace devices, switch browsers, reinstall PNAs. The Private DB has to be exportable, importable, and resilient against accidental wipes — otherwise sovereignty becomes fragility.

### Goal 5 — Locally diagnosable

When something goes wrong, the issue can be diagnosed without compromising Goal 1. Sanitized error capture, runtime build labels, in-app diagnostic panels, user-controlled bug-report flows — all sized to a privacy posture consistent with the rest of the app. In single-user instances with no remote maintainer, the diagnostics primarily serve the user themselves. It goes without saying that source code must be available to the user to modify as they please for the diagnostics to be useful.

> **Why it matters:** A privacy-sovereign user's threshold for what diagnostic data flows anywhere is the same as for the rest of their data. The diagnostic surface is part of the privacy surface, not an exception to it. Many eventual PNAs will be single-user installations with no maintainer at all; the debug substrate has to work in that mode without sending anything anywhere by default. When a sink *is* configured (fellows_local_db sends to a maintainer mailbox), it has to be sanitized and rate-limited so the user trusts using it.

---

## Use cases

A use case names a coherent class of PNA from the user's perspective. A use case typically suggests default axis picks but does not determine them. v0.1 attests two named use cases plus a longer-arc target:

- **Directory Archive** — a snapshot of some external organization's roster (a fellowship, a school, a cohort, a community) plus the user's private overlay on top. Shared data has a single external source; each distributed user receives the same shared data and accumulates their own private overlay. Realized in [fellows_local_db](../Architecture.md).
- **Personal Relationship Manager** — the user's own contact databases (Google + Apple + Facebook + LinkedIn + organizational directories) mirrored locally, plus rich private overlays (notes, tags, groups, comms history, message recency) and tools (LLM-mediated search, visual recall, eventual P2P). Multi-source ingestion. Typically single-user, not distributed onward. PRT-inspired; no PNA-spec-conforming reference design yet. **[draft]**
- **Multi-PNA ecosystem (target, v0.2+)** — multiple cooperating PNAs on one user's device, wired together at runtime by an AI agent via MCP. The PRM acts as the meta-workspace over a deduplicated read-only meta-view composed from the per-PNA shared stores; per-app workspaces remain available for single-context work. No reference design yet; v0.1's contracts are sized to enable it.

Full catalog with attestation status, default axis picks, and reference-design links: [`use_cases.md`](use_cases.md).

---

## Axes

v0.1 names seven independent Axes a PNA picks along. A PNA's *flavor* is the full constellation of picks. Each pick may trigger flavor-derived ACs (the AC-trigger tags appear in [`axes.md`](axes.md), grouped by axis-pick).

- **Composition model** — how slot implementations join. Picks: `build-time-bundle`, `runtime-shell-pipeline`, `runtime-MCP-RPC` (see [§ Composition](#composition)).
- **Distribution** — how the PNA reaches a user's device. Picks: `web-bundle-with-magic-link`, `never-distributed-single-user`, `web-bundle-open`, `app-store-native`, `sideloaded-native`.
- **Storage substrate** — what backs the data layer. Picks: `opfs-sqlite-wasm`, `native-sqlite-via-filesystem`, `idb-only-browser`, `native-sqlcipher`.
- **Ingestion shape** — how the Shared DB is filled and refreshed. Picks: `single-source-static-mirror`, `multi-source-merge-with-dedup`, `single-source-live-pull`, `federated-read` (deferred).
- **Workspace shell** — what the user sees and clicks. Picks: `vanilla-js-spa`, `framework-spa`, `tui-textual`, `cli-subcommands`, `native-shell-tauri`, `native-shell-native`.
- **Comms transport set** — which outreach mechanisms the workspace offers. Picks: `mailto-only`, `mailto-plus-signal`, `mailto-plus-matrix`, `shell-out-to-cli-clients`.
- **MCP-exposure** — which canonical MCP servers (Data ops / Ingestion / Comms / Diagnostics) the PNA hosts. Picks: `none`, `data-ops-only`, `data-ops+comms`, `full`.

Notes on Axis independence:

- Some Axes correlate strongly. `composition:build-time-bundle` is essentially forced by browser-based distribution; `composition:runtime-shell-pipeline` is essentially forced by CLI distribution.
- Some Axes are genuinely orthogonal. A Directory Archive use case could in principle ship as a Tauri-wrapped native shell + native SQLite + build-time-bundle composition; the use case doesn't determine those picks.

Use case is *not* one of these Axes — it's the parent category from which a flavor is instantiated; see [§ Use cases](#use-cases).

Full per-pick catalog with attestation status, AC triggers, and correlation notes: [`axes.md`](axes.md).

---

## Composition

The personal_network_toolkit's stated goal is to make PNAs fast to build. Three attested compositional models, all legitimately "Unix tools philosophy" applied to different substrates:

**Build-time-bundle** (browser PNAs, *intra-bundle*). Slots are JS modules. The composer is a build tool. The bundle is the unit of distribution. IPC inside a bundle is `postMessage` + structured-clone + OPFS handles owned by the dedicated worker. Inter-bundle composition is impossible — browser origin isolation rules it out; the "system" is the single bundle. Composition is at *build time*: the toolkit's composer takes axis picks and assembles a bundle from stock slot modules.

**Runtime-shell-pipeline** (CLI PNAs, *intra-PNA*). Slots are OS processes. The composer is the shell pipeline. SQLite files on disk and stdin/stdout streams serve as pipes. Composition is at *runtime*: the user pipes one tool's output into another (`pnt-contacts-ingest google.zip | pnt-dedup | pnt-directory-build → directory.html`). The toolkit ships independently-installable CLI subcommands; users assemble pipelines ad-hoc.

**Runtime-MCP-RPC** (multi-PNA ecosystem, *inter-PNA*). PNAs expose MCP servers; an AI client (Claude Desktop, Cursor, a custom agent) connects to multiple PNAs simultaneously and orchestrates across them. Composition is at *runtime*, by the AI agent on the user's behalf. Unlike build-time-bundle (impossible across bundles) and runtime-shell-pipeline (CLI-only), runtime-MCP-RPC bridges browser-flavored PNAs and CLI-flavored PNAs because each PNA's MCP server runs as a separate process — browser origin isolation is no obstacle when the composition seam is at the MCP-protocol level, not at the bundle level. This is the composition pattern that makes the ecosystem reference design (multiple PNAs cooperating on one user's device, per the [§ Preamble](#preamble)) possible. The toolkit ships canonical MCP server implementations; each PNA declares its `mcp-exposure` axis pick. See AC-MCP-A and AC-MCP-B in [§ Universal architectural commitments](#universal-architectural-commitments) for the load-bearing constraints.

All three models share the same slot contracts (see [§ Slot map](#slot-map)). A storage module conforming to the spec satisfies the same contract whether it's loaded as a JS module, invoked as a subprocess, or exposed as an MCP server; the *plumbing* differs, the *contract* doesn't. This is the spec's load-bearing claim: it describes slot contracts substrate-neutrally, so the toolkit can ship parallel implementations of each slot — one per composition model — that prove the same conformance.

At the algorithm level (dedup, slug generation, FTS query building, comms eligibility evaluation, image-fallback resolution, multi-source merge), code is shareable across composition models *in principle* — though in practice it's typically written twice, once per host language (Python for CLI, JS for browser), with the spec acting as the shared conformance target. A future spec version may add algorithm specifications precise enough that an automated conformance check can validate both implementations against the same definition.

**v0.1 doesn't ship a composer or stock slot modules.** It ships the spec + one reference design (fellows_local_db). The composer + module library follow when the second reference design (PRM) forces the factoring. This is ship-and-iterate applied to the toolkit: build the monolith first, factor into modules when patterns emerge, ship the modules as a library, let the original app become one consumer of the library.

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
