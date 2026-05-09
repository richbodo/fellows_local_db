# PNA Spec Format — Landscape Pass (scaffolding)

> Working notes for choosing the format / shape of `docs/PNA_Spec.md`. The
> spec is intended to be readable by humans and by AI agents, with the AI
> as the primary builder per the "we expect most PNAs to be built and
> rebuilt by AIs" framing in `_pna_triage.md`. Delete this file once the
> format is settled and the spec is drafted.
>
> Working session: 2026-05-08 with @richbodo.

---

## What we need from the format

Working from the triage doc's preamble:

1. **Readable as prose** — humans need to understand it; AIs handle structured prose well.
2. **Numbered, addressable invariants** — so contracts can be cross-referenced and an AI can check them individually.
3. **Versioned** — so reference designs can declare which spec version they target, and so future versions can supersede invariants without breaking older designs.
4. **Composable with machine-readable contracts** for parts where prose is genuinely ambiguous (data shapes, endpoint shapes, RPC handshakes).
5. **Reference designs as evidence** — at least one deployed PNA per reference design grounds the prose in something that actually runs.
6. **AI-pickup-able from a known entry point** — discoverable via repo conventions (`README.md`, `llms.txt`, `CLAUDE.md`, etc.).
7. **Not over-formalized** — verifiable code is a long-arc goal, not a near-term prerequisite.

---

## Landscape

### Interface and data-shape specs (mature, broadly-known)

- **OpenAPI / Swagger.** REST API specs in JSON/YAML. Mature, widely adopted, excellent tooling. AI agents handle it natively because it's everywhere.
- **JSON Schema.** Data-shape specs. Used inside OpenAPI and standalone. Native AI handling.
- **GraphQL SDL.** Type system + query language. More expressive for typed graphs.
- **Protocol Buffers, Cap'n Proto, FlatBuffers, Thrift, Avro.** Binary IDLs. Heavy tooling, overkill for PNA's needs (no wire-format pressure).
- **TypeSpec (Microsoft).** Higher-level language that compiles to OpenAPI / JSON Schema / GraphQL. Newer.
- **AsyncAPI.** OpenAPI for event-driven systems. Less widespread.

**Relevance to PNA.** The Distribution component's HTTP endpoints (auth status, send-unlock, verify-token, logout, client-errors) fit OpenAPI cleanly. The worker init handshake, RPC operation shapes, and the Communications transport interface fit JSON Schema cleanly. The Shared and Private DB schemas are best expressed as SQL DDL (which is itself the canonical contract).

### Formal specification languages (heavy)

- **TLA+.** Lamport's formal spec language. Real model checker (TLC). High learning curve, narrow audience.
- **Alloy.** Lightweight formal modeling. Easier than TLA+, less expressive.
- **Z notation, B-method, Event-B, VDM.** Older formalisms used in safety-critical industries.
- **Coq, Isabelle, Lean.** Proof assistants. Can specify and prove. Heavy.

**Relevance to PNA.** Almost certainly overkill for v0.1. The architectural commitments could be expressed in TLA+, but the cost is high and the audience is narrow. Re-evaluate when verifiable code becomes a near-term goal, probably v0.3+ at the earliest.

### Architecture documentation patterns (lightweight)

- **ADR (Architecture Decision Records).** Markdown-per-decision. Captures context + decision + consequences. Widely adopted (originated at ThoughtWorks / Michael Nygard). The AC-N table format we're already using is an inline ADR equivalent.
- **C4 model.** 4-level architecture diagrams (context, container, component, code). Simon Brown. Visual.
- **arc42.** 12-section template for architecture docs.
- **4+1 view model.** Older, Kruchten. Logical / development / process / physical / scenarios.
- **Diátaxis.** Doc framework with four categories: tutorials, how-to, reference, explanation. Adopted by Django, GitLab, Cloudflare, Stripe.

**Relevance to PNA.** ADR-style is what we're doing for architectural commitments — keep doing it. C4 / arc42 / 4+1 are heavier than we need; they target enterprise architecture. Diátaxis is a doc-organization principle that's useful if the spec eventually splits into multiple files (tutorial for new builders, reference for the contracts, explanation for the why).

### AI-targeted documentation conventions (emerging)

- **`llms.txt`.** Proposed by Jeremy Howard (answer.ai). Single file at site root, markdown, points at the most relevant docs for an LLM. Companion to `robots.txt` / `sitemap.xml`. Adoption has been growing — Anthropic, Cloudflare, Hugging Face, Stripe, others publish `llms.txt` files for their docs. Two variants: `llms.txt` (curated index) and `llms-full.txt` (concatenated full content). Cheap to add.
- **AGENTS.md / CLAUDE.md.** Project-level conventions for agent-readable docs. fellows_local_db already has a `CLAUDE.md` with project-specific guidance.
- **MCP (Model Context Protocol).** Anthropic's protocol for runtime AI-system interaction (tools, resources, prompts). JSON-RPC based. Targets the live agent-system interface, not the design-time spec — though MCP servers could *expose* spec contents to agents at runtime.
- **Tool specs (Anthropic tool format, OpenAI function calling).** JSON schemas describing callable tools. Embedded in API requests; not standalone spec format.

**Relevance to PNA.** `llms.txt` looks like the right discovery convention — small, well-defined, growing adoption, cheap. MCP is interesting longer-term: a future PNA toolkit could expose the spec via an MCP server an AI consumes natively, but that's not the right shape for the *spec itself* in v0.1.

### Behavior-as-spec (executable, conformance-oriented)

- **Cucumber / Gherkin (BDD).** Scenarios as specs, executable as tests. Human-readable.
- **Property-based testing (Hypothesis, QuickCheck, fast-check).** Specifies properties; randomly tests them. Poor man's formal spec.
- **Specs-as-tests in general.** The `window.__dataProvider` test seam in fellows_local_db is essentially this — contracts are exercised via Playwright against a live instance.

**Relevance to PNA.** Useful for verifying conformance of an AI's output once it has built a PNA. Less useful for the spec itself. Workflow: prose spec → AI builds reference design → test suite proves the reference design conforms. The reference design's tests become the conformance checker for that flavor.

---

## Recommendation

Compose `docs/PNA_Spec.md` and the surrounding artifacts from established conventions rather than inventing new formalism. Concrete plan:

### Layer 1 — Prose spec (`docs/PNA_Spec.md`)

Markdown. Sections in this order:

1. Spec version + changelog summary
2. Vocabulary
3. Goals (with reasoning)
4. Architectural commitments — ADR-style numbered table (AC-N)
5. Slot map (interfaces and components)
6. Per-slot contracts — prose with explicit references to the typed contracts in Layer 2
7. Scope and versioning (deferrals + how versions evolve)
8. Reference designs — links out to known PNA implementations and what flavor each represents

Numbered invariants throughout for cross-reference. Each AC-N gets one paragraph; each slot gets a bounded section (~1–2 pages). Total target length: ~30–40 pages of markdown — long enough to be precise, short enough an AI can reason about it in one context window.

### Layer 2 — Machine-readable contracts (`docs/spec/contracts/`)

Separate files for the parts where prose is genuinely ambiguous:

- `worker-init-handshake.schema.json` — JSON Schema for the worker `init` RPC return shape
- `worker-rpc-protocol.schema.json` — JSON Schema for `{id, op, args}` ↔ `{id, ok, result|error}` envelope
- `distribution-auth.openapi.yaml` — OpenAPI fragment for `/api/auth/status`, `/api/send-unlock`, `/api/verify-token`, `/api/logout`, `/api/client-errors`
- `client-errors-payload.schema.json` — JSON Schema for the sanitized error sink payload
- `transport-interface.d.ts` — TypeScript declaration for the Communications transport interface (`canHandle`, `launch`, `descriptor`)
- `shared-db.schema.sql` — SQL DDL for the canonical Shared schema (record table + extra_json + optional FTS5 + asset URL convention)
- `private-db.schema.sql` — SQL DDL for the canonical Private schema (groups + group_members + record_tags + record_notes + settings)

The prose spec references these by relative path. AIs that need exact shapes pull them directly. Humans treat them as the authoritative specification of those parts.

### Layer 3 — Reference designs (each in its own repo)

Each reference design lives in a separate repo with its own `docs/Architecture.md`. The architecture doc declares:

- Which PNA spec version it targets (e.g., `Spec-Version: 0.1`)
- Its slot-fill choices (Distribution = magic-link PWA; Ingestion = Knack-JSON-to-static-archive; …)
- Its load-bearing adjectives ("magic-link distributed PWA + static network DB archive + single shared directory")
- Any specialization-only invariants

fellows_local_db is the first reference design.

### Layer 4 — Discovery (`llms.txt` at repo root)

A small `/llms.txt` at the repo root (and in each reference design's repo). Format: markdown, structured per the convention (top-level project name + summary + sectioned link list).

For the personal_network_toolkit repo, `llms.txt` points at `PNA_Spec.md`, `docs/spec/contracts/`, the changelog, and the list of known reference designs.

For fellows_local_db, `llms.txt` points at `PNA_Spec.md` (in the toolkit repo, by URL), the local `docs/Architecture.md`, and the project's `CLAUDE.md`.

### Layer 5 — Conformance (deferred)

A reference design's existing test suite serves as its conformance checker. Property-based / scenario-based tests prove the implementation satisfies the contracts. fellows_local_db already has Playwright tests against `window.__dataProvider`; that pattern generalizes.

Formal verification (TLA+ etc.) stays a v0.3+ goal; not blocking v0.1.

---

## Versioning

- Initial version: `Spec-Version: 0.1`. Placeholder until enough demand to merit `1.0`.
- Each version bump carries a `CHANGELOG.md` entry listing changed AC-N rows, slot-contract changes, and deferral resolutions.
- Reference designs declare which version they target. An AI rebuilding a reference design against a newer spec follows the newer contracts; mismatch is allowed, but the reference design's `Architecture.md` says which version it satisfies.

---

## What this implies for the next step

When we draft `PNA_Spec.md`:

1. Start from `_pna_triage.md` Part 1 (synthesis per slot) — that material maps directly into the prose spec sections.
2. Stub `docs/spec/contracts/` with empty files for each typed contract; fill them as the spec drafts cite them.
3. Add `llms.txt` to the repo root pointing at the new spec + contracts dir.
4. Tag the spec `Spec-Version: 0.1` and start a `CHANGELOG.md`.

No formal-methods commitment, no new specification language to learn, no infrastructure beyond markdown + JSON Schema + OpenAPI + a small `llms.txt`. Established conventions composed into a new shape.
