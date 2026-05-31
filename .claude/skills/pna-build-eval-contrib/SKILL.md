---
name: pna-build-eval-contrib
description: 'Use when building, extending, or evaluating a Personal Network Application (PNA) — local-first, private-by-default applications that mirror SaaS contact data into a user-owned workspace and operate on relationship data with no remote authority. Triggers on requests to build a local-first contact app, relationship manager, private CRM-like tool, or any app built around personal-network data; on requests to audit an existing application for PNA-spec conformance ("is this app safe to install?", "does my app conform?"); and on requests to propose a change back to the PNT spec when a builder finds a gap. Three flows: build a conformant PNA from the spec, evaluate whether an existing application conforms, and author a contribution PR back to PNT.'
---

# Building, Evaluating, and Contributing to PNAs

A PNA is a local-first application built to the PNT spec. The spec defines the architectural commitments (ACs) all PNAs share and the axes along which they legitimately differ. Conformance is satisfied by implementing the typed contracts in `contracts/` for each declared axis pick and honoring every applicable AC.

PNT itself is a *generative + evaluative* application-class blueprint:

- **Generative.** AI agents read it to build conformant PNAs. The spec + contracts + reference designs are the materials.
- **Evaluative.** AI agents read it to evaluate whether an existing application conforms. The user trusts the spec; they want to know whether a specific candidate honors it.

This skill covers three flows: **build**, **evaluate**, **contribute**. Use whichever the user's request fits.

## Build flow

Use when the user is starting or extending a PNA.

1. **Read the spec end-to-end first.** `spec/PNA_Spec.md` covers vocabulary, goals, axes, universal architectural commitments, and the slot map with 57 sub-contracts. The universal ACs are non-negotiable.
2. **Determine axis picks with the user.** Each axis has documented options in `spec/axes.md`. The axes in v0.1: distribution, storage substrate, ingestion shape, workspace shell, comms transport set, MCP-exposure. The spec uses variable language because the set may evolve.
3. **Author an Architecture document for the design.** Use the template at `reference_designs/templates/ARCHITECTURE_TEMPLATE.md`. It declares the PNA Spec version, axis picks and their versions, and per-axis implementation choices.
4. **Pull the typed contracts.** For each axis pick, the relevant contracts live in `contracts/`. Each contract opens with a `Realizes: AC-X, AC-Y` header naming the ACs it realizes. Treat the contracts as load-bearing — do not deviate without proposing a spec change (contribute flow).
5. **Find a reference design that shares axis picks.** Each `reference_designs/<name>/` directory has a record with the design's flavor and a Software Heritage SWHID linking the archived source. Study the design that's closest to what the user wants.
6. **Build against the contracts.**
7. **Fill in the AC attestation table for the design.** For every applicable AC, name (a) how the design realizes it, with code references, and (b) the specific test, LLM evaluation rubric, or human-review note that verifies it for this design. This is required for any future contribution PR.
8. **Run the evaluate flow on the in-progress code as a self-check.**

## Evaluate flow

Use when the user wants to audit an application for PNA conformance — either someone else's candidate ("is this app safe to install?") or their own in-progress design ("does my app conform yet?"). Mechanics are the same in both cases; the user's framing tells you which ACs to emphasize.

Inputs: a candidate PNA's source tree (or a description sufficient to read its behavior), and either a declared set of axis picks (from an Architecture document, if present) or picks you can infer from the source.

1. **For each AC in `spec/PNA_Spec.md` that applies to the candidate's flavor**, decide conformance:
   - Read the relevant source files; trace the data flow or control flow the AC constrains.
   - Cite specific code locations supporting the decision.
   - If the candidate has an Architecture document with an AC attestation table, check that the declared verification mechanism actually runs and passes.
2. **For each flavor-derived AC in `spec/axes.md`** triggered by the candidate's axis picks, do the same.
3. **For each typed contract relevant to the candidate's axis picks**, check that the candidate implements the contract correctly. Contract headers (`Realizes: AC-X, AC-Y`) tell you which ACs the contract serves.
4. **Produce a structured report keyed by AC ID**:
   - `conformant` — with cited code locations.
   - `non-conformant` — with cited code locations showing the violation and the AC's stated requirement.
   - `not-applicable` — with reason (typically: the candidate's flavor doesn't trigger this AC).
   - `unable-to-determine` — with explanation; defaults to flagging for human review.
5. **Summarize at the top**: overall posture and the most concerning non-conformances. Goals 1–5 are the load-bearing user-facing concerns — anything compromising private-data sovereignty (Goal 1), source-mirroring honesty (Goal 2), transport security (Goal 3), durability (Goal 4), or local diagnosability (Goal 5) leads the summary.

Callers may ask you to emphasize specific Goals or axes at runtime (e.g., "focus on private-data sovereignty"). Treat that as a hint for the summary, not a structural variation.

## Contribute flow

Use when the user has built or operated a PNA and wants to submit it back to PNT as a reference design — whether they found a spec gap and want to propose a fix, or they have a working design that adds ecosystem value at a flavor not yet attested. The flow has two phases: **preflight validation** (is the design submission-ready?) and **PR authoring** (open the actual PR).

### Preflight validation

Before authoring the PR, validate that the design is submission-ready. This step is interactive — ask the user questions, walk them through gaps, iterate until clean.

1. **Locate the design's Architecture document.** Typically at `docs/Architecture.md` (or equivalent) in the design's own repo.
   - **If it exists**, validate it against the code. For each AC attested as `conformant`, check the cited code locations and confirm the realization matches. For each AC with a Verification mechanism declared, check that the cited test/rubric/note actually exists and (where automated) passes.
   - **If it doesn't exist**, walk the user through creating one interactively. Use `reference_designs/templates/ARCHITECTURE_TEMPLATE.md` as the template. Ask about each section in turn:
     - Which PNA Spec version does the design conform to?
     - For each axis in `spec/axes.md`, which pick does the design use, and at which axis version?
     - For each axis, how does the design realize the pick? (Read the code to help fill this in.)
     - For each applicable AC (universal in `spec/PNA_Spec.md`, plus any flavor-derived AC in `spec/axes.md` triggered by the picks): how does the design realize it? What test/rubric/note verifies it?

2. **Ask the user what's interesting architecturally about this design.** Three patterns are valuable enough to justify submission:
   - **New architectural commitment.** The design demonstrates a constraint the spec doesn't yet name. (Most valuable — the PR includes a spec diff.)
   - **Existing patterns on a new platform.** The design exercises existing ACs on a substrate or use-case not yet attested in the reference set. (Valuable — no spec change needed; the design's flavor expands the ecosystem.)
   - **Ecosystem value-add.** The design fills a use-case gap, brings accessibility, or makes something easier that no existing design demonstrates. (Valuable.)

   If the design fits any of these patterns, encourage submission. If it's purely identical to an existing reference with no novelty, surface that and ask what motivated the submission — if nothing surfaces, the PR may not be worth the maintenance overhead.

3. **Report what's broken or missing** in a structured list. The user needs to address these before the PR will be accepted:
   - Missing files (Architecture document, design record)
   - Missing sections in the Architecture document
   - Missing Verification field on any row of the AC attestation table
   - AC realizations whose cited code doesn't match the claim
   - Failing or missing tests on the Verification side
   - License problems (must be OSI-approved; must permit Software Heritage archival)

4. **Iterate.** When the user fixes things, re-run preflight. Keep going until the report is clean.

### PR authoring

Once preflight passes:

1. **Read `CONTRIBUTING.md`** for the acceptance rules.
2. **Frame the contribution.** If proposing a spec change, write the spec diff and explain what working code in the design demonstrates each change. If purely additive (no spec change), say so in the design record's contributions section.
3. **Author the design record** at `reference_designs/<design-name>/README.md` per `reference_designs/templates/TEMPLATE.md`.
4. **Copy the Architecture document** to `reference_designs/<design-name>/Architecture.md`. (PNT keeps its own copy at acceptance time; the design's own repo may evolve after.)
5. **Open the PR** with: spec diff (if any), design record, Architecture document, canonical repo URL, and the commit SHA being submitted.

After merge, the maintainer triggers Software Heritage archival on the design's repo at the accepted commit (planned tooling: `tools/swh-save.sh`, landing in Phase 5; until then, archival is performed manually via Software Heritage's Save Code Now) and records the returned SWHID in the design record. A final preflight run against the merged state should come out clean.

A builder using Claude Code can drive both preflight and PR authoring end-to-end. Maintainer review at acceptance time is the human-judgment gate that's intentionally not automated.

## Principles to honor in every flow

- **Layering of verification.** Deterministic tools (lints in `tools/`) for the mechanical layer; LLMs (you) for the architectural-conformance layer; humans for judgment-and-review at PR time. Investment is ~80/20 toward description-and-process; PNT does not ship a Python conformance test runner beyond trivial lints.
- **The AC is the unit of identity.** Every AC has a stable ID. Every contract names the AC(s) it realizes. Every Architecture document attests AC-by-AC. When citing non-conformance, cite by AC ID.
- **Conformance is checked, not awarded.** There is no certifying body. A user trusts an app because they (or an LLM running this skill) checked it against the spec, not because the app carries a badge.
- **Variable language about axis counts.** The spec says "the axes," not "the six axes." The set may evolve; don't hardcode numbers.

## Key resources

- `spec/PNA_Spec.md` — canonical spec (vocabulary, goals, ACs, slot map, sub-contracts)
- `spec/axes.md` — axes, attested picks per axis, flavor-derived ACs
- `spec/use_cases.md` — attested classes of PNA (Directory Archive, PRM [draft], Multi-PNA ecosystem [target])
- `contracts/` — typed contracts (JSON Schema, OpenAPI, SQL DDL, TypeScript), each with a `Realizes: AC-X` header
- `reference_designs/README.md` — index of accepted reference designs
- `reference_designs/templates/` — the per-design and Architecture templates
- `tools/lint-spec-ids.py` — checks AC ↔ contract traceability invariants
- `CONTRIBUTING.md` — full contribution rules
- `docs/prior_art.md` — survey of related work
