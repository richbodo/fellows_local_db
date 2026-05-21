# Plan: Convert PNA Spec to RFC Format and Bootstrap PRT as a Conformance Suite

## Summary

Convert `PNA_Spec.md` into an RFC-formatted normative specification, then treat the Personal Network Toolkit (PRT) as the conformance suite that grows alongside implementations. The RFC format isn't valued for IETF legitimacy — it's valued because it produces unambiguous, AI-parseable normative requirements (MUST / SHOULD / MAY) that both humans and agents can implement against and verify conformance to.

## Architectural framing

- **PNA** = the specification: what makes a Personal Network Application correct
- **PRT** = conformance suite + first-party reference tooling
- **Implementations** (hello-world, Tolaria composition, khard/vdirsyncer composition) = test cases that pressure-test and refine the spec
- **AI agents** = primary downstream consumers: they read the spec, build conforming implementations, and verify via the harness

The spec and implementations co-evolve. Successful real-world RFCs (SMTP, HTTP, CalDAV, OAuth) were not written in isolation — they shaped and were shaped by prototypes. The first few PNA implementations will surface architectural constraints that aren't yet visible in `PNA_Spec.md`.

## Order of operations

1. **Phase 1**: Research example specs + convert PNA_Spec.md to RFC draft
2. **Phase 2**: Build hello world (SaaS contacts backup/viewer) as forcing function
3. **Phase 3**: Refine spec based on hello-world learnings → RFC draft 2
4. **Phase 4**: Composition with existing tools (Tolaria + khard + vdirsyncer)
5. **Phase 5**: Conformance harness grows need-driven
6. **Ongoing**: PNA conformance survey across the ecosystem

Note: this puts the hello world *before* composition with Tolaria/khard. Rationale below.

---

## Phase 1: Research + Conversion

### Research targets (RFCs and specs to mine)

IETF RFCs worth mining for format and conformance idioms:

- **RFC 2119 + RFC 8174** — normative keyword semantics (MUST, SHOULD, MAY, MUST NOT). Foundation.
- **RFC 6352 (CardDAV)** — directly relevant; contacts protocol with explicit conformance levels
- **RFC 4791 (CalDAV)** — same family; good interop history and test-suite culture
- **RFC 7519 (JWT)** — tight, widely-implemented spec; exemplar of minimal normative core
- **RFC 6749 + RFC 6750 (OAuth 2.0)** — strong profile/extension pattern; mobile considerations
- **RFC 8628 (Device Authorization Grant)** — model for constrained-device / mobile profile pattern

Non-IETF specs that are probably closer to PNA's shape (since PNA is about application behavior and data sovereignty, not just wire format):

- **W3C Solid Protocol** — personal data sovereignty, multiple implementations, near-identical philosophy to PNA. Worth deep study.
- **W3C ActivityPub** — federation between sovereign servers; pattern for the community-protocol layer
- **AT Protocol (Bluesky)** — modern spec-first design with reference implementations and explicitly AI-era documentation patterns
- **Matrix Specification** — explicit conformance levels, modular spec, well-organized for multi-implementation reality
- **IndieWeb microformats specs** — small, focused, conformance-by-multiple-implementations

**Honest assessment for Claude Code to factor in:** IETF RFCs excel at *protocol* conformance (bytes on the wire, state machines). The W3C / Matrix / Solid family is closer to PNA's shape because PNA constrains application behavior and data flow, not just wire format. Mine both; copy whichever idiom fits each section of PNA.

Deliverable: `pna-rfc-research-notes.md` — findings, cherry-picked patterns, idioms to import.

### Conversion approach

For each section of the existing `PNA_Spec.md`:

1. **Separate normative from informative content.** Normative = conformance-bearing requirements. Informative = motivation, examples, context.
2. **Reword normative content using RFC 2119 keywords.** Every requirement becomes MUST / MUST NOT / SHOULD / SHOULD NOT / MAY.
3. **Make every MUST/SHOULD testable.** If a requirement can't be mechanically or AI-evaluated, either rewrite until it can be, or downgrade to informative.
4. **Add ASCII diagrams and tables** where they sharpen meaning. Data flow diagrams, state machines, role/permission matrices.
5. **Introduce conformance levels** if useful: e.g., "Core" / "Federation" / "Mobile Profile". A mobile-constrained device may legitimately not implement federation but should still be "PNA-conformant" for what it does implement.
6. **Preserve `PNA_Spec.md` as v1.** Produce `pna-rfc-draft-01.md` as the converted form. Keep traceability.

### Phase 1 deliverables

- `pna-rfc-draft-01.md` — first RFC-formatted draft
- `pna-conformance-checklist.md` — flat list of every extracted MUST/SHOULD assertion (the seed of the conformance harness; what eventually becomes runnable tests)
- `pna-rfc-research-notes.md` — research findings

---

## Phase 2: Hello World — SaaS Contacts Backup & Viewer

Forcing function. Pull contacts from the various SaaS services in use (Google Contacts, LinkedIn export, iCloud, whatever else), normalize into PNA-canonical form, and provide a basic viewer.

**Why this app:**

- Immediately useful (a thing worth having anyway)
- Implements a meaningful subset of the spec without needing the federation layer
- Pressure-tests the data-sovereignty assertions hardest — explicitly moves data *out of* SaaS into a vault under user control
- Establishes the translator pattern (one translator per SaaS source → canonical form)
- Surfaces what's wrong with the canonical schema when it meets real-world dirty contact data

**Acceptance criteria:**

- Does not violate any MUST NOT in the current spec
- Output conforms to the canonical PNA contact schema
- Idempotent imports; merge semantics defined
- Includes a basic viewer (CLI or web — whichever ships faster, this is throwaway-grade)

**What this will teach:**

- Which spec assertions are operationally meaningful vs. theoretical
- Where the canonical schema is too rigid or too loose
- What the translator surface area actually looks like
- First implications for desktop/mobile split (probably desktop-only at this stage)

---

## Phase 3: Spec Refinement → RFC Draft 2

After hello world ships, revise the spec based on lessons learned. Specifically:

- Which assertions were reinterpreted during implementation?
- Which schema fields had to be added, removed, or relaxed?
- What translator or extension points need first-class treatment in the spec?
- What was over-specified? Under-specified?

Produce `pna-rfc-draft-02.md`.

---

## Phase 4: Composition with Existing Tools

Build a second implementation by composition: Tolaria as workspace/viewer, khard as CLI contact manager, vdirsyncer as sync substrate, with the translator layer normalizing data into PNA canonical form.

**Key question this phase answers:** can the same PNA be described across two very different tool compositions? If yes, the spec is portable. If no, the spec is over-fitted to the hello-world.

This is also the right time to think hard about which tool fits which PNA subsystem — storage, viewer, sync, federation. That subsystem mapping is what eventually feeds the conformance survey.

---

## Phase 5: Conformance Harness Growth

Build conformance tooling incrementally, driven by what each implementation reveals:

1. **Mechanical tests** — formalize the MUST assertions from `pna-conformance-checklist.md` as runnable tests that any PNA implementation can be run against
2. **Runtime audit** — sandbox + egress monitor + filesystem monitor for the negative-space requirements (no telemetry, no unauthorized network, no unencrypted leaks). Likely Docker + mitmproxy or equivalent.
3. **AI-mediated review** — an agent that reads spec + implementation source + behavioral traces and produces a structured conformance report. Covers posture/intent assertions that mechanical tests can't reach.
4. **Interop matrix** — published table of which implementations have been verified against which others, at what spec version.

The harness should be portable from day one: not "Python tests for my CLI" but "a test harness any conforming implementation can run against itself."

---

## Ongoing: PNA Conformance Survey

Once the harness is mature enough, run it across existing tools to identify accidental PNAs:

- Which tools satisfy the spec without intending to?
- Which subsystems does each fit best (storage / viewer / sync / federation)?
- Desktop vs. mobile fitness matrix (mobile will likely need a constrained profile of the spec)

Becomes a living ecosystem map — the public-facing artifact that helps others find or build PNA-conformant tooling.

---

## Open decisions before Claude Code starts

These shouldn't be decided unilaterally; flag them and surface choices:

1. **Repo layout.** Does the RFC live in the same repo as `PNA_Spec.md`, or a separate `pna-spec` repo? Probably separate, so the conformance suite and spec can be versioned independently.
2. **Canonical contact schema baseline.** Use vCard 4.0 as the floor and extend, or define something more opinionated? vCard has the advantage of existing translators; the disadvantage of legacy cruft.
3. **Mobile profile.** Separate document, or sections within the main RFC with explicit "Mobile MAY omit §X"?
4. **Versioning convention.** RFC-style drafts (`draft-pna-01`)? Semver? Date-based?
5. **License.** Probably CC-BY-4.0 for the spec, MIT or Apache 2.0 for reference tooling. Worth being explicit.
6. **Naming for the federation/community-protocol layer.** Still TBD; do not assume "CRT" carries forward.

---

## Notes on the order of operations

The proposed order swaps two steps from the original sketch: RFC conversion *and* hello world both happen before composition with Tolaria/khard/vdirsyncer. Reasoning:

- Hello world is more controlled — one app, one developer, immediate feedback loop. Spec changes are easier to identify and attribute.
- Composition with multiple existing tools is a stronger test, but it should come *second*. Otherwise spec-vs-tool friction tangles with spec-vs-reality friction and it's hard to tell which is which.
- The conformance survey is correctly downstream of having a mature harness. Don't try to survey without something to measure with.

Everything else matches the original proposed order.
