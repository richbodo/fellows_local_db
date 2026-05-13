# PNA Triage (scaffolding — delete after split)

> Intermediate planning artifact for splitting the existing docs into:
>
> - `docs/pna_toolkit/PNA_Spec.md` — universal personal network app spec; lifts to `personal_network_toolkit/` when that repo is created
> - `docs/pna_toolkit/axes.md` — flavor axis taxonomy + attested picks per axis + flavor-derived ACs grouped by axis-pick trigger
> - `docs/pna_toolkit/use_cases.md` — attested use case catalog (Directory Archive realized; Personal Relationship Manager draft)
> - `docs/pna_toolkit/spec/contracts/` — generic typed contracts (JSON Schema for RPC + handshake, OpenAPI fragments for distribution, SQL DDL for schemas, TypeScript declaration for transport interface, JSON Schema for each canonical MCP server's tool surface)
> - `docs/pna_toolkit/llms.txt` — discovery for the spec itself (lifts with the toolkit)
> - `docs/Architecture.md` — fellows_local_db's specialization + spec-conformance declaration
> - `llms.txt` at repo root — discovery for fellows (stays here)
>
> Working sessions: 2026-05-08, 2026-05-11, 2026-05-12 with @richbodo. Iterative — vocabulary and decomposition evolve as we go.
>
> Read in this order:
> 1. **Vocabulary** — small, deliberate term set
> 2. **Goals** — five user-facing needs we satisfy, with reasoning
> 3. **Use cases** — attested classes of PNA (Directory Archive realized; Personal Relationship Manager draft)
> 4. **Flavor axes** — seven axes a PNA varies along; each axis-pick may trigger flavor-derived ACs
> 5. **Composition** — the two attested compositional models (`build-time-bundle`, `runtime-shell-pipeline`) and what they imply for the toolkit
> 6. **Architectural commitments** — universal ACs (apply to every PNA) + flavor-derived ACs (tagged by axis-pick triggers)
> 7. **Slot map** — three interfaces, five components
> 8. **Part 1** — synthesis per slot (what `PNA_Spec.md` will say)
> 9. **Part 2** — source map (verification: where each claim came from)
> 10. **Part 3** — bugs, missing items, open questions
> 11. **Part 4** — component decomposition (sub-contracts per slot)

---

## Vocabulary

This doc — and the eventual spec — uses a small, deliberate set of terms.

- **Personal network application (PNA).** The category. An app that lets a user view contact data and work on relationship data over it as a firewalled data layer with higher security needs than the contact data.   fellows_local_db is one PNA; Another would be an app that allows you to aggregate personal contact data ingested from the big SaaS providers and operate privately on that data, adding privacy-sensitive notes, and searching and launching tasks from the app.  PNAs bridge the old world of SaaS and offer private, custom tools to operate on contact data.

- **Workspace.** One *component* of a PNA: the viewer + editor. The thing the user looks at and clicks. fellows_local_db's workspace is a vanilla-JS SPA in the browser; another PNA's might be a native shell, a Tauri app, or a separately-distributed mini-app sharing the same data layer.

- **Shared data.** In the context of a PNA, shared data is data that exists in more than one place — typically, a copy held by an external system the user uses (Google Contacts, Apple Contacts, Facebook friends, a fellowship's directory, a school's roster). The user is OK with that external system continuing to hold it, and often has no say in the matter. *Examples:* name, email, photo, organizational membership. The PNA mirrors this data locally so the user can browse and search it without depending on the external system being reachable.

  > "Shared" is the key word — not "public" in the everyday sense.  Shared data can be data that the user publicly shared, or shared with Apple Contacts and exported, and is typically maintained outside the users systems.  The contact data in your Google account isn't *publicly visible*; it just isn't *exclusively yours* - it is shared with Google and any controlling governments or google partners who it is sold to.  In all cases, some external system has a copy, or once did.

- **Private data.** Data that exists only on the user's device(s). The user is *not* OK with any external system holding a copy. *Examples:* notes the user keeps about a contact, tags they apply, groups they assemble, communication history. The PNA's central architectural job is to keep this layer protected, durable, and exclusively local.  This data must never be sent across insecure channels, and must only be explicitly sent by the users command in any form.

- **Shared DB / Private DB.** The two databases that a PNA stores. The Shared DB holds shared data (read-only inside the PNA — written only by the Ingestion component). The Private DB holds private data (read-write from the workspace).  Further decomposition and isolation of data according to privacy constraints is reasonable but unnecessary for the first PNAs envisioned.

  In fellows_local_db, the shared DB is `fellows.db` and the private DB is `relationships.db`. The spec uses the generic names; specializations may rename for ergonomics, or change database engines for practical reasons, as long as the data stays local.

- **Mirroring.** The act of producing a fresh shared DB from an external source of shared data. A snapshot is created by the Ingestion component. Re-mirrors are atomic from the workspace's view (stage, validate, swap) and never silently orphan private references.

- **Plugin / extension.** Anything that adds a capability to a composed PNA without modifying it's core. A memory-assistant view, a calendar overlay, a federated portrait pull, a community-statistics survey tool — all plugins. PNAs themselves will expose MCP server interfaces as well.

- **Reference design / thematic example.** A working, deployed PNA that demonstrates one valid combination of slot-fills against the spec. fellows_local_db is the first reference design — its load-bearing adjectives are *magic-link distributed PWA* (Distribution choice) + *static network DB archive* (Ingestion choice — the directory is mirrored once with opt-in updates, not linked to a live contact manager) + *single shared directory* (Source choice). New reference designs accumulate adjectives as their slot-fills land. AIs adapting a thematic example start from one of these and ask the user which slot-fills to keep, swap, or extend.

- **Use case.** A user-facing class of PNA — "Directory Archive," "Personal Relationship Manager." Names what kind of app this is *from the user's perspective*. v0.1 attests two; future versions will add more. Use case is *not* one of the flavor axes (defined next); it's the parent category that a flavor instantiates. A use case typically suggests default axis picks (Directory Archives gravitate toward web-bundle distribution; PRMs toward never-distributed-single-user) but the axes remain independent — a hypothetical Directory Archive shipped as a Tauri shell + native SQLite is conceivable.

- **Flavor axis.** An independent developer-side dimension along which a PNA's shape varies. Each axis has a small enumerated set of possible values; the builder picks one value per axis when shaping a PNA. *Example:* the **distribution** axis has picks `web-bundle-with-magic-link` (fellows_local_db's pick), `never-distributed-single-user` (PRM's likely pick), `web-bundle-open`, `app-store-native`, `sideloaded-native` — the builder picks one. v0.1 names seven flavor axes: composition model, distribution, storage substrate, ingestion shape, workspace shell, comms transport set, MCP-exposure.

- **Axis pick.** One value on one flavor axis. Written `axis:value` — for instance `storage:opfs-sqlite-wasm`, `distribution:web-bundle-with-magic-link`. The set of attested picks per axis is enumerated in `pna_toolkit/axes.md`.

- **Flavor.** The full constellation of axis picks for a specific PNA. fellows_local_db's flavor: `composition:build-time-bundle + distribution:web-bundle-with-magic-link + storage:opfs-sqlite-wasm + ingestion:single-source-static-mirror + workspace-shell:vanilla-js-spa + comms:mailto-only + mcp-exposure:none`. Two PNAs of the same use case can have different flavors (a TUI PRM vs. a Tauri-wrapped GUI PRM share the use case but differ on workspace shell and storage). A flavor + a use case together fully identify a PNA's shape.

- **Composition model.** One of the seven flavor axes, called out here because its picks shape several other axes. Two attested: `build-time-bundle` (browser PNAs; slots are JS modules; bundler is the seam) and `runtime-shell-pipeline` (CLI PNAs; slots are OS processes; shell pipeline is the seam). A third, `runtime-MCP-RPC`, applies *across* PNAs in the ecosystem composition pattern (see Composition section below). Browser distribution typically forces build-time-bundle; CLI distribution typically forces runtime-shell-pipeline.

- **MCP server.** A process exposing PNA capabilities as MCP tools (Anthropic's Model Context Protocol — JSON-RPC over stdio or socket). The spec defines four canonical MCP servers per PNA — Data operations (the Storage slot's read/write surface), Ingestion (drive imports + dedup + orphan preview), Communications (with workspace-mediated user consent), and Diagnostics (read-only access to the Debug contract). An AI client (Claude Desktop, Cursor, a local-Ollama-backed agent, etc.) consumes these servers to drive the PNA. MCP servers are the basis of the `runtime-MCP-RPC` composition model: a PNA exposing MCP becomes externally composable so an AI agent can wire multiple PNAs together at runtime even though each is its own bundle.

- **Universal AC vs flavor-derived AC.** Universal ACs derive from goals alone and apply to every PNA. Flavor-derived ACs are triggered by specific axis picks (e.g., `[storage:opfs-sqlite-wasm]`) and apply only when the flavor matches. The AC tables tag each entry.

---

## Goals

### Preamble

We are at an inflection point. Two shifts are arriving at the same time. Personal data is withdrawing from centralized systems: users are increasingly unwilling to trust Facebook with who they talk to about politics or mental health. At the same time, edge compute and AI agents capable of running serious work locally are arriving fast. The first shift creates demand for tools that keep user data sovereign; the second makes such tools practical to build, run, and recompose at the user's own pace.

A personal network application is a tool for users to manage and use contact and relationship data that makes up their personal networks.  A PNA handles a user's contact data and personal-relationship data with strong, declared contracts about how that data is treated. The PNA separates the concerns of editing data shared with other systems from data created and held locally as private. 

V0.1 PNAs all operate downstream of SaaS systems of record - they do not modify contact data, although a contact manager might well exist as a plugin to a PNA, or vice-versa. What distinguishes the niche is the architectural promise: shared data is local-first and replaceable; private data is sovereign and protected; the user can reclassify a record's privacy at any time, and the PNA honors it durably; communication transports are user-chosen to meet the user's privacy and other requirements; the user can reason about where their data lives without trusting a vendor.

The spec matters because users will increasingly compose software by prompting AI agents. We expect most PNAs to be built and rebuilt by AIs — adapting a thematic reference design like fellows_local_db, or building fresh against this spec. When an AI is asked to build the P&A, it is required to follow the contracts of the PNA on the user's behalf, and they're written so the AI can pick them up and check its own work. The user's confidence comes from the spec being clear enough that both they and the AI can read it; as long as the contracts hold, an AI can rewrite a PNA from scratch while the user is still talking to it without changing the user's sovereignty, durability, or privacy posture. The goals below are user-facing needs; the architectural commitments after them are the choices that make those needs achievable.

The longer-arc target is an ecosystem of cooperating PNAs on a single user's device — a Personal Relationship Manager (where private relationship data lives) running alongside one or more Directory Archives, a Contact Manager, and a Calendar app, each in its own bundle. The PRM acts as the meta-workspace: relationship data layered on top of a deduplicated read-only meta-view composed from the other apps' shared stores (Bob's cell from Google + work history from a fellowship directory + email from a Facebook export, resolved into one coherent contact view; the PRM's private overlay attached through stable IDs). The user can also work in clean per-app workspaces when they want a single context. Composing the meta-view requires per-source connectors, dedup with conflict resolution, and disciplined provenance — work for later spec versions. The eventual *ecosystem reference design* is the goal; v0.1 ships one PNA (fellows_local_db) and the spec it conforms to, with the architectural seams sized to let the ecosystem grow into place.

PNAs that participate in such an ecosystem need to be reachable not just to humans but to AI agents acting on the user's behalf. The spec therefore defines MCP server interfaces at four canonical connection points: a **Data operations server** (the Storage slot's read/write surface), an **Ingestion server** (drive imports, dedup, orphan preview), a **Communications server** (with workspace-mediated user consent per AC-19), and a **Diagnostics server** (read-only access to the Debug contract). An AI client (Claude Desktop, Cursor, a local-Ollama-backed agent, or any MCP-capable runtime) can drive a PNA through these servers without modifying its core; canonical implementations will ship with the personal_network_toolkit. Cloud AI clients (anything that sends Private DB rows off-device) require explicit per-call consent — see AC-MCP-A below.

### Goal 1 — Private data sovereignty

The PNA stores two databases: a Shared DB (data the user is OK with external systems mirroring) and a Private DB (data that must stay only on the user's device). The Private DB is protected forever — it never leaves the device, never lands on any server, and is durable across app updates and routine cache clears. The Shared DB doesn't need that lifetime protection.  Further decomposition and isolation of data according to privacy constraints is reasonable but unnecessary for the first PNAs envisioned.

> **Why it matters:** Private data — who you confide in, your private notes on people, your communication history — is what most exposes you to surveillance, social-graph mining, and platform abuse. Keeping it on the user's device is the only durable defense. The architectural job of the PNA is to keep the line between shared and private data unmistakably bright.

### Goal 2 — Mirror centralized data sources locally

V0.1 PNAs all operate downstream of SaaS systems of record.  This goal exists due to the transitionary period we are in - where it is not possible to take back data from centralized SaaS over time, but necessary to continue to interact with those platforms for some time.  Users keep contacts in centralized platforms — Google, Apple, Facebook, work directories, organizational directories. A PNA mirrors those locally, producing a Shared DB the workspace can browse offline. Mirroring runs from exports today and may grow to richer pipelines (federated reads, multi-source dedup wizards) as the toolkit matures.

> **Why it matters:** We're in a transitional period. Users won't migrate cold. The bridge from "my contacts are scattered across Google + Apple + Facebook + my fellowship's directory" to "my contacts are local-first" runs through ingesting their existing data, not asking them to maintain a parallel master list. The toolkit makes that ingestion a swappable component so a PNA can mirror one source or many.

### Goal 3 — Secure communication options from inside workspaces

When the user wants to reach out to a contact, the workspace offers a choice of transports — including more secure / decentralized options like Signal, not just `mailto:` and `tel:`.

> **Why it matters:** A user who demands sovereignty of their local data has the same high bar for the private transfer of that data. Defaulting every outreach to email — routed through whoever runs their mail server — is inconsistent with goal 1. The architectural commitment is that transports are pluggable and the user picks per outreach.

### Goal 4 — Portable, durable, recoverable user data

Private data travels with the user across devices, browsers, and PNA versions. Auto-backup, restore-from-file, and explicit opt-in update flows ensure no silent data loss.

> **Why it matters:** Local-first only delivers on goal 1 if "local" doesn't mean "trapped on this exact installation forever." Users replace devices, switch browsers, reinstall PNAs. The Private DB has to be exportable, importable, and resilient against accidental wipes — otherwise sovereignty becomes fragility.

### Goal 5 — Locally diagnosable

When something goes wrong, the issue can be diagnosed without compromising goal 1. Sanitized error capture, runtime build labels, in-app diagnostic panels, user-controlled bug-report flows — all sized to a privacy posture consistent with the rest of the app. In single-user instances with no remote maintainer, the diagnostics primarily serve the user themselves.  It goes without saying that source code must be available to the user to modify as they please for the diagnostics to be useful.

> **Why it matters:** A privacy-sovereign user's threshold for what diagnostic data flows anywhere is the same as for the rest of their data. The diagnostic surface is part of the privacy surface, not an exception to it. Many eventual PNAs will be single-user installations with no maintainer at all; the debug substrate has to work in that mode without sending anything anywhere by default. When a sink *is* configured (fellows_local_db sends to a maintainer mailbox), it has to be sanitized and rate-limited so the user trusts using it.

---

## Use cases

A use case names a coherent class of PNA from the user's perspective. v0.1 attests two; the toolkit composer will eventually target both.

### Directory Archive — realized in fellows_local_db

A snapshot of some external organization's roster (a fellowship, a school, a cohort, a community) plus the user's private overlay on top. Shared data has a *single external source* — typically the organization that previously hosted the directory as a SaaS service, or a maintainer who curates updates. Each distributed user receives the same shared data and accumulates their own private overlay (groups, tags, notes). Distribution typically goes outward to many users from a maintainer or organizer; the toolkit's role is to make that distribution easy and safe.

fellows_local_db (this repo) is the first reference design. Its picks across the seven flavor axes are listed in Flavor axes below; the ACs it inherits are the universal set plus those triggered by its picks.

### Personal Relationship Manager — draft (no PNA-spec-conforming reference design yet)

The user's *own* contact databases (Google + Apple + Facebook + LinkedIn + organizational directories) mirrored locally, plus rich private overlays (notes, tags, groups, comms history, message recency) and tools (LLM-mediated search, visual recall, eventual P2P). Shared data has multiple sources the user controls; ingestion involves a dedup pass. Typically single-user, not distributed onward — the PRM is for one person's contact graph.

PRT (`../prt/`) is the inspiration but pre-dates this spec. A future PRM reference design built against PNA Spec v0.1 will live in its own repo. AC-PRM-* entries in this triage are **[draft]** until that reference design lands. Capturing the draft now is deliberate: a second use case stress-tests the universal-vs-flavor partition — an AC that fires for both DA and PRM is genuinely universal; an AC that fires for only one is flavor-derived and gets axis-pick triggers.

### Multi-PNA ecosystem — target use case (v0.2+, no reference design)

The longer-arc goal introduced in the Preamble: multiple PNAs cooperating on one user's device, wired together at runtime by an AI agent via MCP. Roles in the ecosystem:

- **Personal Relationship Manager** — holds private relationship data (notes, tags, groups, history); hosts the meta-workspace where the user sees their full picture.
- **Contact Manager** — edits and manipulates shared contact data (typically downstream of Google / Apple / Facebook exports). A contact manager could also exist as a plugin to the PRM, or interact via MCP.
- **Directory Archive(s)** — one or more snapshots of external organizational rosters (a fellowship, a school, an old workplace). fellows_local_db is one instance.
- **Calendar app** — events, scheduling, relationship-temporal data.

The user wants two complementary modes:

- **Per-PNA workspaces (always clean).** Just the fellows directory; just Google contacts; just Facebook contacts. Single-context, focused, fast — useful for tasks scoped to one source.
- **Unified meta-view (in the PRM).** A read-only composed database deduplicating across the per-PNA shared stores. Bob's cell from Google + work history from a fellowship directory + email from a Facebook export combine into one coherent contact view. The PRM's private overlay (notes, tags, groups) references unified-view records via stable IDs; private data stays in the PRM regardless of which shared source contributed the underlying contact record.

Achieving the unified meta-view requires per-source database connectors, careful dedup and conflict resolution, and disciplined provenance — substantial work that's deferred to later spec versions. The eventual *ecosystem reference design* would demonstrate this; v0.1 establishes the architectural seams (composition models, MCP server contracts, AC-10's opt-in non-destructive re-imports, AC-PRM-B's multi-source dedup contract, the four canonical MCP servers) that let the ecosystem grow into place.

This is the deep "why" behind defining slot contracts substrate-neutrally: when the second PNA exists, an AI agent can wire it to fellows without modifying either; when the fifth PNA exists, the same. Composability isn't bolted on; it's the architecture's primary deliverable.

---

## Flavor axes

Seven independent axes a PNA picks along. A PNA's *flavor* is the full constellation of picks. Each pick may trigger flavor-derived ACs (see Architectural commitments below for the trigger tags). Use case is *not* one of these axes — it's the parent category from which a flavor is instantiated; see the Use cases section above.

| Axis | fellows_local_db pick | PRM (draft) pick | Other plausible picks |
|---|---|---|---|
| Composition model | `build-time-bundle` | `runtime-shell-pipeline` | `runtime-MCP-RPC` (composes *across* bundles via MCP); browser distribution typically forces build-time, CLI typically forces runtime |
| Distribution | `web-bundle-with-magic-link` | `never-distributed-single-user` | `web-bundle-open`, `app-store-native`, `sideloaded-native` |
| Storage substrate | `opfs-sqlite-wasm` | `native-sqlite-via-filesystem` | `idb-only-browser`, `native-sqlcipher` |
| Ingestion shape | `single-source-static-mirror` | `multi-source-merge-with-dedup` | `single-source-live-pull`, `federated-read` (deferred) |
| Workspace shell | `vanilla-js-spa` | `tui-textual` or `cli-subcommands` | `framework-spa`, `native-shell-tauri`, `native-shell-native` |
| Comms transport set | `mailto-only` (Signal planned) | `shell-out-to-cli-clients` | `mailto-plus-signal`, `mailto-plus-matrix` |
| MCP-exposure | `none` (v1); `data-ops-only` planned | `full` (all four servers) | `none`, `data-ops-only`, `data-ops+comms`, `full` |

Notes on axis independence:

- Some axes correlate strongly. `composition:build-time-bundle` is essentially forced by browser-based distribution; `composition:runtime-shell-pipeline` is essentially forced by CLI distribution.
- Some axes are genuinely orthogonal. A Directory Archive use case could in principle ship as a Tauri-wrapped native shell + native SQLite + build-time-bundle composition; the use case doesn't determine those picks.
- Picks attested in PRT but not yet attested against a PNA-spec-conforming reference design are tagged `[draft]` in the flavor table and throughout the AC tables.

---

## Composition

The personal_network_toolkit's stated goal is to make PNAs fast to build. Three attested compositional models, all legitimately "Unix tools philosophy" applied to different substrates:

**Build-time-bundle** (browser PNAs, *intra-bundle*). Slots are JS modules. The composer is a build tool. The bundle is the unit of distribution. IPC inside a bundle is `postMessage` + structured-clone + OPFS handles owned by the dedicated worker. Inter-bundle composition is impossible — browser origin isolation rules it out; the "system" is the single bundle. Composition is at *build time*: the toolkit's composer takes axis picks and assembles a bundle from stock slot modules.

**Runtime-shell-pipeline** (CLI PNAs, *intra-PNA*). Slots are OS processes. The composer is the shell pipeline. SQLite files on disk and stdin/stdout streams serve as pipes. Composition is at *runtime*: the user pipes one tool's output into another (`pnt-contacts-ingest google.zip | pnt-dedup | pnt-directory-build → directory.html`). The toolkit ships independently-installable CLI subcommands; users assemble pipelines ad-hoc.

**Runtime-MCP-RPC** (multi-PNA ecosystem, *inter-PNA*). PNAs expose MCP servers; an AI client (Claude Desktop, Cursor, a custom agent) connects to multiple PNAs simultaneously and orchestrates across them. Composition is at *runtime*, by the AI agent on the user's behalf. Unlike build-time-bundle (impossible across bundles) and runtime-shell-pipeline (CLI-only), runtime-MCP-RPC bridges browser-flavored PNAs and CLI-flavored PNAs because each PNA's MCP server runs as a separate process — browser origin isolation is no obstacle when the composition seam is at the MCP-protocol level, not at the bundle level. This is the composition pattern that makes the ecosystem reference design (multiple PNAs cooperating on one user's device, per the Preamble) possible. The toolkit ships canonical MCP server implementations; each PNA declares its `mcp-exposure` axis pick. See AC-MCP-A and AC-MCP-B below for the load-bearing constraints.

All three models share the same slot contracts (see Slot map + Part 1 + Part 4 below). A storage module conforming to the spec satisfies the same contract whether it's loaded as a JS module, invoked as a subprocess, or exposed as an MCP server; the *plumbing* differs, the *contract* doesn't. This is the spec's load-bearing claim: it describes slot contracts substrate-neutrally, so the toolkit can ship parallel implementations of each slot — one per composition model — that prove the same conformance.

At the algorithm level (dedup, slug generation, FTS query building, comms eligibility evaluation, image-fallback resolution, multi-source merge), code is shareable across composition models *in principle* — though in practice it's typically written twice, once per host language (Python for CLI, JS for browser), with the spec acting as the shared conformance target. A future spec version may add algorithm specifications precise enough that an automated conformance check can validate both implementations against the same definition.

**v0.1 doesn't ship a composer or stock slot modules.** It ships the spec + one reference design (fellows_local_db). The composer + module library follow when the second reference design (PRM) forces the factoring. This is ship-and-iterate applied to the toolkit: build the monolith first, factor into modules when patterns emerge, ship the modules as a library, let the original app become one consumer of the library.

---

## Architectural commitments (derived from goals + flavor-axis picks)

These are load-bearing rules the spec will enforce. They split into two tables:

- **Universal ACs** derive from goals alone. They apply to every PNA regardless of flavor. The wording is substrate-neutral; specific *forms* (URL parameter vs CLI flag, OPFS vs native filesystem) are flavor-derived realizations of the universal contract.
- **Flavor-derived ACs** are triggered by specific axis picks. They apply only when the flavor matches. Each is tagged with axis-pick triggers; multiple triggers mean *all must match* for the AC to fire (logical AND).

Some original ACs were generalized during the partition pass. Where the original fellows-specific form was load-bearing (`?gate=1`, `OPFS SAH-pool`, etc.), the universal form names the contract and the flavor-derived form names the realization. References to the original AC numbers are preserved.

### Universal ACs (apply to every PNA)

| ID | Commitment | Serves |
|---|---|---|
| AC-1 | **Two-store ownership split.** Shared data is read-only and externally managed; private data is read-write and locally owned. Separate storage namespaces, separate privacy postures. (Storage substrate — what the stores are *made of* — is flavor-derived; fellows realizes this as two SQLite databases via OPFS; PRT realizes it as two SQLite files on the filesystem.) | Goal 1 |
| AC-4 | **Versioned cross-boundary handshake.** Every PNA with a storage boundary (worker ↔ workspace in a browser bundle, CLI ↔ DB module in a TUI/CLI tool, native shell ↔ DB process) version-checks at init; mutating ops refused on mismatch; reads still work. Build label is *not* the gate. *Generalized from the original `[shell:web-spa] + [storage:opfs-sqlite-wasm]` form.* | Goal 4 |
| AC-6 | **Always-reachable diagnostic escape.** A force-reset / force-unlock affordance is reachable regardless of stuck app state. Form depends on shell: URL parameter for web SPAs (`?gate=1`), CLI flag for terminal apps (`--reset`), key chord for native shells. *Generalized from the original fellows-specific `?gate=1` form.* | Goal 5 |
| AC-7 | **Self-service field-debug substrate.** Build label, sanitized error capture, diagnostic state-dump, bug-report flow, escape hatch (AC-6), boot watchdog with named phase marks, slow-boot persistence. Specific affordances are shell-derived (badge in a web UI; `--diag` subcommand in a CLI; native diagnostic menu); the substrate is required everywhere. | Goal 5 |
| AC-9 | **Auto-backup of private data on user-edit cadence.** Snapshot the Private store on a per-boot debounced schedule (not per-deploy); rotate to keep a small ring of recoverable points. | Goal 4 |
| AC-10 | **Re-imports of the Shared store are opt-in and non-destructive.** Whether refreshed from the original source (a directory operator pushes an update) or re-mirrored from a centralized platform (the user re-exports their Google contacts), the workspace previews any private references that would be orphaned by the update before the user commits. | Goal 2, Goal 4 |
| AC-11 | **Storage substrate detects concurrent access.** Multi-tab in browsers, multi-process in native — when something else holds the data layer, surface it cleanly with a specific message (not a generic "unsupported"). *Generalized from the original `[storage:opfs-sqlite-wasm]` multi-tab form.* | Goal 4 |
| AC-15 | **Build label tied to source revision, substituted at build *and* serve time.** Each delivered artifact carries a runtime-visible unique label tied to the source revision. Format is implementation-specific (`<YYYY-MM-DD>-<short-sha>` in fellows; whatever `--version` reports in CLI tools). | Goal 5 |
| AC-16 | **Communication-transport selection is user-driven.** The workspace surfaces multiple transports — including secure / decentralized options when configured — and the user chooses per outreach. No transport is hardcoded. | Goal 3 |
| AC-17 | **Mirrored data is sourced.** Every record in the Shared store traces to a specific external source the user has explicitly configured. The toolkit doesn't introduce contact data the user hasn't approved. | Goal 2 |
| AC-18 | **Transports cannot read message contents.** A transport's acceptability is about the transport mechanism itself, not the chain it kicks off. mailto: passes (hands off to whichever client the user has configured; the downstream provider's behavior — Gmail, Outlook — is outside the toolkit's enforcement). Signal-class protocols pass (encryption-in-protocol). Centralized message-broker SaaS that decodes payloads as part of operating (Slack, Discord) does not pass. Contact-graph retention by the transport is *not* part of the rule — too hard to enforce uniformly across protocols, and varies by user threat model. | Goal 3 |
| AC-19 | **User-visible payload before send.** Any workspace-initiated communication shows the user the full payload — recipients, body, and any data merged in from the Shared or Private store — before the transport is launched. The user can edit or cancel. This applies even to bulk operations (e.g., "email this group of 50"). Workspaces never auto-blast data through transports without the user seeing the composition. | Goal 3 |
| AC-PRM-A | **LLM calls over user data are transports.** Any LLM invocation over Private or Shared data is treated as a transport: local-model is default; cloud-model is opt-in per call; user sees the prompt and merged data before send (extension of AC-18 + AC-19 to a new transport class). Promoted from PRM-flavor to universal because any PNA may add LLM features. | Goal 3 |
| AC-PRM-D | **Re-ingestion is always user-initiated.** No background polling of source services (Google Contacts, IMAP, organizational directories). Strengthening of AC-10: the user always knows when fresh data is being fetched. | Goal 1, Goal 4 |
| AC-MCP-A | **Cloud AI clients require per-call consent for Private DB access via MCP.** Any MCP tool that returns Private DB rows must either refuse, or require explicit per-session opt-in, when the consuming MCP client is not locally hosted. Local clients (Claude Desktop with a local model, Cursor + local Ollama) are the default green path; cloud clients (Claude API direct, OpenAI API, etc.) are opt-in per call. Concrete realization of AC-PRM-A at the MCP surface. | Goal 1, Goal 3 |
| AC-MCP-B | **MCP Communications tools stage outreach; the workspace launches.** A Communications MCP tool call must not directly fire a transport. It returns a staging ID with the full payload preview; the user confirms via the workspace before the transport launches. The MCP server proposes; the workspace disposes. AC-19 (user-visible payload before send) is enforced at the workspace boundary and cannot be bypassed by AI clients. | Goal 3 |

### Flavor-derived ACs (triggered by axis picks)

| ID | Commitment | Triggered by |
|---|---|---|
| AC-2 | **No SaaS surface.** Server (when present) is a delivery channel, not a service. No per-user RW endpoints, no server-side persistence of private data, no admin console, no cross-device sync. | `[dist:server-backed]` |
| AC-3 | **Single OPFS owner.** All OPFS handles and SQLite-WASM instances live in one dedicated worker. The workspace is an RPC client. No parallel main-thread OPFS. *Form-of-AC-1 + form-of-AC-11 for this substrate.* | `[storage:opfs-sqlite-wasm]` |
| AC-5 | **Stale session never locks users out of cached data.** A 401/403 from any shared-side fetch falls through to the local cache. Fresh data requires explicit user action. | `[dist:auth-gated]` |
| AC-8 | **Anti-enumeration on auth + abuse-bounded analytics.** Distribution-channel auth endpoints always return neutral payloads; per-IP rate limits; sanitized error sink doubles as analytics pipe (`kind=install`, `kind=worker`, …) with no widening of the privacy boundary. | `[dist:auth-server]` + `[debug:has-error-sink]` |
| AC-12 | **Capability detection inside the worker, UA-parsing for messaging only.** Browsers lie about main-thread OPFS support; the worker is the only context where the answer is reliable. UA strings inform error messages, never gating. | `[storage:opfs-sqlite-wasm]` |
| AC-13 | **COOP/COEP required.** OPFS-SAH-Pool needs `crossOriginIsolated`; both dev server and prod reverse proxy must send `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`. Without this, the storage substrate silently fails to install. | `[storage:opfs-sqlite-wasm]` + `[dist:web-served]` |
| AC-14 | **Service worker never owns SQLite.** SW lifecycle (idle eviction, multi-instance, restart on push) is hostile to data ownership. SW is app-shell + update detection only. The Shared store URL is explicitly bypassed in the SW fetch handler. | `[dist:pwa]` |
| AC-PRM-B | **Multi-source dedup contract.** Stable `record_id` survives merge across sources; dedup wizard surfaces conflicts; per-source provenance is recorded *per field*, not just per record. Lifts the deferred "multi-source dedup contract" from Scope into v0.1 for PRM-flavor PNAs. **[draft — no reference design yet]** | `[ingestion:multi-source-merge-with-dedup]` |
| AC-PRM-C | **Single-instance file-lock.** Native SQLite demands one writer; second process refuses cleanly with a specific message naming the holding process. *Form-of-AC-11 for this substrate.* **[draft — no reference design yet]** | `[storage:native-sqlite-via-filesystem]` |

---

## Slot map

Three interfaces (data + cross-cut contracts) + five components (slots an implementation fills):

| Kind | Name | Purpose |
|---|---|---|
| Interface | **Shared schema** | Read-only data contract — what the Shared DB looks like |
| Interface | **Private schema** | Read-write data contract — what the Private DB looks like |
| Interface | **Debug contract** | Every component implements: build label, sanitized error sink, ?diag, boot watchdog hooks |
| Component | **Ingestion** | Produce a conforming Shared DB from one or many sources |
| Component | **Storage** | OPFS-resident sqlite-wasm via dedicated worker; two-DB pattern; version handshake |
| Component | **Workspace** | UI; routing; render shared + private data; launch communications |
| Component | **Communications** | Outreach transports the user controls |
| Component | **Distribution** *(optional)* | Ship + refresh to other users; auth/allowlist; signed bundle |

A PNA *instance* fills each component slot with an implementation. fellows_local_db's slot-fills are the subject of `Architecture.md` after the split.

---

## Scope and versioning

This spec is intentionally narrow. It addresses the user demand and runtime realities we can implement and deploy now. New demand develops further versions of the spec; reference designs continue to satisfy whatever spec version they were built against.

**This is PNA Spec v0.1** (placeholder until real numbering lands). When new demand surfaces or runtime constraints shift, we bump the version, declare what changed in `CHANGELOG.md`, and update the architectural commitments accordingly.

Items deliberately deferred to future spec versions:

- **Privacy reclassification migration mechanics.** Para 2 of the preamble commits the PNA to honoring a user-driven privacy reclassification of a record (shared → private). The implementation pattern — does the record stay in the Shared DB with a private-side override row that supersedes? Get copied into the Private DB and removed from the Shared DB on next re-mirror? — is not pinned in v0.1. The contract is declared; the migration is left for a future version when the first reference design needs it.
- **Multi-source dedup contract.** v0.1 assumes single-source ingestion. The personal-aggregator case (Google + Apple + Facebook merged into one Shared DB) lands in a future version when the first multi-source reference design is built.
- **Per-database (or finer) transport requirements.** A future spec version may let each database — Shared, Private, or any custom database in a richer PNA — declare which transport properties it requires for outbound flow. v0.1 handles the data-transport matching implicitly: AC-18 filters out transports that read content; AC-19 ensures the user sees the full payload before launch; the user resolves the matching in the moment. Explicit per-DB rules (workspaces auto-suggesting or auto-filtering transports based on source DB sensitivity) land when a reference design has an auto-send feature that needs them.
- **Cross-device sync.** Out of scope for v0.1. Future versions may declare a sync protocol; v0.1 explicitly does not.
- **Federated p2p capabilities.** Signed-repo asset pulls (a community member's photos), community-stats aggregation tools (the CRT vision @richbodo described). Out of scope for v0.1.
- **Formally verifiable code.** A longer-arc goal. v0.1 aims for AI-checkable contracts (markdown prose + JSON Schema / OpenAPI / SQL DDL); formal verification (TLA+ / Alloy / etc.) is reserved for a later version.

When any of these become near-term, they get a v0.2+ spec bump and the relevant architectural commitments are revised.

---

## Classification key

| Tag | Meaning | Destination |
|---|---|---|
| `pna-cat` | Category-level (no single slot) — universal invariants | `pna_toolkit/PNA_Spec.md`, top-level |
| `pna-shared` / `pna-private` / `pna-debug` | Generic, lives under that interface | `pna_toolkit/PNA_Spec.md`, interface section |
| `pna-ingest` / `pna-storage` / `pna-workspace` / `pna-comms` / `pna-dist` | Generic, lives under that component | `pna_toolkit/PNA_Spec.md`, component section |
| `axis:<axis-pick>` | Flavor-derived; lives in axes.md under the relevant axis-pick (e.g., `axis:storage:opfs-sqlite-wasm`) | `pna_toolkit/axes.md`, axis-pick section |
| `use-case:<name>` | Lives in use_cases.md under the named use case | `pna_toolkit/use_cases.md` |
| `fellows-{slot}` | fellows_local_db's choice for that slot | `docs/Architecture.md`, slot section |
| `fellows-cat` | Specialization-only invariant or operator concern | `docs/Architecture.md` |
| `STALE` | Wrong / outdated; fix in place before either spec inherits | Source doc |
| `MISSING` | Not in any doc; needs to be added | `pna_toolkit/PNA_Spec.md` or `docs/Architecture.md` |
| `DROP` | Tribal knowledge; doesn't earn a spec line | — |

**Note on `pna-cat` ↔ axis tags:** Source-map rows previously tagged `pna-cat` that referenced AC-2 through AC-14's *original* forms have been left as `pna-cat` for now; the AC table partition above is the authoritative source for whether the AC is universal or flavor-derived. Part 2's source map will get a `Destination` column refinement pass after the AC partition has settled.

---

# Part 1 — Synthesis per slot

What `PNA_Spec.md` will declare for each interface / component, drawn from the triage. fellows_local_db's specific slot-fills are noted separately under each slot.

## Category-level invariants (`pna-cat`)

The universal ACs from the partition above (AC-1, AC-4, AC-6, AC-7, AC-9, AC-10, AC-11, AC-15, AC-16, AC-17, AC-18, AC-19, AC-PRM-A, AC-PRM-D — 14 in v0.1). `PNA_Spec.md` leads with these; each gets one paragraph. The flavor-derived ACs are not category-level — they live in `axes.md` under the axis-pick that triggers them. The goals section sits above the universal ACs.

## Shared schema (`pna-shared`)

**Contract.** A conforming Shared DB is a SQLite database containing:

- A required primary record table (canonically named `records` in the spec; specializations may rename — fellows_local_db calls it `fellows`) with a stable core column set:
  - `record_id TEXT PRIMARY KEY` — opaque, stable across re-mirrors
  - `slug TEXT NOT NULL UNIQUE` — display URL key; deterministic from name
  - `name TEXT NOT NULL` — display label
  - Plus zero or more app-defined display columns (name, bio, avatar URL, …). The spec defines the slot; ingestion fills it.
- An overflow column `extra_json TEXT` carrying any source-specific keys not in the explicit column set; the workspace merges these into per-record API responses without per-field schema knowledge.
- An optional FTS5 virtual table indexing whichever columns the workspace wants to search.
- An optional per-record asset URL convention (e.g. `/images/<slug>.{jpg,png}` in fellows_local_db) — separate from the database, cacheable, immutable, slug-keyed.

**Read-only enforcement** at the SQLite level via `ATTACH DATABASE … ?mode=ro` whenever joined from the Private DB (worker-internal; happens once per init in the OPFS path). Any stray write into the attached namespace raises `OperationalError`.

**Re-import semantics.** Replacing the Shared DB is atomic from the workspace's point of view: stage → validate → swap. No partial states observable. On replacement, every `record_id` referenced by the Private DB is checked against the new shared records; orphans are flagged for the user, never silently dropped (per AC-10).

**Mirrored-source provenance.** Every record traces to a specific external source the user has approved. Multi-source PNAs include a `source` column; single-source PNAs may omit it (per AC-17).

**fellows_local_db specifics:** see Architecture.md § Shared schema specialization (17 explicit columns + extra_json; FTS5 over name/bio/cohort/fellow_type/search_tags/key_links; record table named `fellows`).

## Private schema (`pna-private`)

**Contract.** The Private DB is a SQLite database containing at minimum:

- `groups(id, name, note, created_at, updated_at)` — user-curated subsets
- `group_members(group_id, record_id, PRIMARY KEY(group_id, record_id))` — joins a group to records; `ON DELETE CASCADE` on group_id; foreign keys ON
- `record_tags(record_id, tag, created_at, PRIMARY KEY(record_id, tag))` — per-record tags
- `record_notes(record_id PRIMARY KEY, body, updated_at)` — per-record freeform notes
- `record_comms_history(id INTEGER PRIMARY KEY, record_id, transport, direction, occurred_at, summary)` — opt-in log of outreach launched from the workspace. **Disabled by default.** User must explicitly enable via `settings['comms_history_enabled']='1'`; the workspace honors the flag and never writes to this table when disabled. User has full read / edit / delete control over the rows; rows live in the Private DB and are protected by AC-1 (never leave the device).
- `settings(workspace_id, key, value, PRIMARY KEY(workspace_id, key))` — key/value bag partitioned by workspace ID. Single-workspace PNAs use empty-string `workspace_id` (default); multi-workspace PNAs (per the "one origin, many workspaces" decision) use their workspace's ID so each workspace has its own settings namespace.

`PRAGMA user_version` set to the schema version at bootstrap so future migrations can branch on it. `PRAGMA foreign_keys = ON` per connection (sqlite default is OFF; without it the cascade is silently inert).

**Durability.** The Private DB is never replaced on app update. It survives Clear App Cache. It is wiped only by Reset Everything (explicit user choice).

**Auto-backup.** Worker `init` snapshots the Private DB to `private.db.bak.<ISO>` at OPFS root (outside the SAH-pool dir) on a per-boot debounced schedule, rotated to keep newest N. Trigger keyed to user-edit cadence, not deploy cadence.

**Restore.** Two paths surfaced from the workspace: restore from a user-supplied file, restore from a recent auto-backup. Both validate via `PRAGMA quick_check` + schema check, snapshot the live DB before replacement, atomically swap, and re-bootstrap schema (idempotent CREATE IF NOT EXISTS so older backups gain new tables).

**fellows_local_db specifics:** filename is `relationships.db`; tables named `fellow_tags` / `fellow_notes` / `group_members.fellow_record_id` for in-app ergonomics.

## Debug contract (`pna-debug`)

Every component implements this. PNA_Spec.md declares it once; per-component sections reference it.

**Build label substitution.** Every component shipping JS / config / templates supports placeholder substitution at build *and* serve time (so dev and dist agree byte-for-byte). Format: `<YYYY-MM-DD>-<short-sha>` from the source repo's HEAD.

**Build badge.** The workspace renders an always-visible badge showing local + server build labels.

**Boot phase marks + watchdog.** Every component contributes named marks at meaningful boot transitions. The workspace runs a watchdog that surfaces a recovery panel naming the last completed mark. Slow boots persist a one-line record to localStorage so a regression captured one session is readable in the next.

**Sanitized error sink.** A single unauthenticated POST endpoint (when configured — purely-personal PNAs may have no sink at all). Body: `{events, ua, build, route, displayMode, online, lastSubmitHashPrefix}`. 16KB body cap; per-IP rate limit; always 204; events typed via a `kind=` enum allowlist; free-text fields sanitized server-side. Privacy boundary is *server-side*, not trusted to the client.

**Sink doubles as analytics pipe.** Adding a new `kind=` enum (e.g., `install`, `worker`, `comms`) is the only widening lever. No separate analytics endpoint, no separate identifier scheme.

**Bug-report dialog.** Workspace ships a dialog that collects the same diagnostic block as ?diag and opens a `mailto:` to a configured maintainer (when one is configured).

**Force-gate / force-reset escape hatch.** Reachable from ?diag *and* from a hardcoded URL parameter, regardless of cookie / localStorage state.

**Configurability.** Every part of the debug contract is configurable. A purely personal PNA may have no error sink and no maintainer mailbox; the build badge and ?diag panel still work, error capture goes to localStorage only.

**fellows_local_db specifics:** sink at `/api/client-errors`; bug report to `richbodo@gmail.com`; force-gate URL is `/?gate=1`; substituted placeholders are `__FELLOWS_UI_DIAG__` and `__CACHE_VERSION__`.

## Ingestion (`pna-ingest`)

**Contract.** Produces a Shared DB conforming to the shared schema. Inputs and pipeline are app-specific. Output must validate via `PRAGMA quick_check` and the primary record table must have ≥1 row (zero-row guard prevents silent orphaning of all private references).

**Update mechanics.** When the user opts into a re-mirror (per AC-10), Ingestion produces fresh bytes and stages them; Storage validates and atomically swaps. The workspace's preview step computes affected `private.group_members` rows whose `record_id` is no longer in the new shared records — and surfaces them by name to the user before commit.

**Possible richer ingestion shapes (toolkit-future):**

- Multi-source merge (Google + Apple + Facebook + custom CSVs) with a deduplication wizard (UI for resolving merge conflicts across record_ids)
- Per-source provenance tracking (`source` column on every record)
- Re-ingestion that preserves stable `record_id` across source changes
- Incremental ingestion (only changed records) when source supports it

**fellows_local_db specifics:** Knack JSON ETL via `build/restore_from_knack_scrapefile.py`; image fallback chain `app/fellow_profile_images_by_name/` → `final_fellows_set/`; alpha-only fuzzy filename match; one source, no dedup needed.

## Storage (`pna-storage`)

The most architecturally constrained slot. Most of the AC commitments live here.

**Substrate.** SQLite-WASM via OPFS-SAH-Pool VFS, owned by a single dedicated worker. Page is RPC client.

**Worker init contract.** First message must be `op='init'`. Returns handshake blob:

```
{
  workerRpcVersion: int,
  schemaVersion: int,
  buildLabel: string,
  opfsCapable: bool,
  hasSharedDb: bool,
  hasPrivateDb: bool,
  poolFiles: string[],
  trace: string[]
}
```

Workspace reads the version fields and refuses mutating RPCs on mismatch (passive — the SW's reload banner is the canonical update affordance). `opfsCapable=false` triggers the unsupported-browser panel from the workspace.

**RPC protocol.** `{id, op, args}` from page → `{id, ok:true, result}` or `{id, ok:false, error, errorName?, errorCode?, httpStatus?, meta?, stack?}` from worker. Fan-in via sequence-numbered pending Map. Worker `onerror` rejects all pending RPCs with `workerScriptError=true` so callers can fall back instead of hanging.

**Capability detection.** Inside `init` (per AC-12). UA-parsing in the workspace for messaging only.

**Two databases.** Private DB (RW) opened via `OpfsSAHPoolDb`; Shared DB (read-only) opened via the same when present, fetched on cold start by an `ensureSharedDb`-style RPC. Names canonicalized to leading-slash form (SAH-pool quirk: `importDb('foo')` and `OpfsSAHPoolDb('foo')` resolve differently without it).

**Auto-backup.** Per AC-9. Backups live at OPFS root, not inside SAH-pool, so they survive normal sqlite-wasm operations. Rotation by sorted ISO filename.

**Opt-in update.** Per AC-10. `compareSha → previewSwap → applySwap | cancelSwap` RPCs with opaque per-session `stagingId` so a stale page can't accidentally commit.

**Multi-tab.** Per AC-11. `installOpfsSAHPoolVfs()` throws `NoModificationAllowedError` on conflict; worker tags as `code='OWNERSHIP_CONFLICT'` so the workspace can render a specific "another tab/window holds the data layer" panel rather than the misleading "your browser doesn't support this."

**Reset Everything.** A nuclear `wipeAll` RPC: closes both DBs, tears down SAH-pool VFS via `removeVfs()`, iterates OPFS root and removes every entry. Caller reloads after.

**Diagnostics.** `getOpfsInventory`, `getTrace`, `getVersions`, `getSharedDbMeta` — all read-only, used by ?diag and bug reports.

**fellows_local_db specifics:** worker file at `app/static/vendor/sqlite-worker.js`; `WORKER_RPC_VERSION=2`; `RELATIONSHIPS_SCHEMA_VERSION=1`. The legacy main-thread OPFS paths still exist in `app.js` but are unused post-Phase-1.

## Workspace (`pna-workspace`)

**Contract.** Renders shared + private data. Implements the debug contract. Provides:

- Boot persona function (the "should we boot directly into the workspace, or show the distribution gate?" decision)
- Three-tier dataProvider with mid-boot hot-swap on auth failure
- Hash-based routing (or equivalent) with per-route focus modes
- Render path for orphaned private references (per AC-10 follow-through)
- `escapeHtml()` discipline for all user-supplied data
- Capability-failure panel (`renderLocalDataUnavailablePanel(feature)` style)
- Local-search fallback when network is offline (over the cached shared data)

**Data providers (three tiers).** A PNA workspace consults a provider abstraction with three implementations:

- **worker** (happy path) — RPC to Storage; full OPFS-backed reads + writes
- **api+idb** (auth-failure fallback) — shared-data reads via the distribution channel's API or local IDB cache; private-data writes refuse with `localDataUnavailable` so the unsupported panel renders
- **api** (deepest fallback, dev) — same as api+idb but no IDB

The workspace hot-swaps mid-boot on a 401/403 from the shared-data fetch, so a stale session never locks the user out of cached data (AC-5). The active provider is exposed at `window.__dataProvider` for tests and diagnostics.

**Persistence-marker contract.** Exactly one localStorage key is preserved across the workspace's "Clear App Cache" affordance: the "this origin authenticated once" marker. All other localStorage keys are cleared. (Drafts in localStorage are explicitly unsaved-by-definition; durable user state lives in the Private DB.)

**Force-gate.** Per AC-6.

**URL-just-works (browser-mode-acts-as-app).** When the user previously authenticated this origin (the marker is set) and they're visiting in a browser tab (not standalone PWA), boot directly into the workspace.

**fellows_local_db specifics:** vanilla-JS SPA, single 9400-line IIFE, hash routing with seven routes (`#/`, `#/about`, `#/fellow/<slug>`, `#/groups`, `#/groups/<id>`, `#/groups/<id>/directory`, `#/edit/<id>`, `#/settings`). Filter state persisted in URL query suffix.

## Communications (`pna-comms`)

**Contract.** A pluggable transport layer. Each transport exposes an interface:

```
canHandle(action) → bool
launch(action, payload) → Promise<launchResult>
descriptor() → { id, name, secureLevel?, … }
```

Where `action` is one of (initial set): `email_one`, `email_group_cc`, `email_group_bcc`, `direct_message_one`, `share_link_one`, `share_link_group`. The workspace offers whichever transports the running PNA is configured with; the user picks per outreach (per AC-16).

**Privacy invariant — content secrecy (per AC-18).** A transport is acceptable for inclusion iff its mechanism itself cannot read message contents. mailto: passes — the mechanism hands off to whichever client the user has configured; downstream provider behavior (Gmail, Outlook, etc.) is outside the toolkit's enforcement. Signal-class protocols pass — encryption is part of the protocol. Centralized message-broker SaaS that decodes payloads as part of operating (Slack, Discord) does not pass.

**User-visible payload before send (per AC-19).** Communications launched by the workspace show the user the full payload — recipients, body, any merged data from Shared or Private DB — before the transport is invoked. The user can edit or cancel. Even bulk operations (email this group of 50) show a composed view first. This is how the data-transport matching gets resolved in v0.1: the user sees what's going where and either approves it or doesn't. (Per-database transport requirements as an explicit declarative mechanism are deferred — see § Scope.)

**Distinction from distribution-mechanism transports.** Communications transports are what the workspace launches when the user wants to reach out to a contact. They are *distinct from* the Distribution component's auth-link transport (e.g., Postmark sending a magic link in fellows_local_db). Distribution-mechanism transports are governed by the Distribution slot's contracts, not AC-18 — choosing a magic-link distribution flavor implies accepting whatever the magic-link delivery service does within its scope.

**Sharing-scope as future consideration.** The Shared schema in v0.1 has no per-record sharing-scope metadata (who already has a copy: just the fellowship, just Google, the world, etc.). Future versions may add this so the workspace can warn before sending data through a transport whose effective scope would exceed the data's existing scope. Out of scope for v0.1; noted here so the Shared schema isn't designed in a way that precludes adding it.

**fellows_local_db specifics:** `mailto:` only. Signal planned next.

## Distribution (`pna-dist`) — optional

A PNA *may or may not* distribute. A purely-local instance (one user, locally built, no shipping to others) has no Distribution component. When present, Distribution provides:

**Install path.** Some way to deliver a verified bundle to an authorized user's device. Contract: results in a local install of Workspace + Storage + an initial Shared DB, with a session that authorizes future fetches.

**Update path.** Workspace + worker file updates via SW + cache versioning (when the implementation is a PWA). Shared-DB updates are explicitly user-driven (per AC-10), not automatic.

**Auth contract (when allowlisted).**

- `GET /api/auth/status` — never gated; returns `{authEnabled, authenticated, hasSessionCookie, installRecentlyAllowed, build, buildGitSha}`
- `POST /api/send-unlock` — anti-enum, always 200 `{sent:true}`; rate-limited per email-hash
- `POST /api/verify-token` — 200 + Set-Cookie on success; 401 with distinct `expired`/`invalid` error strings otherwise
- `POST /api/logout` — idempotent, always 200, doesn't require valid session
- Server-side: HMAC-signed session cookie; v-prefixed format so prior versions reject cleanly post-deploy
- Token re-consume grace window (~60s) to defend against bfcache, iOS back-button, email-side link scanners

**No per-user RW endpoints** (per AC-2). The distribution server gates shared-data reads behind a session; it has no per-user state to defend.

**Distribution server hardening (when present).**

- TLS terminator on :443 forwarding to a 127.0.0.1 origin
- COOP/COEP headers per AC-13
- 16 KB POST cap
- Per-IP rate limits matching the auth path
- Long-cache for immutable assets, no-cache for HTML/JS/CSS/SW + worker file + manifest + build-meta.json
- Status-aware caching: 4xx/5xx never long-cached
- Sanitized error sink per Debug contract

**PWA-specific gotchas (when distribution medium is a PWA).**

- Manifest stays minimal: `id`, `start_url`, `scope` all `=/`; three icons (`any`, `any`, `maskable`); **no `related_applications`** (Android WebAPK pipeline foot-gun); **no `share_target` with `method: "POST"`** (Samsung/Chromium foot-gun)
- SW network-first for HTML/JS/CSS/SW *and* the worker file (RPC version is tightly coupled to app.js); cache-first for vendored sqlite3.js / sqlite3.wasm
- Profile/asset cache is a separate cache name from app shell so shell bumps don't evict tens of MB of immutable assets; asset URLs stay bare (no `?v=` cache-bust) because per-record assets are immutable
- The Shared DB URL is explicitly bypassed in the SW fetch handler (per AC-14)

**fellows_local_db specifics:** never-SaaS PWA + Postmark magic-link allowlist; Caddy on Ubuntu droplet; `TOKEN_TTL = 30 min`, `INSTALL_WINDOW = 30 min`, `SESSION_MAX_AGE = 7 days`; v2 cookie format. Decision tree (browser-mode vs PWA-mode), six-step ordered match, always-reachable `?gate=1`. Specifics in `email_gate.md` (post-rewrite, this becomes the Distribution specialization annex).

---

# Part 2 — Source map (verification)

For each existing doc, a compact list of load-bearing claims with classifications. Use this to verify Part 1 didn't drop anything important.

## docs/Architecture.md

| Section | Claim | Class | Maps to |
|---|---|---|---|
| Design constraint | "single-user and local-only by design… must never become a SaaS" | `pna-cat` | AC-2 |
| Design constraint | server contact bounded to install + update | `pna-cat` | AC-2 |
| Design constraint | no per-user resources on the server | `pna-cat` | AC-2 |
| Design constraint | stale-session must not lock users out of cached data | `pna-cat` | AC-5 |
| Design constraint | ruled-out features list (cross-device sync, share group, admin console, etc.) | `pna-cat` | non-goals |
| Tech Stack | Python stdlib `http.server` | `fellows-dist` | impl choice |
| Tech Stack | SQLite3 with FTS5 | `pna-storage` (sqlite) + `fellows-workspace` (FTS5 columns) | shared schema allows but doesn't require FTS5 |
| Tech Stack | Vanilla JS SPA, no build step | `fellows-workspace` | impl choice |
| Tech Stack | pytest + Playwright | `fellows-cat` | testing |
| Data Flow | ETL → fellows.db with 17 cols + extra_json | `fellows-ingest` | impl choice |
| Data Flow | extra_json overflow merged at API time | `pna-shared` | extension mechanism is generic |
| Runtime | new SQLite connection per request, no pool | `fellows-cat` | server detail |
| Runtime | HTTP API table | `fellows-cat` | specific routes |
| Runtime | `/api/auth/status` shape | `pna-dist` | Distribution auth contract |
| Runtime | `/api/client-errors` privacy-bounded | `pna-debug` | sink |
| Runtime | `/api/groups` and `/api/settings` retired (Phase 1) | `fellows-storage` | choice that all this lives in OPFS now; phase numbering is `STALE` for spec |
| Persistence | private.db separate from shared.db | `pna-cat` | AC-1 |
| Persistence | ATTACH ?mode=ro for cross-DB joins | `pna-shared` | read-only enforcement |
| Persistence | private.db durable across app updates and Clear App Cache | `pna-private` | durability |
| Persistence | shared.db re-imported on user request when SHA differs | `pna-cat` | AC-10 |
| Persistence | pre-swap impact preview lists affected members | `pna-cat` | AC-10 |
| Persistence | OPFS in both standalone PWA and browser-tab modes | `pna-storage` | substrate |
| Persistence | unsupported-browser panel via `renderLocalDataUnavailablePanel()` | `pna-workspace` | capability-failure panel |
| Worker-owned OPFS | single dedicated worker owns every OPFS handle | `pna-cat` | AC-3 |
| Worker-owned OPFS | RPC `{id, op, args}` ↔ `{id, ok, result\|error}` | `pna-storage` | protocol |
| Worker-owned OPFS | worker handles both RW and RO databases | `pna-storage` | substrate |
| Worker-owned OPFS | no other context calls `getDirectory` / `createSyncAccessHandle` | `pna-cat` | AC-3 |
| Worker-owned OPFS | rationale: Safari etc. strip createSyncAccessHandle from main-thread | `pna-cat` | AC-12 |
| Worker-owned OPFS | init is network-free; fetch is page-driven | `pna-storage` | install-only by design |
| Worker-owned OPFS | `WORKER_RPC_VERSION` + schema version gates | `pna-cat` | AC-4 |
| Worker-owned OPFS | mismatch refuses mutating RPCs; reads still work | `pna-cat` | AC-4 |
| Worker-owned OPFS | build label not consulted for the gate | `pna-cat` | AC-4 |
| Worker-owned OPFS | ATTACH happens once per init in worker (not per request) | `pna-storage` | substrate; doc wording is `STALE` (see Bug 3) |
| Worker-owned OPFS | capability detection in worker | `pna-cat` | AC-12 |
| Non-goals | SW never owns SQLite | `pna-cat` | AC-14 |
| Non-goals | no parallel main-thread OPFS | `pna-cat` | AC-3 |
| Non-goals | no server-side per-user state | `pna-cat` | AC-2 |
| Non-goals | no silent cross-device sync substrate | `pna-cat` | non-goal |
| Non-goals | no multi-tab concurrent ownership | `pna-cat` | AC-11 |
| Two-Phase Load | list-then-full | `pna-workspace` | lazy-load pattern |
| Two-Phase Load | fall back to single-record GET if user clicks before phase 2 | `fellows-workspace` | pre-Phase-1 path |
| Frontend Routing | hash-based, no router lib | `fellows-workspace` | shell choice |
| Frontend Routing | route table (7 routes) | `fellows-workspace` | specific routes |
| Manifest gotchas | `id, start_url, scope` all `=/` | `pna-dist` | PWA-specific contract |
| Manifest gotchas | don't add `related_applications` (Android WebAPK foot-gun) | `pna-dist` | runtime fact |
| Manifest gotchas | don't use `share_target` with `method:"POST"` | `pna-dist` | runtime fact |
| Database Schema | fellows table 17 cols + extra_json | `fellows-ingest` | impl schema |
| Database Schema | fellows_fts virtual table | `fellows-storage`+`fellows-workspace` | impl |
| Database Schema | private.db schema (5 tables) | `pna-private` | promote core; rename `fellow_record_id`→`record_id` |
| Database Schema | PRAGMA user_version for migrations | `pna-private` | versioning |
| Database Schema | private.db gitignored, per-user, durable | `pna-cat` | AC-1 |

## docs/email_gate.md

| Section | Claim | Class | Maps to |
|---|---|---|---|
| Goals | default view is the email gate | `fellows-dist` | impl-specific UI choice |
| Goals | install landing exists only inside a bounded window | `fellows-dist` | PWA-install timing |
| Goals | dev must always reach the gate in one click | `pna-cat` | AC-6 |
| Definitions | session cookie HttpOnly, HMAC-signed, v2 format | `fellows-dist` | impl |
| Definitions | TOKEN_TTL = 30 min | `fellows-dist` | tunable |
| Definitions | INSTALL_WINDOW = 30 min from issue | `fellows-dist` | tunable; the *anchor* is generic |
| Definitions | SESSION_MAX_AGE = 7 days | `fellows-dist` | tunable |
| Invariants | email gate is the default | `fellows-dist` | impl |
| Invariants | install landing never repeats | `fellows-dist` | impl |
| Invariants | expired vs invalid links explicit | `fellows-dist` | UX |
| Invariants | session cookie TTL decoupled from install window | `pna-dist` | generic pattern |
| Invariants | dev escape hatch always reachable (`?gate=1`) | `pna-cat` | AC-6 |
| Invariants | unsupported browsers told so on click, not eagerly | `pna-workspace` | UX rule |
| Invariants | URL-just-works for returning visitors | `pna-cat` | persistence-marker contract |
| Invariants | stale session does not lock users out of cached data | `pna-cat` | AC-5 |
| Browser-mode decision tree | six-step ordered match | `fellows-dist` | impl-specific tree |
| `fellows_authenticated_once` marker | preserved across `clearAllAppData` | `pna-cat` | persistence-marker contract |
| Endpoints | `/api/auth/status` | `pna-dist` | contract |
| Endpoints | `/api/send-unlock` anti-enum 200 | `pna-dist` | AC-8 |
| Endpoints | `/api/verify-token` 401 with `expired`/`invalid` | `fellows-dist` | distinct strings is impl |
| Endpoints | `/api/logout` idempotent | `pna-dist` | contract |
| Endpoints | `/api/client-errors` 204 / 16KB / sanitized / rate-limited | `pna-debug` | sink contract |
| Client error reporting | privacy boundary is server-side | `pna-debug` | invariant |
| Client error reporting | sanitization rules | `pna-debug` | sanitizer contract |
| Client error reporting | `kind=` enum allowlist | `pna-debug` | analytics-via-sink |
| Client error reporting | `lastSubmitHashPrefix` correlation handle | `pna-debug` | mechanism |
| Client error reporting | `client_ip_prefix` first-12-hex of sha256 | `pna-debug` | invariant: never log raw IP |
| Client error reporting | per-IP rate limit | `pna-debug` | AC-8 |
| `kind=install` events | install-funnel telemetry | `pna-debug` | analytics example |
| `kind=worker` events | spawn / init outcomes | `pna-debug` | analytics example |
| Cookie format (v2) | payload + HMAC | `fellows-dist` | impl |
| Cookie format (v2) | v1 rejected on sight | `fellows-dist` | impl |
| Token grace | 60-sec re-consume window | `fellows-dist` | tunable; rationale (defense against bfcache / scanners) is generic |
| Security notes | `?gate=1` doesn't bypass auth, only the UI | `pna-cat` | AC-6 |

## docs/persistence_and_upgrades.md

| Section | Claim | Class | Maps to |
|---|---|---|---|
| Storage layers table | Cache API names; IDB; OPFS; localStorage; cookie | `pna-storage` (the layers exist) + `fellows-workspace` (specific keys) | substrate |
| Storage layers | one localStorage key preserved across Clear App Cache | `pna-cat` | persistence-marker contract |
| Storage layers | `last_seen_sha.txt` retired | `STALE` | document as "no longer applicable to new instances" |
| Standard app update flow | SW polls /build-meta.json, shows banner, user reloads | `pna-dist` | PWA update mechanism |
| Standard app update flow | what survives the reload | `pna-cat` | AC-1, AC-9, AC-10 |
| Directory data update flow | About page → Check for updates → preview → confirm | `pna-cat` | AC-10 |
| Directory data update flow | orphan members rendering | `pna-workspace` | post-swap UX |
| Directory data update flow | one-shot soft scan | `fellows-cat` | one-time migration |
| Auto-backup | snapshot to bak.<ISO>, rotate keep newest 5 | `pna-cat` | AC-9 |
| Auto-backup | 1-hour debounce, per-boot trigger keyed to user-edit cadence | `pna-cat` | AC-9 |
| Auto-backup | backups at OPFS root, outside SAH-pool | `pna-storage` | substrate detail |
| Restore | from a file or auto-backup | `pna-workspace` + `pna-storage` | restore contract |
| Restore | validate via PRAGMA quick_check + table check | `pna-storage` | safety |
| Restore | snapshot pre-restore state | `pna-cat` | AC-9 |
| Restore | bootstrapRelationshipsSchema after restore | `pna-private` | idempotent migration |

## docs/browser_support.md

| Section | Claim | Class | Maps to |
|---|---|---|---|
| Stance | local-first | `pna-cat` | goals |
| Stance | capability-detect, don't UA-sniff for gating | `pna-cat` | AC-12 |
| Stance | be specific in messaging | `pna-debug` | UX rule |
| Stance | failure should never look like a bug | `pna-workspace` | UX |
| Required versions | `OPFS_MIN_VERSIONS` table | `pna-storage` | substrate facts; tunable |
| Required versions | iOS callout (all browsers use WebKit) | `pna-cat` | runtime fact |
| Detection path | worker-init reports `opfsCapable` | `pna-storage` | handshake field |
| Adding new local-data feature | checklist | `pna-workspace` | shell convention |
| What we deliberately don't do | no server-side storage of user-authored data | `pna-cat` | AC-2 |
| What we deliberately don't do | no browser blocklist | `pna-cat` | AC-12 |
| What we deliberately don't do | no silent degradation for blocked features | `pna-workspace` | UX |

## docs/data_provenance.md

| Section | Claim | Class | Maps to |
|---|---|---|---|
| Source tables | Knack REST API extraction is canonical | `fellows-ingest` | source choice |
| Source tables | known-good backup DB as source-of-last-resort | `fellows-ingest` | recovery |
| Image fallback | app dir → final_fellows_set; .jpg→.png; alpha-only fuzzy match | `fellows-ingest` | impl detail |
| Column-by-column provenance | full table | `fellows-ingest` | source mapping |
| Backup workflow | data-backup, data-restore commands | `fellows-cat` | operator workflow |
| Recovery paths | three (snapshot, reference DB, full ETL) | `fellows-cat` | operator workflow |
| Historical note | .bak.JSON demo subset | `DROP` | historical anecdote |

## docs/DevOps.md

| Section | Claim | Class | Maps to |
|---|---|---|---|
| Architecture at a glance | one droplet, Caddy on :443, Python on 127.0.0.1:8765 | `fellows-dist` | impl |
| Architecture at a glance | TLS terminator + 127.0.0.1 origin pattern | `pna-dist` | hardening |
| Unix identities | rsb (operator) + fellows (daemon) | `fellows-cat` | operator |
| Filesystem layout | /opt/fellows/, /etc/fellows/, mode 2775 | `fellows-cat` | operator |
| systemd hardening | full directive list | `fellows-cat` | operator |
| Network and firewall | ssh + 80 + 443 inbound | `fellows-cat` | operator |
| Routine operations | `just ship` | `fellows-cat` | operator |
| Required env vars | session secret + Postmark token + mail from + public origin | `fellows-dist` | impl needs |
| Debugging | journald event schema | `pna-debug` | structured log conventions |
| **Missing entirely** | COOP/COEP requirement | `MISSING` | AC-13 (Bug 1) |

## docs/README.md

Mostly mirrors Architecture.md + DevOps.md + email_gate.md. Specific items worth noting:

| Section | Claim | Class | Maps to |
|---|---|---|---|
| Design Stance | local-only, not SaaS | `pna-cat` | duplicate |
| Testing The Latest Code | the trap is stale state — SW + OPFS + IDB + cookie + localStorage marker all persist | `pna-storage` | substrate behavior |
| Testing The Latest Code | DevTools "Clear site data" misses several layers | `fellows-cat` | testing convention |
| Phase numbering | "Phase 4 magic-link gate" | `STALE` for spec; phases are project history |

## CLAUDE.md

| Item | Class | Maps to |
|---|---|---|
| No frameworks | `fellows-cat` | impl posture |
| No frontend build tools | `fellows-cat` | impl posture |
| No new pip dependencies | `fellows-cat` | impl posture |
| No authentication (in dev) | `fellows-dist` | dev choice |
| Port 8765 fixed | `fellows-cat` | dev port |
| `escapeHtml()` for all user data | `pna-workspace` | XSS invariant |
| Parameterized `?` placeholders for SQL | `pna-cat` | SQL-injection invariant |
| Image path traversal validation | `pna-cat` | file access invariant |
| OPFS access only via dedicated worker | `pna-cat` | AC-3 |
| Two-DB architecture | `pna-cat` | AC-1 |

---

# Part 3 — Bugs, missing items, open questions

## Bugs in existing docs (fix in place before split)

**Bug 1 — FIXED 2026-05-08.** COOP/COEP requirement was undocumented anywhere; Architecture.md § Tech Stack now has a "Cross-origin isolation" bullet, and DevOps.md § Architecture at a glance now has a paragraph after the diagram explaining that Caddy/proxies must preserve the headers and what the silent-breakage symptom looks like.

**Bug 2 — FIXED 2026-05-08.** Three-tier dataProvider with mid-boot hot-swap is now documented in a new "Workspace data providers (three tiers, mid-boot hot-swap)" section in Architecture.md, between "Non-goals (worker-owned OPFS)" and "Two-Phase Load." Names the three tiers, the hot-swap trigger (worker `ensureFellowsDb` 401/403), and the test/diagnostics seam at `window.__dataProvider`.

**Bug 3 — FIXED 2026-05-08.** ATTACH wording normalized in both Architecture.md and persistence_and_upgrades.md. Both now explicitly say "attached once per worker `init` — *not* per request" and call out the pre-Phase-1 per-request behavior as retired. Adjacent stale wording in persistence_and_upgrades.md ("re-imported on every boot") fixed at the same time — replaced with "replaceable — its bytes derive from a buildable source and the user can opt into a refresh from the About page."

**Bug 4 — FIXED 2026-05-08.** Boot watchdog + named bootMarks + slow-boot persistence now documented in a new "Boot orchestration (named marks + watchdog + slow-boot persistence)" section in Architecture.md, immediately after the Workspace data providers section. Names the eight phase marks, the 20s watchdog, the recovery panel, the slow-boot localStorage key (`fellows_last_slow_boot`), and the e2e seams (`window.__bootMarks`, `window.__bootDebugLines`).

**Bug 5: Build badge / ?diag panel / bug-report dialog aren't articulated as architectural commitments.** They exist in code but `Architecture.md` doesn't frame them as the self-service field-debug substrate (AC-7). They look like UI affordances, not architectural choices.
*Fix:* lift to the Debug contract slot in the new spec; reference from `Architecture.md`.

**Bug 6: Multi-tab `OWNERSHIP_CONFLICT` detection is in code but not in `Architecture.md`.** Worker tags `installOpfsSAHPoolVfs()` failures so the page can render a specific "another tab" panel. `plans/multi_tab_ownership_takeover.md` covers the *future* coordinated takeover, but the *current* refused-with-distinct-message behavior isn't documented as architecture.
*Fix:* add a paragraph to `Architecture.md § Worker-owned OPFS § Non-goals`.

**Bug 7: Hash routes table doesn't note URL filter persistence.** The directory hash carries query-suffix params (`#/?cohort=2020`) read on every `route()` call by `applyFiltersToHash` / `readFiltersFromHash`. Worth one line in the routes table.

**Bug 8: Phase numbering ("Phase 1", "Phase 4", "Phase 6 retires IndexedDB") is project history, not spec.** Several docs reference phases without explaining them. For the spec rewrite, drop phase numbers from `PNA_Spec.md`; preserve the staging history in `plans/local_first_worker_architecture.md`.

**Bug 9: `window.ai` natural-language search is undocumented.** It's a real feature behind a capability gate. Fellows-specific (lands in `Architecture.md` § Workspace specialization).

**Bug 10: `DevOps.md`'s ProtectSystem note suggests `?mode=ro` is the next hardening step**, but neither server actually opens the Shared DB with `?mode=ro` yet. The note describes a *potential* improvement, not the current state. Worth either making the change (flip both servers to read-only open) or rephrasing as a backlog item.

**Bug 11: README's "Phase 4 magic-link gate" reference** is a minor stale note; tidy along with Bug 8.

## Items missing from existing docs (need to add to PNA_Spec)

**M1: Build label substitution as a uniform interface.** Every component-shipping-text-files participates in build-label substitution at build *and* serve time. fellows_local_db substitutes `__FELLOWS_UI_DIAG__` and `__CACHE_VERSION__` in `app.js`, `sw.js`, `vendor/sqlite-worker.js`. Generalize to: "Every component implementing the Debug contract supports placeholder substitution at both build and serve time."

**M2: Worker init handshake field list as a typed contract.** Currently described in prose. A spec needs the explicit shape (see Storage slot synthesis above).

**M3: Per-record asset URL convention.** `/images/<slug>.{jpg,png}` with alpha-only fuzzy fallback is fellows-specific, but the *idea* of per-record asset URLs separate from the database (cacheable, immutable, slug-keyed) generalizes to the Shared schema interface.

**M4: `PRAGMA foreign_keys = ON` per connection.** sqlite default is OFF; without it `ON DELETE CASCADE` is silently inert. Generic invariant for the Private schema.

**M5: Reset Everything via worker `wipeAll` RPC.** Documented in `persistence_and_upgrades.md` as a UX flow but the *RPC contract* (close DBs → removeVfs → iterate OPFS root) isn't formalized. Belongs in the Storage slot.

**M6: `?gate=1` precedes display-mode short-circuit.** fellows-specific URL, but the pattern (forced-gate URL beats display-mode short-circuit in the boot persona function) is generic.

**M7: Persisted-storage best-effort.** `navigator.storage.persist()` once per install, result in `window.__persistStorageState`. Generic; lives in Storage or Workspace slot.

**M8: Tests-as-spec via `window.__dataProvider`.** Phase-1 tests drive the worker via `page.evaluate(() => window.__dataProvider.createGroup(...))`. The seam (page exposes the active provider on a stable global; tests use it instead of HTTP) is part of the Debug contract — testability requirement.

## Resolved (formerly open) questions

These were open in the previous version of this doc; resolved in the 2026-05-08 working session:

- **`record_id` naming.** Spec uses `record_id` (no `fellow_` prefix) in the Private schema. fellows_local_db's specialization keeps `fellow_record_id` for in-app ergonomics.
- **`relationships.db` vs `private.db` naming.** Spec uses `private.db`. fellows_local_db keeps `relationships.db` as its specialization filename.
- **Phase numbering.** Drop from spec; preserve in `plans/`.
- **Public vs shared terminology.** Settled on *shared / private* (not *public / private*). "Shared" captures "an external system has a copy"; "public" colloquially means "anyone can see," which isn't what we mean.
- **Spec format and AI-checkability.** Landscape passed in `docs/_pna_spec_format_landscape.md` (2026-05-08). Recommendation: markdown prose for `PNA_Spec.md` + machine-readable typed contracts in `docs/spec/contracts/` (JSON Schema for RPC + handshake, OpenAPI fragment for Distribution auth, SQL DDL for the two schemas, TypeScript declaration for the Communications transport interface) + `llms.txt` at repo root for AI discovery + reference designs as evidence (each in its own repo with its own `Architecture.md` declaring spec version + slot-fill choices + adjectives). Formal verification deferred to a future spec version.
- **Communications transport acceptability rule.** Settled on **content secrecy** as the primary criterion (AC-18): a transport is acceptable iff its mechanism itself cannot read message contents. Contact-graph retention dropped from the rule (too hard to enforce uniformly across protocols; varies by user threat model — P2P apps may inherently expose some graph, while message-broker SaaS retain it as a feature). Distinction made between Communications transports (governed by AC-18) and Distribution-mechanism transports (governed by the Distribution slot's contracts; Postmark for magic links is the latter, not the former). Sharing-scope metadata on the Shared DB noted as a future-version consideration so the v0.1 schema doesn't preclude it.
- **Communications-history table in Private schema.** Added to the canonical Private schema as `record_comms_history`. **Disabled by default**; user opts in via `settings['comms_history_enabled']`; workspace honors the flag and writes nothing when disabled. User has full read / edit / delete control. Lives in the Private DB and is protected by AC-1 (never leaves the device).
- **Per-workspace settings partitioning.** `settings` table gets a composite primary key `(workspace_id, key)`. Single-workspace PNAs use empty-string `workspace_id` (default); multi-workspace PNAs (per the "one origin, many workspaces" decision) use real workspace IDs. Resolves the future-multi-workspace migration concern up front.

## Open questions for @richbodo

All v0.1 open questions resolved as of 2026-05-08 (see Resolved section above). Items deferred to future spec versions are listed in § Scope and versioning. New open questions will surface during the component decomposition pass and the spec drafting; this section gets repopulated then.

---

# Part 4 — Component decomposition (sub-contracts per slot)

Each slot's contract is composed of named sub-contracts. The decomposition gives `PNA_Spec.md` clear language for each piece so an AI building or rewriting a PNA can target each sub-contract individually. None of the v0.1 slots split into multiple top-level slots — but every slot has multiple distinct contracts inside it, and several cross-slot relationships need explicit naming.

Naming convention: two-letter prefix per slot (`WS-`, `ST-`, `IN-`, `CO-`, `DI-`, `SH-`, `PR-`, `DB-`) + dash + monotonic integer. New sub-contracts get the next integer; numbers don't get reused.

## Workspace (`WS-`)

- **WS-1: Boot persona.** Function that decides "directory mode" vs "distribution gate" given standalone-display, persistence marker, and force-gate URL. Drives the entire boot flow.
- **WS-2: Routing.** Hash-based or equivalent; per-route focus modes; URL-shareable filter state where applicable.
- **WS-3: Render contracts.** Per-route contracts on what each view shows. Includes orphan-row rendering after Shared DB updates.
- **WS-4: Data provider abstraction.** Three-tier provider (worker / api+idb / api) with mid-boot hot-swap on auth failure (per AC-5). Single source of truth at `window.__dataProvider`.
- **WS-5: Boot orchestration.** Named `bootMarks` at meaningful transitions; watchdog timeout surfaces a recovery panel naming the last-completed mark; slow-boot persistence to localStorage across sessions.
- **WS-6: Capability-failure panel.** `renderLocalDataUnavailablePanel(feature)`-style for OPFS / version-skew / multi-tab-conflict failures.
- **WS-7: Persistence-marker.** Exactly one localStorage key preserved across Clear App Cache (the "this origin authenticated once" marker; spelled `fellows_authenticated_once` in fellows_local_db).
- **WS-8: Local-search fallback.** Search over cached Shared DB when network is offline.
- **WS-9: Sanitization discipline.** `escapeHtml` for all user-supplied data; parameterized `?` placeholders for all SQL; image path traversal validation.
- **WS-10: User-visible payload before send (AC-19).** Workspace shows full composition before any communication launches.

Cross-slot: WS-4 sits at the boundary with Storage (the `worker` tier is RPC into ST-3); WS-5 implements the boot side of DB-3.

## Storage (`ST-`)

- **ST-1: Substrate.** Single dedicated worker; OPFS-SAH-Pool VFS; sqlite-wasm runtime. Only context that calls `navigator.storage.getDirectory` or opens a `FileSystemSyncAccessHandle` (per AC-3).
- **ST-2: Init handshake.** First RPC must be `op='init'`. Returns `{workerRpcVersion, schemaVersion, buildLabel, opfsCapable, hasSharedDb, hasPrivateDb, poolFiles, trace}`. Capability detection happens here (per AC-12).
- **ST-3: RPC protocol.** `{id, op, args}` ↔ `{id, ok, result|error}`. Fan-in dispatch via sequence-numbered pending Map. `worker.onerror` rejects all pending RPCs so callers can fall back instead of hanging.
- **ST-4: Two-database management.** Private DB (RW), Shared DB (RO). Cross-DB joins via `ATTACH ?mode=ro`, attached once per init in the worker.
- **ST-5: Schema bootstrap.** `CREATE IF NOT EXISTS` for both schemas. `PRAGMA foreign_keys=ON` per connection. `PRAGMA user_version` set to schema version. Idempotent so older backups gain newer tables on restore.
- **ST-6: Auto-backup.** Per-boot debounced snapshots of Private DB to OPFS root (outside SAH-pool dir, so survives sqlite-wasm operations). Rotation by sorted ISO filename. Per AC-9.
- **ST-7: Restore.** From a user-supplied file or a recent auto-backup. Validates via `PRAGMA quick_check` + schema check. Snapshots pre-restore state to the same rotation. Atomic swap.
- **ST-8: Opt-in update flow.** `compareSha → previewSwap → applySwap | cancelSwap`. Opaque per-session `stagingId` so a stale page can't accidentally commit. Affected-member preview computed from joined Private DB references. Per AC-10.
- **ST-9: Multi-tab detection.** `OWNERSHIP_CONFLICT` tagged on `installOpfsSAHPoolVfs()` failure so WS-6 can render a specific multi-tab panel (per AC-11).
- **ST-10: Reset Everything.** `wipeAll` RPC: close both DBs, `removeVfs()`, iterate OPFS root and remove every entry. Caller reloads after.
- **ST-11: Diagnostics.** `getOpfsInventory`, `getTrace`, `getVersions`, `getSharedDbMeta`. Read-only; pure reads, no fetches.

Cross-slot: ST-2/3 are the contract WS-4 calls; ST-7's schema re-bootstrap respects PR-3.

## Ingestion (`IN-`)

- **IN-1: Source adapter.** Produces bytes conforming to the Shared schema (SH-1 through SH-3). App-specific.
- **IN-2: Output validation.** `PRAGMA quick_check` passes; primary record table has ≥1 row (zero-row guard prevents catastrophic orphaning of every Private DB reference).
- **IN-3: Sourced provenance (AC-17).** Every record traces to a specific external source the user has configured.
- **IN-4: Re-ingestion mechanics.** Atomic stage → validate → swap. Non-destructive of Private DB references; orphan preview required (per AC-10, surfaced via ST-8 + WS-3).

Cross-slot: IN-4 hands off to ST-8 for the actual stage/swap; SH-5 is the Shared-side view of the same transition.

## Communications (`CO-`)

- **CO-1: Transport interface.** `canHandle(action) → bool`, `launch(action, payload) → Promise<launchResult>`, `descriptor() → {id, name, secureLevel?, …}`.
- **CO-2: Action set.** Fixed enum: `email_one`, `email_group_cc`, `email_group_bcc`, `direct_message_one`, `share_link_one`, `share_link_group`. Extensible — new actions can be added with toolkit version bumps.
- **CO-3: Transport eligibility (AC-18).** Mechanism cannot read message contents.
- **CO-4: User-driven selection (AC-16).** Workspace surfaces multiple transports; user picks per outreach.
- **CO-5: User-visible payload (AC-19).** Workspace shows full payload (recipients, body, merged data) before launch.
- **CO-6: Distinction from distribution-mechanism transports.** A distribution flavor's auth-link transport (e.g., Postmark in fellows_local_db's magic-link distribution) is governed by Distribution slot contracts, not CO-3.

Cross-slot: CO-4 is observable from WS (the shell renders the picker); CO-5 is the same contract as WS-10, dual-listed because both slots co-implement.

## Distribution (`DI-`) — optional

- **DI-1: Install path.** Bundle delivery + verified initial Shared DB + session bootstrap.
- **DI-2: Update path.** Shell + worker file via SW + cache versioning. Shared DB updates user-driven (per AC-10), not automatic.
- **DI-3: Auth contract.** `GET /api/auth/status`, `POST /api/send-unlock`, `POST /api/verify-token`, `POST /api/logout`. Session cookie HMAC-signed, version-prefixed (so prior versions reject cleanly post-deploy).
- **DI-4: Anti-enum + rate limit (AC-8).** Always-200 / 204 on send-unlock and client-errors. Per-IP and per-email-hash rate limits. Distinct expired/invalid error strings on verify-token.
- **DI-5: Server hardening.** TLS terminator on :443 → 127.0.0.1 origin. COOP/COEP (AC-13). 16KB POST cap. No per-user RW endpoints (AC-2). Status-aware caching (4xx/5xx never long-cached).
- **DI-6: PWA-specific gotchas (when distribution medium is a PWA).** Minimal manifest, no `related_applications`, no `share_target` POST. SW network-first for HTML/JS/CSS/SW + worker file; cache-first for vendored runtime. Separate asset cache. Shared DB URL bypassed in SW fetch (AC-14).

Cross-slot: DI-2's update path triggers WS's "New version available — Reload" banner; DI-3 outcomes feed WS-1's persona decision.

## Shared schema (`SH-`)

- **SH-1: Primary record table.** `record_id` PK, `slug` UNIQUE, `name`, app-defined display columns, `extra_json TEXT` overflow.
- **SH-2: Optional FTS5 virtual table.** Indexes whichever columns the workspace wants searchable.
- **SH-3: Optional per-record asset URL convention.** `/images/<slug>.{jpg,png}` style; cacheable, immutable, slug-keyed.
- **SH-4: Read-only enforcement.** ATTACH `?mode=ro` for cross-DB joins; stray writes raise `OperationalError`.
- **SH-5: Atomic re-import semantics with orphan preview (AC-10).** Stage → validate → swap; pre-swap impact preview lists Private DB references that would be orphaned.
- **SH-6: Sourced-provenance per record (AC-17).** Multi-source PNAs add a `source` column; single-source may omit.

Cross-slot: SH-5 is implemented by ST-8.

## Private schema (`PR-`)

- **PR-1: Core tables.** `groups`, `group_members`, `record_tags`, `record_notes`, `settings(workspace_id, key, value)` with composite PK.
- **PR-2: Opt-in tables.** `record_comms_history`. **Disabled by default** (`settings['comms_history_enabled']='1'` to enable). User has full read/edit/delete control.
- **PR-3: Schema metadata.** `PRAGMA user_version`; `PRAGMA foreign_keys=ON` per connection.
- **PR-4: Durability.** Never replaced on app update; survives Clear App Cache; only Reset Everything wipes.
- **PR-5: Backup/restore conformance.** Idempotent CREATE IF NOT EXISTS lets older backups gain newer tables on restore.

Cross-slot: PR-4 is enforced by ST-1 (separate file from Shared DB) and ST-10 (Reset Everything is the only wipe path); PR-5 is exercised by ST-7.

## Debug contract (`DB-`)

- **DB-1: Build label substitution.** Placeholder substitution at build *and* serve time (AC-15). Format `<YYYY-MM-DD>-<short-sha>`.
- **DB-2: Build badge.** Always-visible runtime display showing local + server labels.
- **DB-3: Boot phase marks + watchdog.** Named `bootMarks`; watchdog timeout surfaces a recovery panel; slow-boot persistence across sessions.
- **DB-4: Sanitized error sink.** POST endpoint; 16KB cap; rate limit; always 204; allowlisted `kind=` enum; server-side free-text sanitization.
- **DB-5: Sink-as-analytics.** Adding a new `kind=` enum is the only widening lever. No separate analytics endpoint, no separate identifier scheme.
- **DB-6: Bug-report dialog.** Collects DB-2 + DB-3 + DB-4 ring; opens mailto to configured maintainer.
- **DB-7: Force-gate / force-reset escape hatch.** Reachable from `?diag` and a hardcoded URL parameter regardless of cookie / localStorage state (per AC-6).
- **DB-8: Configurability.** Every part is configurable. Purely-personal PNAs may have empty sink, no maintainer mailbox; the substrate still works.
- **DB-9: Test affordance.** Workspace exposes the active data provider on a stable global (`window.__dataProvider` in fellows_local_db) so test suites can drive the contracts the same way the workspace does, without a separate test-only seam (per Q5 resolution).

Cross-slot: every component implements DB-1; WS instantiates DB-2, DB-3, DB-6, DB-7, DB-9; DI hosts DB-4 (when present).

## Cross-slot sub-contract summary

Sub-contracts that span slots, formalized:

- **Build-label discipline (AC-15):** every component implements DB-1.
- **Update notification:** DI-2 → SW banner → WS-3 reload affordance.
- **Opt-in directory update (AC-10):** IN-4 → ST-8 → SH-5 → WS-3 (orphan render).
- **Storage RPC boundary:** WS-4 calls ST-3 / ST-4 / etc.; ST-2's handshake gates whether mutations are allowed (AC-4).
- **Restore data flow:** WS (file picker / backup picker UI) → ST-7 → PR-5 (re-bootstrap).
- **User-aware payload (AC-19):** WS-10 ↔ CO-5 — dual-listed because both slots co-implement.
- **Capability-failure surfacing:** ST-2 (`opfsCapable=false`) → WS-6 (panel render); ST-9 (`OWNERSHIP_CONFLICT`) → WS-6 (multi-tab variant).
- **Diagnostic substrate (DB-*):** every slot logs to DB-4; WS surfaces DB-2/3/6/7/9.

These cross-slot threads are what make the spec describe a *system* rather than a bag of slots.

## Decomposition decisions

- **No slots split.** Each top-level slot keeps a single contract surface; sub-contracts give it texture without fragmenting the toolkit's mental model. The toolkit may internally factor slots further (Storage in particular has eleven internal contracts already), but the spec exposes one slot per concern.
- **Cross-slot ACs land in both slots' sub-contracts.** AC-19 is both WS-10 and CO-5; AC-10 fans out into IN-4 + ST-8 + SH-5 + WS-3; etc. The AC table remains the single source of truth; sub-contracts cite ACs where they land.
- **One naming convention.** `<slot prefix>-<integer>`, monotonic per slot. No renumbering as items are added; new sub-contracts get the next integer.

---

## Next steps (proposed, in dependency order)

The partition pass (this reorg) is now done. Working from the destination-tagged content above.

1. **Stub `docs/pna_toolkit/`** with skeleton files:
   - `PNA_Spec.md` with version header (`Spec-Version: 0.1`) and section skeleton (Vocabulary, Goals, Use cases, Flavor axes, Composition, Universal ACs, Slot map, Scope/versioning)
   - `axes.md` with one H2 per axis (Composition model, Distribution, Storage substrate, Ingestion shape, Workspace shell, Comms transport set, Use case)
   - `use_cases.md` with one H2 per attested use case
   - `spec/contracts/` directory with placeholder files for each typed contract (worker-init-handshake.schema.json, worker-rpc-protocol.schema.json, distribution-auth.openapi.yaml, client-errors-payload.schema.json, transport-interface.d.ts, shared-db.schema.sql, private-db.schema.sql, plus MCP server tool surfaces: mcp-data-ops.schema.json, mcp-ingestion.schema.json, mcp-comms.schema.json, mcp-diagnostics.schema.json)
   - `CHANGELOG.md` with the v0.1 entry
   - `llms.txt` (for the spec itself; will lift with the toolkit)
2. **Draft `docs/pna_toolkit/PNA_Spec.md`** from this triage's universal content (Goals + Vocabulary + Use cases + Flavor axes overview + Composition section + Universal ACs + Slot map + Scope/versioning). Self-contained; no fellows references except as cross-links to the reference design.
3. **Draft `docs/pna_toolkit/axes.md`** from the Flavor axes section + flavor-derived ACs grouped by axis-pick trigger. Each axis-pick lists which ACs it triggers and which other axis-picks it commonly correlates with.
4. **Draft `docs/pna_toolkit/use_cases.md`** from the Use cases section. Directory Archive entry links to fellows's Architecture.md as the reference design; PRM entry remains `[draft]` until a reference design is built.
5. **Fill `docs/pna_toolkit/spec/contracts/`** with the typed contracts as the spec drafts cite them.
6. **Rewrite `docs/Architecture.md`** as fellows's specialization-and-conformance layer. New top section: "Spec conformance" declaring spec version + the seven axis picks + which flavor-derived ACs apply. Cross-links to `pna_toolkit/` for everything generic. Specialization-only invariants (fellows-specific operator concerns, fellows-specific HTTP routes, etc.) stay here.
7. **Add `llms.txt` at repo root** for fellows (distinct from the one inside `pna_toolkit/`). Points at fellows's `docs/Architecture.md` and, during the transition, the `pna_toolkit/` subdir.
8. **Demote** `docs/email_gate.md`, `docs/persistence_and_upgrades.md`, `docs/browser_support.md`, `docs/data_provenance.md` to Architecture.md annexes (unchanged from prior plan).
9. **When the personal_network_toolkit repo is created**: `git mv docs/pna_toolkit/` over to its destination; update fellows's `Architecture.md` cross-links from local paths to toolkit-repo URLs; delete the now-empty `docs/pna_toolkit/` here. fellows's repo retains only fellows-specific content (Architecture.md + annexes + repo-root llms.txt).
10. **PRM reference design** (separate repo, separate effort): builds against the spec; its `docs/Architecture.md` declares PRM-flavor axis picks; PRM-flavor ACs (AC-PRM-B, AC-PRM-C) lose their `[draft]` tags once realized. At that point, `pna_toolkit/use_cases.md` gets a link to the PRM reference design.
11. **Delete `_pna_triage.md` and `_pna_spec_format_landscape.md`** once steps 2-8 are committed.
