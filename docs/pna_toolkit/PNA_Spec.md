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

- **Personal network application (PNA).** A PNA is an application that helps a user view contact data and work on relationship data over it as a firewalled data layer with higher security needs than the contact data. The PNA runs local-only, never as SaaS. It bridges SaaS data (which should never contain private relationship data) into a much more functional, customizable user-owned work environment suitable for viewing personal networks, updating private data about them, and interacting with them.

  fellows_local_db is one PNA reference design — making a directory archive useful and fast. Another PNA reference design would be an app that aggregates personal contact data ingested from the big SaaS providers and lets the user operate privately on that data, adding privacy-sensitive notes, searching, and launching tasks from the app. PNAs bridge the old world of SaaS and offer private, custom tools to operate on contact data.

- **Slot.** A slot is a part of a PNA — a code module that handles a specific job within the system. v0.1 names five slots:

  - **Ingestion** — loads contact data into the Shared DB
  - **Storage** — owns the data files and serves queries
  - **Workspace** — runs the UI
  - **Communications** — launches outreach
  - **Distribution** — ships the PNA to other users

  Each slot has a contract; any code that satisfies the contract can fill it — a JavaScript module, a Python package, or an OS process, depending on the target environment. The full catalog and contracts are in [§ Slot map](#slot-map).

- **Interface.** A contract that spans multiple slots. Where a slot is filled by *one* code module, an interface is a shared constraint — either a data shape that multiple slots produce and consume (the Shared and Private DB schemas), or a capability requirement every slot must implement (the Debug contract). v0.1 names three interfaces: **Shared schema**, **Private schema**, **Debug contract**. Catalogued in [§ Slot map](#slot-map) alongside the slots they bind.

- **Workspace.** One of the slots in a PNA: the viewer + editor. The thing the user looks at and clicks. fellows_local_db's workspace is a vanilla-JS SPA in the browser; another PNA's might be a native shell, a Tauri app, a TUI, or a separately-distributed mini-app sharing the same data layer.

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

  v0.1 names six Axes: distribution, storage substrate, ingestion shape, workspace shell, comms transport set, MCP-exposure. The full catalog of attested picks per Axis lives in [`axes.md`](axes.md).

- **Axis pick.** One value on one Axis. Written `axis:value` — for instance `storage:opfs-sqlite-wasm`, `distribution:web-bundle-with-magic-link`. The set of attested picks per Axis is enumerated in [`axes.md`](axes.md).

- **Flavor.** The full constellation of axis picks for a specific PNA. fellows_local_db's flavor: `distribution:web-bundle-with-magic-link + storage:opfs-sqlite-wasm + ingestion:single-source-static-mirror + workspace-shell:vanilla-js-spa + comms:mailto-only + mcp-exposure:none`. Two PNAs of the same use case can have different flavors (a TUI PRM vs. a Tauri-wrapped GUI PRM share the use case but differ on workspace shell and storage). A flavor + a use case together fully identify a PNA's shape.

- **MCP server.** A process exposing PNA capabilities as MCP tools (Anthropic's Model Context Protocol — JSON-RPC over stdio or socket). The spec defines four canonical MCP servers per PNA — Data operations (the Storage slot's read/write surface), Ingestion (drive imports + dedup + orphan preview), Communications (with workspace-mediated user consent), and Diagnostics (read-only access to the Debug contract). An AI client (Claude Desktop, Cursor, a local-Ollama-backed agent, etc.) consumes these servers to drive the PNA. MCP servers are how multiple PNAs cooperate at runtime: a PNA exposing MCP becomes externally reachable so an AI client can wire multiple PNAs together on the user's device even though each is its own bundle.

- **Universal AC vs flavor-derived AC.** Universal ACs derive from goals alone and apply to every PNA. Flavor-derived ACs are triggered by specific axis picks (e.g., `[storage:opfs-sqlite-wasm]`) and apply only when the flavor matches. [§ Universal architectural commitments](#universal-architectural-commitments) lists the universal set; flavor-derived ACs live in [`axes.md`](axes.md), grouped under the axis-pick that triggers them.

---

## Goals

### Preamble

We are at an inflection point. Two shifts are arriving at the same time. Personal data is withdrawing from centralized systems: users are increasingly unwilling to trust Facebook with who they talk to about politics or mental health. At the same time, edge compute and AI agents capable of running serious work locally are arriving fast. The first shift creates demand for tools that keep user data sovereign; the second makes such tools practical to build, run, and recompose at the user's own pace.

A personal network application is a tool for users to manage and use contact and relationship data that makes up their personal networks. A PNA handles a user's contact data and personal-relationship data with strong, declared contracts about how that data is treated. The PNA separates the concerns of editing data shared with other systems from data created and held locally as private.

v0.1 PNAs all operate downstream of SaaS systems of record — they do not modify contact data, although a contact manager might well exist as a plugin to a PNA, or vice-versa. What distinguishes the niche is the architectural promise: shared data is local-first and replaceable; private data is sovereign and protected; the user can reclassify a record's privacy at any time, and the PNA honors it durably; communication transports are user-chosen to meet the user's privacy and other requirements; the user can reason about where their data lives without trusting a vendor.

### Personal Network Toolkit

When building a PNA, specs are foundational because users will increasingly compose software by prompting AI agents, and success is measured by adherence to them.

The Personal Network Toolkit project is an attempt to offer:

- Foundational specs for PNAs
- Production-ready reference applications
- MCP servers

That combination best satisfies the composability model of Software 3.0 in this context. It should ensure that both the humans and the AIs in modern human-AI builder teams can build PNAs that they understand fully and that behave as expected. The Personal Network Toolkit augments the human-AI builder teams; it doesn't automatically build applications itself.

So we expect most PNAs to be built and rebuilt by AIs — adapting a thematic reference design like fellows_local_db, or building fresh against the specs and code herein. 

### Building a PNA

When an AI is asked to build a PNA, it is required to follow the contracts of the PNA on the user's behalf, and those contracts are written so the AI can pick them up and check its own work. The user's confidence comes from the spec being clear enough that both they and the AI can read it.  As long as the contracts hold, an AI can rewrite a PNA from scratch while the user is still talking to it without changing the user's sovereignty, durability, or privacy posture. The goals below are user-facing needs; the architectural commitments after them are the choices that make those needs achievable.

### Vision

One longer-arc target is an ecosystem of cooperating PNAs on a single user's device — a Personal Relationship Manager (where private relationship data lives) running alongside one or more Directory Archives, a Contact Manager, and a Calendar app, each in its own bundle and sharing data as per their contracts.

The PRM acts as the meta-workspace: relationship data layered on top of a deduplicated read-only meta-view composed from the other apps' shared stores (Bob's cell from Google + work history from a fellowship directory + email from a Facebook export, resolved into one coherent contact view; the PRM's private overlay attached through stable IDs). The user can also work in clean per-app workspaces when they want a single context. Composing the meta-view requires per-source connectors, dedup with conflict resolution, and disciplined provenance — work for later spec versions. The eventual *ecosystem reference design* is the goal; v0.1 ships one PNA (fellows_local_db) and the spec it conforms to, along with MCP servers, with the architectural seams sized to let the ecosystem grow into place.

PNAs that participate in such an ecosystem need to be reachable not just to humans but to AI agents acting on the user's behalf. The spec therefore defines MCP server interfaces at four canonical connection points:

- A **Data operations server** — the Storage slot's read/write surface.
- An **Ingestion server** — drives imports, dedup, orphan preview.
- A **Communications server** — with workspace-mediated user consent per AC-19.
- A **Diagnostics server** — read-only access to the Debug contract.

An AI client (Claude Desktop, Cursor, a local-Ollama-backed agent, or any MCP-capable runtime) can drive a PNA through these servers without modifying its core; canonical implementations will ship with the personal_network_toolkit. Cloud AI clients (anything that sends Private DB rows off-device) require explicit per-call consent — see AC-MCP-A in [§ Universal architectural commitments](#universal-architectural-commitments).


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

v0.1 names six independent Axes a PNA picks along. A PNA's *flavor* is the full constellation of picks. Each pick may trigger flavor-derived ACs (the AC-trigger tags appear in [`axes.md`](axes.md), grouped by axis-pick).

- **Distribution** — how the PNA reaches a user's device. Picks: `web-bundle-with-magic-link`, `never-distributed-single-user`, `web-bundle-open`, `app-store-native`, `sideloaded-native`.
- **Storage substrate** — what backs the data layer. Picks: `opfs-sqlite-wasm`, `native-sqlite-via-filesystem`, `idb-only-browser`, `native-sqlcipher`.
- **Ingestion shape** — how the Shared DB is filled and refreshed. Picks: `single-source-static-mirror`, `multi-source-merge-with-dedup`, `single-source-live-pull`, `federated-read` (deferred).
- **Workspace shell** — what the user sees and clicks. Picks: `vanilla-js-spa`, `framework-spa`, `tui-textual`, `cli-subcommands`, `native-shell-tauri`, `native-shell-native`.
- **Comms transport set** — which outreach mechanisms the workspace offers. Picks: `mailto-only`, `mailto-plus-signal`, `mailto-plus-matrix`, `shell-out-to-cli-clients`.
- **MCP-exposure** — which canonical MCP servers (Data ops / Ingestion / Comms / Diagnostics) the PNA hosts. Picks: `none`, `data-ops-only`, `data-ops+comms`, `full`.

Notes on Axis independence:

- Some Axes cluster strongly. Browser-based distribution typically goes with `storage:opfs-sqlite-wasm` and a SPA-style workspace shell. CLI distribution typically goes with `storage:native-sqlite-via-filesystem` and a TUI or CLI workspace shell. [§ Composition](#composition) names these clusters (Browser PNAs, CLI / native PNAs) for shorthand.
- Some Axes are genuinely orthogonal. A Directory Archive use case could in principle ship as a Tauri-wrapped native shell + native SQLite + a browser-style bundle; the use case doesn't determine those picks.

Use case is *not* one of these Axes — it's the parent category from which a flavor is instantiated; see [§ Use cases](#use-cases).

Full per-pick catalog with attestation status, AC triggers, and correlation notes: [`axes.md`](axes.md).

---

## Composition

In v0.1, a PNA is composed by an AI coding agent (Claude Code, Cursor, or similar) working with a user. The agent reads this spec, optionally adapts a reference design like fellows_local_db, uses canonical MCP servers to interact with existing PNA data, and writes the code with the user. **The AI agent is the composer.** v0.1 does not ship a separate build tool that assembles PNAs from stock modules — the toolkit's three deliverables (specs, reference apps, MCP servers) are the materials, and the AI agent uses them.

The agent's job, per this spec, is to:

1. Identify the **use case** with the user (see [§ Use cases](#use-cases)).
2. Walk the user through the **Axes** (see [§ Axes](#axes)) and make picks that fit the user's goals.
3. Generate or adapt code that fills each **slot** (see [§ Slot map](#slot-map)) according to its contract, with implementations consistent with the axis picks.
4. Verify the result against the **universal architectural commitments** (see [§ Universal architectural commitments](#universal-architectural-commitments)) and any flavor-derived commitments triggered by the axis picks (catalogued in [`axes.md`](axes.md)).

### Target environments for one PNA

Two target environments are attested in v0.1:

- **Browser PNAs.** The PNA runs in the user's browser as a web bundle. Storage is OPFS-backed SQLite-WASM owned by a dedicated worker. Distribution typically goes through an HTTP origin (with or without an auth gate). Multiple users can install from the same source. **fellows_local_db is a Browser PNA.**
- **CLI / native PNAs.** The PNA runs as one or more OS processes — a TUI, a CLI subcommand set, or a native GUI (Tauri / Electron / etc.). Storage is a native SQLite file on disk (optionally SQLCipher). Distribution is typically self-install; the PNA is usually single-user. **PRT is the inspiration; a CLI / native PRM reference design is the next planned addition.**

The target environment shapes several axis picks (Distribution, Storage substrate, Workspace shell tend to cluster) but doesn't determine them — a Directory Archive could in principle be either kind. The Axes section names the specific decisions; this section names the high-level clusters.

### Cooperation across multiple PNAs

At runtime, multiple PNAs on a user's device can cooperate through their canonical MCP servers. An AI client (Claude Desktop, Cursor, a custom agent) connects to each PNA's exposed MCP servers and orchestrates across them — pull a contact from a Directory Archive, attach a private note from a PRM, schedule a follow-up in a Calendar app. The AI client is the runtime composer here, just as the AI coding agent was the build-time composer above.

This is the longer-arc *ecosystem reference design* described in [§ Goals § Vision](#vision). v0.1 doesn't yet have multiple cooperating PNAs to demonstrate the pattern, but the architectural seams that enable it — the four canonical MCP server interfaces, AC-MCP-A's cloud-client consent rule, AC-MCP-B's workspace-mediated outreach — are part of v0.1.

Cooperation across PNAs is not the same kind of thing as building one PNA. Building is design-time + AI coding agent + writing code that fills slots. Cooperation is runtime + AI client + invoking MCP tools across already-built PNAs. The two kinds of composition are separate concerns.

---

## Universal architectural commitments

Universal ACs are the architectural commitments derived from the goals alone. They apply to every PNA regardless of flavor.

Recall that a *flavor* is the full set of axis picks a builder makes when shaping a PNA (see [§ Vocabulary](#vocabulary)). **Flavor-derived ACs** are architectural commitments triggered by specific axis picks — they apply only when the flavor includes those picks. Because they depend on specific axis-picks, they're catalogued near them in [`axes.md`](axes.md), grouped under the triggering pick.

Universal ACs (in this file) and flavor-derived ACs (in `axes.md`) share a single stable numbering sequence, so cross-references work regardless of which file the AC ended up in. The gaps you'll see in the table below (no AC-2, AC-3, AC-5, AC-8, AC-12, AC-13, AC-14) are the flavor-derived ACs catalogued in `axes.md`.

The wording in the universal table below is substrate-neutral; specific *forms* (URL parameter vs CLI flag, OPFS vs native filesystem) are flavor-derived realizations of universal contracts.

| ID | Commitment | Serves |
|---|---|---|
| AC-1 | **Two-store ownership split.** Shared data is read-only and externally managed; private data is read-write and locally owned. Separate storage namespaces, separate privacy postures. fellows_local_db realizes this as two SQLite databases via OPFS; a CLI / native PNA might realize it as two SQLite files on the filesystem. | Goal 1 |
| AC-4 | **Versioned cross-boundary handshake.** Every PNA with a storage boundary (worker ↔ workspace in a browser bundle, CLI ↔ DB module in a TUI/CLI tool, native shell ↔ DB process) version-checks at init; mutating ops refused on mismatch; reads still work. Build label is *not* the gate. | Goal 4 |
| AC-6 | **Always-reachable diagnostic escape.** A force-reset / force-unlock affordance is reachable regardless of stuck app state. Form depends on the workspace shell: URL parameter for web SPAs (`?gate=1`), CLI flag for terminal apps (`--reset`), key chord for native shells. | Goal 5 |
| AC-7 | **Self-service field-debug substrate.** Build label, sanitized error capture, diagnostic state-dump, bug-report flow, escape hatch (AC-6), boot watchdog with named phase marks, slow-boot persistence. Specific affordances are shell-derived (badge in a web UI; `--diag` subcommand in a CLI; native diagnostic menu); the substrate is required everywhere. | Goal 5 |
| AC-9 | **Auto-backup of private data on user-edit cadence.** Snapshot the Private store on a per-boot debounced schedule (not per-deploy); rotate to keep a small ring of recoverable points. | Goal 4 |
| AC-10 | **Re-imports of the Shared store are opt-in and non-destructive.** Whether refreshed from the original source (a directory operator pushes an update) or re-mirrored from a centralized platform (the user re-exports their Google contacts), the workspace previews any private references that would be orphaned by the update before the user commits. | Goal 2, Goal 4 |
| AC-11 | **Storage substrate detects concurrent access.** Multi-tab in browsers, multi-process in native — when something else holds the data layer, surface it cleanly with a specific message (not a generic "unsupported"). | Goal 4 |
| AC-15 | **Build label tied to source revision, substituted at build *and* serve time.** Each delivered artifact carries a runtime-visible unique label tied to the source revision. Format is implementation-specific (`<YYYY-MM-DD>-<short-sha>` in fellows_local_db; whatever `--version` reports in CLI tools). | Goal 5 |
| AC-16 | **Communication-transport selection is user-driven.** The workspace surfaces multiple transports — including secure / decentralized options when configured — and the user chooses per outreach. No transport is hardcoded. | Goal 3 |
| AC-17 | **Mirrored data is sourced.** Every record in the Shared store traces to a specific external source the user has explicitly configured. The toolkit doesn't introduce contact data the user hasn't approved. | Goal 2 |
| AC-18 | **Transports cannot read message contents.** A transport's acceptability is about the transport mechanism itself, not the chain it kicks off. `mailto:` passes (hands off to whichever client the user has configured; the downstream provider's behavior — Gmail, Outlook — is outside the toolkit's enforcement). Signal-class protocols pass (encryption-in-protocol). Centralized message-broker SaaS that decodes payloads as part of operating (Slack, Discord) does not pass. Contact-graph retention by the transport is *not* part of the rule — too hard to enforce uniformly across protocols, and varies by user threat model. | Goal 3 |
| AC-19 | **User-visible payload before send.** Any workspace-initiated communication shows the user the full payload — recipients, body, and any data merged in from the Shared or Private store — before the transport is launched. The user can edit or cancel. This applies even to bulk operations (e.g., "email this group of 50"). Workspaces never auto-blast data through transports without the user seeing the composition. | Goal 3 |
| AC-PRM-A | **LLM calls over user data are transports.** Any LLM invocation over Private or Shared data is treated as a transport: local-model is default; cloud-model is opt-in per call; the user sees the prompt and merged data before send. Extension of AC-18 and AC-19 to a new transport class. | Goal 3 |
| AC-PRM-D | **Re-ingestion is always user-initiated.** No background polling of source services (Google Contacts, IMAP, organizational directories). Strengthens AC-10: the user always knows when fresh data is being fetched. | Goal 1, Goal 4 |
| AC-MCP-A | **Cloud AI clients require per-call consent for Private DB access via MCP.** Any MCP tool that returns Private DB rows must either refuse, or require explicit per-session opt-in, when the consuming MCP client is not locally hosted. Local clients (Claude Desktop with a local model, Cursor + local Ollama) are the default green path; cloud clients (Claude API direct, OpenAI API, etc.) are opt-in per call. Concrete realization of AC-PRM-A at the MCP surface. | Goal 1, Goal 3 |
| AC-MCP-B | **MCP Communications tools stage outreach; the workspace launches.** A Communications MCP tool call must not directly fire a transport. It returns a staging ID with the full payload preview; the user confirms via the workspace before the transport launches. The MCP server proposes; the workspace disposes. AC-19 is enforced at the workspace boundary and cannot be bypassed by AI clients. | Goal 3 |

---

## Slot map

The spec defines **five slots** (positions filled by code) and **three interfaces** (cross-cutting contracts spanning multiple slots). The Slot and Interface vocab terms are defined in [§ Vocabulary](#vocabulary).

Each slot has a code-level contract. The typed contracts — JSON Schema for RPC + handshake, OpenAPI fragments for distribution, SQL DDL for schemas, TypeScript declaration for the Communications transport interface, JSON Schema for each canonical MCP server's tool surface — live in [`spec/contracts/`](spec/contracts/).

Many Universal ACs (see [§ Universal architectural commitments](#universal-architectural-commitments)) cite specific slots in their wording. The slot map is the architectural skeleton; the ACs are the load-bearing constraints over it.

### Slots

| Slot | Purpose |
|---|---|
| **Ingestion** | Produces a Shared DB conforming to the Shared schema, from one or many external sources. |
| **Storage** | Owns both DB files (Shared + Private) and serves queries. Implements AC-1's two-store ownership split and AC-4's cross-boundary version handshake. |
| **Workspace** | The user-facing surface — UI, routing, rendering shared + private data, launching communications. Enforces AC-19's user-visible payload before send. |
| **Communications** | Pluggable transport layer for outreach. Honors AC-16's user-driven selection and AC-18's transport eligibility rule. |
| **Distribution** *(optional)* | Delivers the PNA to other users' devices. When the PNA isn't distributed (single-user CLI / native), this slot is empty. |

### Interfaces

| Interface | Purpose |
|---|---|
| **Shared schema** | Data contract for the Shared DB — tables, columns, optional FTS structure, optional per-record asset URL conventions. Produced by Ingestion; consumed by Storage and Workspace. |
| **Private schema** | Data contract for the Private DB — `groups`, `group_members`, `record_tags`, `record_notes`, `settings`, opt-in `record_comms_history`. Owned by Storage; accessed by Workspace through Storage. Durability rules (survives app update + Clear App Cache; wiped only by Reset Everything) are part of the contract. |
| **Debug contract** | Capabilities every slot must implement: build label substitution at build *and* serve time (AC-15), sanitized error capture (with sink endpoint when configured), diagnostic state-dump, bug-report flow, always-reachable escape hatch (AC-6), boot watchdog with named phase marks. |

---

## Scope and versioning

This spec is intentionally narrow. It addresses the user demand and runtime realities we can implement and deploy now. New demand develops further versions of the spec; reference designs continue to satisfy whatever spec version they were built against.

**This is PNA Spec v0.1** (placeholder until real numbering lands). When new demand surfaces or runtime constraints shift, we bump the version, declare what changed in [`CHANGELOG.md`](CHANGELOG.md), and update the architectural commitments accordingly.

Items deliberately deferred to future spec versions:

- **Privacy reclassification migration mechanics.** The Preamble commits PNAs to honoring user-driven privacy reclassification of a record (shared → private). The *implementation pattern* — does the record stay in the Shared DB with a private-side override row that supersedes? Get copied into the Private DB and removed from the Shared DB on next re-mirror? — is not pinned in v0.1. The contract is declared; the migration is left for a future version when the first reference design needs it.
- **Multi-source dedup implementation.** AC-PRM-B (catalogued in [`axes.md`](axes.md) as a draft flavor-derived AC) captures the v0.1 commitment for `ingestion:multi-source-merge-with-dedup` flavors — stable `record_id` survives merge, dedup wizard surfaces conflicts, per-field provenance. The concrete implementation (merge UI, conflict-resolution algorithms) awaits the first multi-source reference design.
- **Per-database (or finer) transport requirements.** A future spec version may let each database — Shared, Private, or any custom database in a richer PNA — declare which transport properties it requires for outbound flow. v0.1 handles the data-transport matching implicitly: AC-18 filters out transports that read content; AC-19 ensures the user sees the full payload before launch; the user resolves the matching in the moment. Explicit per-DB rules (workspaces auto-suggesting or auto-filtering transports based on source DB sensitivity) land when a reference design has an auto-send feature that needs them.
- **Cross-device sync.** Out of scope for v0.1. Future versions may declare a sync protocol; v0.1 explicitly does not.
- **Federated P2P capabilities.** Signed-repo asset pulls (a community member's photos), community-stats aggregation tools (the CRT vision). Out of scope for v0.1.
- **Formally verifiable code.** A longer-arc goal. v0.1 aims for AI-checkable contracts (markdown prose + JSON Schema / OpenAPI / SQL DDL / TypeScript declarations); formal verification (TLA+ / Alloy / etc.) is reserved for a later version.

When any of these become near-term, they get a v0.2+ spec bump and the relevant architectural commitments are revised.
