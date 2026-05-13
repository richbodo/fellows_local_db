# Use cases

> **Spec-Version:** 0.1 (draft)

This document catalogs the use cases the spec attests. Each use case names a coherent class of PNA from the user's perspective; it suggests default axis picks but does not determine them. The Use case concept is defined in [`PNA_Spec.md` § Vocabulary](PNA_Spec.md#vocabulary).

v0.1 attests two named use cases plus one longer-arc target:

- [Directory Archive](#directory-archive) — realized in fellows_local_db
- [Personal Relationship Manager](#personal-relationship-manager-draft) — draft (no PNA-spec-conforming reference design yet)
- [Multi-PNA ecosystem](#multi-pna-ecosystem-target-v02) — target (v0.2+, no reference design)

---

## Directory Archive

A snapshot of some external organization's roster (a fellowship, a school, a cohort, a community) plus the user's private overlay on top. Shared data has a *single external source* — typically the organization that previously hosted the directory as a SaaS service, or a maintainer who curates updates. Each distributed user receives the same shared data and accumulates their own private overlay (groups, tags, notes). Distribution typically goes outward to many users from a maintainer or organizer; the toolkit's role is to make that distribution easy and safe.

**Default flavor (as realized in fellows_local_db):**

`distribution:web-bundle-with-magic-link + storage:opfs-sqlite-wasm + ingestion:single-source-static-mirror + workspace-shell:vanilla-js-spa + comms:mailto-only + mcp-exposure:none`

The use case doesn't *determine* these picks — a hypothetical Directory Archive could ship with a Tauri shell + native SQLite + sideloaded distribution. The picks above are what fellows_local_db chose; another Directory Archive reference design might choose differently. See [`axes.md`](axes.md) for the full pick catalog per Axis.

**Triggered flavor-derived ACs:** Via fellows_local_db's picks — AC-2, AC-5, AC-8, AC-14 (distribution-derived); AC-3, AC-12, AC-13 (storage-derived). Full per-pick triggers in [`axes.md`](axes.md).

**Reference design:** [fellows_local_db](../Architecture.md) (this repo, for now; will become a separate repo URL when the toolkit lifts).

---

## Personal Relationship Manager [draft]

The user's *own* contact databases (Google + Apple + Facebook + LinkedIn + organizational directories) mirrored locally, plus rich private overlays (notes, tags, groups, comms history, message recency) and tools (LLM-mediated search, visual recall, eventual P2P). Shared data has multiple sources the user controls; ingestion involves a dedup pass. Typically single-user, not distributed onward — the PRM is for one person's contact graph.

**Likely flavor (draft, PRT-inspired):**

`distribution:never-distributed-single-user + storage:native-sqlite-via-filesystem + ingestion:multi-source-merge-with-dedup + workspace-shell:tui-textual + comms:shell-out-to-cli-clients + mcp-exposure:full`

This is a draft — a future PRM reference design built against PNA Spec v0.1 will live in its own repo and may pick differently. The TUI shell choice in particular is PRT's current direction; a Tauri-wrapped GUI or a CLI-subcommand-only flavor are equally plausible alternatives.

**Triggered flavor-derived ACs (via likely picks):** AC-PRM-B **[draft]** (ingestion-derived), AC-PRM-C **[draft]** (storage-derived). MCP-related universal ACs (AC-MCP-A, AC-MCP-B) apply when `mcp-exposure` is non-`none`.

**Reference design:** None yet. PRT (`../../prt/`, a sibling repo) is the inspiration but pre-dates this spec.

**Why include a draft use case in v0.1?** Capturing PRM's outlines now stress-tests the universal-vs-flavor partition. An AC that fires for both Directory Archive *and* PRM is genuinely universal; an AC that fires for only one is flavor-derived and gets axis-pick triggers. With only one realized use case, every AC would look universal; the second case (even in draft) forces the right partition.

---

## Multi-PNA ecosystem [target, v0.2+]

The longer-arc goal introduced in [`PNA_Spec.md` § Vision](PNA_Spec.md#vision): multiple PNAs cooperating on one user's device, wired together at runtime by an AI agent via MCP. This isn't a single PNA but a *system of PNAs*; the use case is the system, not any individual PNA within it.

**Roles in the ecosystem:**

- **Personal Relationship Manager** — holds private relationship data (notes, tags, groups, history); hosts the meta-workspace where the user sees their full picture.
- **Contact Manager** — edits and manipulates shared contact data (typically downstream of Google / Apple / Facebook exports). A contact manager could also exist as a plugin to the PRM, or interact via MCP.
- **Directory Archive(s)** — one or more snapshots of external organizational rosters (a fellowship, a school, an old workplace). fellows_local_db is one instance.
- **Calendar app** — events, scheduling, relationship-temporal data.

**Two complementary modes for the user:**

- **Per-PNA workspaces (always clean).** Just the fellows directory; just Google contacts; just Facebook contacts. Single-context, focused, fast — useful for tasks scoped to one source.
- **Unified meta-view (in the PRM).** A read-only composed database deduplicating across the per-PNA shared stores. Bob's cell from Google + work history from a fellowship directory + email from a Facebook export combine into one coherent contact view. The PRM's private overlay (notes, tags, groups) references unified-view records via stable IDs; private data stays in the PRM regardless of which shared source contributed the underlying contact record.

**v0.2+ work:**

Achieving the unified meta-view requires per-source database connectors, careful dedup and conflict resolution, and disciplined provenance — substantial work that's deferred to later spec versions. The eventual *ecosystem reference design* would demonstrate this; v0.1 establishes the architectural seams (the four canonical MCP server contracts, AC-10's opt-in non-destructive re-imports, AC-PRM-B's draft multi-source dedup contract, AC-MCP-A's cloud-client consent rule, AC-MCP-B's workspace-mediated outreach) that let the ecosystem grow into place.

This is the deep "why" behind defining slot contracts substrate-neutrally: when the second PNA exists, an AI agent can wire it to the first without modifying either; when the fifth PNA exists, the same. Composability isn't bolted on; it's the architecture's primary deliverable.

**Reference design:** None yet. Target for v0.2+.
