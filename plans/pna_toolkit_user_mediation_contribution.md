# Plan — Contributing the **User-mediation** invariant to the Personal Network Toolkit (PNT)

> **Status: SCOPE STAGED — TEST-FIRST, NOT YET EXECUTABLE.** This document scopes the third general
> PNT mechanism (dual in spirit to Exceptions and Constraints) and stages it for hand-off. Unlike the
> [Exceptions](pna_toolkit_exceptions_contribution.md) and [Constraints](pna_toolkit_constraints_contribution.md)
> plans, this one deliberately **does not** ship execute-ready spec text. Per the tracking issue
> (**#252**) the mechanism is **test-first**: the demonstrating tests define the enforceable boundary,
> and the spec is written to match what proved testable — not the other way round. Writing the spec
> first risks an unenforceable "user MUST comprehend" clause that `test_attestation_has_evidence.py`
> would (correctly) reject as evidence-free. So §3 sketches the *shape* of the PNT artifacts; the
> normative text is drafted only after §4 step 1 (the tests) lands.
>
> Nothing here files into PNT until the maintainer says so. Companion to, and the third of, the
> matched set staged in [`upstream_contributions_staging.md`](upstream_contributions_staging.md).
> The canonical lesson-learned is [`../docs/architectural_findings.md` § 2026-06-07](../docs/architectural_findings.md).
>
> Local paths: PNT repo `~/src/personal_network_toolkit`; demonstrating design (this repo) `~/src/fellows_local_db`.

---

## 1. Summary + motivation

### The discovery

Planning AI write-proposals ([`ai_write_proposals_groups.md`](ai_write_proposals_groups.md)) made
explicit a discipline the app had been practising piecemeal: an AI may *propose* a change, but the
user *disposes* of it against a deterministic before/after diff **in the workspace, not in the AI's
interface**. Pulling the thread showed this is not a rule about AI writes — it is one instance of a
single, previously-unnamed principle already load-bearing in at least six places:

- **AC-19** — the outbound payload is visible before send.
- **AC-16** — the user picks the transport per outreach.
- **AC-MCP-B** — MCP *stages* a `mailto:`; the workspace launches it.
- **AC-10 / AC-PRM-D** — directory re-import previews orphaned members and is user-initiated.
- **AC-PRM-A** — an LLM call over user data is a *transport*, inheriting the same mediation.
- the AI-writes plan's proposed **AC-PRM-E/F** — propose/dispose for the Private DB.

> **Name it:** *the human is the actuator; the workspace is the locus of ground truth.* Every path that
> mutates the sovereign store or sends data out of it routes through a user-legible review in a surface
> the user controls. The proposer — AI, network, or importer — only **stages**; the human **disposes**.

### The tension is structural, not a fellows wart

The PNA Spec commits to private-data sovereignty (Goal 1) and to mediated egress (the AC-16/18/19
family), but it has **no first-class name** for the cross-cutting invariant that *unifies* them: that
every mutation and every egress is gated by a distinct, attributable, legible authorization the
principal performs in a surface they control. Without the name, each AC re-derives the discipline
locally, and a *new* mutation source (the next importer, the next AI affordance) can be added without
anyone noticing it skipped the gate. The toolkit exists to name exactly this class of cross-cutting
property.

### The resolution — the third mechanism (dual to Exceptions and Constraints)

| Mechanism | Origin of the deviation | Metaphor | Effect on PNA mode |
|---|---|---|---|
| **Exception** (`EX-*`) | the **user raises** it | runtime error: raise / catch / handle | **exits** PNA mode |
| **Constraint** (`CST-*`) | the **platform imposes** it | compile-time error: inherit / detect / handle | **does not** change mode |
| **User-mediation** (this) | nothing is raised or inherited — it is an **always-on invariant** on the actuation boundary | **separation of duties / dual control**: the proposer cannot self-commit; a distinct principal authorizes | **invariant** (its *violation* is a conformance failure, like a silent deviation/over-reach) |

Where Exceptions catch a user-raised deviation and Constraints handle a platform-imposed ceiling,
User-mediation is the standing rule about **who may actuate**: a *proposer* (AI / network / importer)
holds the capability to **stage** but **no authority to commit**; mutation or egress requires a
distinct, attributable **dispose** event the principal performs in a surface they control.

### The hard part — what you must NOT try to test (the testability decision)

The obvious reading — "verify a real human is driving the workspace" — is a trap: that is the
bot-detection / liveness arms race, and detection is not assumed ahead of automation in that race. A
guarantee built on "is this a human?" is false confidence.

The escape is that the invariant **never required knowing who the actor is.** The enforceable property
is a property of the **code**, and it is actor-agnostic. The claim the spec may make is **bounded to
separation + legibility + attribution — NOT comprehension.** We cannot probe the user's mind, and an
automation driving the workspace can click *Approve* as easily as a person can. That residual is the
same shape as `EX-H7` (consent-to-human propagation: conformant for the mechanical half, explicitly
unenforceable for the "did the other side tell the human" half). **The naming choice — "the human is
the *actuator*," not "a human is *present*" — IS the testability decision.**

### Why this belongs upstream, not just in fellows

Per `pna-build-eval-contrib/SKILL.md` § Contribute → Preflight, the most valuable submission pattern
is **a new architectural concept the spec doesn't yet name**, with a demonstrating reference design.
This is that — and it completes the trio (user-raised / platform-imposed / actuation-boundary). The
spec change rides along with working code, as `CONTRIBUTING.md` requires.

---

## 2. The User-mediation concept

### The three enforceable properties (the demonstrating-test targets)

These are the code properties #252 commits to proving **first**. They become the normative
sub-contract clauses (working IDs `UM-1..UM-3`; naming is an open question, §5):

- **UM-1 — No bypass.** No path mutates the sovereign store or egresses its data except through the
  dispose gate. This is a **negative invariant** and so needs a **negative test** — same family as
  `test_no_durable_private_write_when_browse_only`, `test_worker_is_load_bearing_off_folder_via_raw_rpc`,
  and the `mode=ro` proofs. (Per § Conformance discipline: "X must NOT happen" is not covered by the
  test that X happens.)
- **UM-2 — Separation.** The proposing surface (the MCP inbox; any in-workspace AI; a network import
  staging area) carries **no actuation capability**. Dispose is a **distinct, attributable** event
  decoupled from the proposer — the entity that staged cannot be the entity that commits.
- **UM-3 — Legibility.** The dispose surface renders a **deterministic** before/after diff in
  **human-readable** content (names, not `record_id`s) and **escapes untrusted proposer strings**
  (the proposer's text is data, never markup/markup-trusted).

### The bounded claim (the honest part)

The invariant guarantees **separation, legibility, and attribution. It does NOT guarantee
comprehension.** This bound is stated in the mechanism itself, not buried — over-claiming
comprehension would be the same false-confidence failure the spec exists to prevent. The handler
attests the gap (à la EX-H7), it does not pretend to close it.

### What it explicitly does not cover (carry into the PR)

- **Human-vs-bot / liveness detection.** Out of scope — unwinnable arms race; a guarantee on it is
  false confidence.
- **Binding an enforceable contract from another AI.** No mechanism today: a stateless generator has
  no continuous identity or liability to bind, so an "AI contract" is closer to a category error than
  an unsolved engineering problem. Test that *we* made and recorded the ask (the best-effort
  `instructions` notice, EX-H7); treat the other agent's compliance as out-of-band.

### A commitment to pin before it's needed

"Review happens in a non-AI surface" is true in fellows today only **by construction** (vanilla-JS
SPA, no embedded agent). The deferred in-app local model and the `window.ai` search affordance are the
pressure points. The honest commitment is not "the workspace MUST NOT be an AI interface" but the
user-knowledge form: **any in-workspace AI is a *proposer* subject to the same gate, never an
*actuator*.** Declare it, with a frontier, *before* local-AI lands — not after. (This is a fellows-side
attestation commitment AND a candidate normative line for the spec; §5.)

---

## 3. Proposed PNT artifacts (SHAPE ONLY — normative text drafted from the tests)

Mirrors the matched set's structure. **None of the normative text below is final**; it is drafted
after §4 step 1, to match what the tests prove.

### 3a. NEW file: `spec/user_mediation.md` (or fold into an existing spec section — §5)

Sibling to `spec/exceptions.md` and `spec/constraints.md`. Carries: the concept (proposer stages /
principal disposes), the normative handler contract (`UM-1..UM-3` + the bounded-claim clause), the
header conventions, and a **mediated-boundary registry** — the enumerated mutation/egress boundaries a
reference design routes through the gate.

> **Why a registry of boundaries, not of instances.** Exceptions and Constraints each register many
> *instances* (`EX-CLOUD-LLM`, `CST-PWA-*`). User-mediation is **one invariant** that applies at
> **every** actuation boundary; the registry a reference design carries is its **list of mediated
> boundaries** (createGroup, restore, export, mailto-stage, directory re-import, AI-propose), each with
> the test that proves UM-1/2/3 for it. The spec defines the invariant once; designs attest the
> boundary list.

### 3b. Header conventions (mirroring `Relaxes:`/`Triggered-by:`)

- **`Mediates:`** — on a reference-design boundary entry, names what crosses the gate: a mutation of
  the sovereign store, or an egress of its data. Token form TBD from the tests (likely `mutation:<op>`
  / `egress:<transport>`).
- **`Proposer:`** — names the staging surface that has *no* actuation authority for this boundary
  (e.g. `mcp-inbox`, `network-import`, `in-workspace-ai`).
- **`Dispose:`** — names the attributable authorization surface + the test ref that proves UM-1/2/3.

### 3c. Extend `tools/lint-spec-ids.py`

Mirror the AC/EX/CST machinery: collect `UM-*` clause IDs and the `Mediates:`/`Dispose:` headers;
verify each boundary entry's `Dispose:` cites a resolvable test ref (the lint already validates
*shape + traceability*, not runtime behavior — same 80/20 line as the existing checks). **Build on
PR #18's as-built** (the constraints lint extension is the closest template).

### 3d. "Validation, not certification" framing

Already promoted by the Exceptions/Constraints work. Add the user-mediation clause: the evaluate flow
detects each mediated boundary and verifies UM-1/2/3 hold, reporting by boundary; an **un-mediated
mutation/egress path is a silent conformance failure** — the dual of an undeclared Exception
(deviation) and an undeclared over-reach (constraint). The three backstops then form a complete set.

### 3e. SKILL flow steps (`pna-build-eval-contrib/SKILL.md`)

- **Build flow:** when adding any mutation or egress path, route it through the dispose gate; the
  proposer stages only.
- **Evaluate flow — new pass (after the exceptions + constraints passes):** for each mutation/egress
  boundary, confirm UM-1 (no bypass — try to actuate from a raw RPC / console, expect refusal), UM-2
  (the proposer can't self-commit), UM-3 (deterministic, human-readable, escaped diff). **Backstop:**
  find an un-mediated path and flag it. Report by boundary.

### 3f. `fellows_local_db` as the demonstrating reference design

- **(i) `docs/Architecture.md` § User-mediation attestation** — a new section listing fellows'
  mediated boundaries with their UM-1/2/3 evidence. **Starting evidence already exists** from #260:
  `test_worker_is_load_bearing_off_folder_via_raw_rpc` and `test_no_durable_private_write_when_browse_only`
  (UM-1 no-bypass, data-layer), the `mode=ro` MCP proofs (UM-2 separation: MCP stages, can't write),
  `test_groups_export.py` / `test_groups_compose.py` (UM-3 legibility before send). The **dispose-gate
  diff** boundary (UM-3 for AI-proposed writes) is the one that needs the AI-writes feature.
- **(ii) Reference-design record + Architecture.md copy** into `reference_designs/fellows_local_db/`.
- **Known gap to close first (#252):** private-data **restore** (`importRelationshipsBytes` wholesale
  replace) has far less "what is changing" legibility than AC-10 gives a directory import. It is the
  sibling boundary that does not yet meet the family's UM-3 bar — surface it honestly (attest the gap,
  or close it) rather than claiming uniform mediation.

---

## 4. Sequencing (test-first)

Stays a **scope in the fellows repo** until the maintainer approves. When approved:

1. **Write the three demonstrating tests** (UM-1 no-bypass, UM-2 separation, UM-3 legibility) against
   the mediated boundaries. Start from the #260 data-layer proofs (already green) as the UM-1 seed;
   the dispose-gate diff tests come with the AI-writes feature (gated — see §Dependencies). **This step
   defines the enforceable boundary; the spec text is written to match it.**
2. **Audit every inbound/egress boundary** against the invariant (the known restore-legibility gap +
   any others). Close or honestly attest each.
3. **Pin the workspace-AI stance** (any in-workspace AI is a proposer, never an actuator) with a
   frontier — *before* local-AI / `window.ai` lands.
4. **Attest in fellows' `docs/Architecture.md`** § User-mediation, every boundary citing a live test.
   Run `tests/test_attestation_has_evidence.py` + the conformance report.
5. **Run the SKILL preflight** against fellows; iterate clean.
6. **Draft + author the PNT changes** (§3a–3f) on a PNT branch, *now* that the tests have proven the
   boundary — reconcile against PR #18's as-built machinery. Run `tools/lint-spec-ids.py` green.
7. **Only on the maintainer's explicit go-ahead:** open the PNT PR. Version bump **Minor** (additive).

**Dependencies / gate:** the flagship demonstration (the AI propose/dispose diff) needs the AI-writes
feature ([`ai_write_proposals_groups.md`](ai_write_proposals_groups.md), plan #254 merged, **feature
unbuilt**). **Maintainer decision (§5):** demonstrate now via #260's existing no-bypass/separation
proofs as the minimum viable demonstration, or wait for the AI-writes dispose gate to demonstrate the
full propose→diff→dispose loop.

**Explicit decision recorded here:** no issues or PRs are filed into PNT from this scope. This
document is the artifact the maintainer reviews; everything downstream waits on approval and on the
tests landing first.

---

## 5. Open questions / terminology notes

1. **Mechanism name + ID prefix.** Working name "user-mediation / informed-actuation"; working clause
   prefix `UM-*`. Alternatives: `MED-*`, `ACT-*` (actuation). The metaphor to lead with: **separation
   of duties / dual control** (the proposer cannot self-approve) — confirm vs the
   runtime-error (Exceptions) / compile-time-error (Constraints) pairing.
2. **One invariant vs a registry.** Recommend: the spec defines **one** invariant with `UM-1..UM-3`
   clauses; reference designs register their **mediated-boundary list**. Confirm this asymmetry with
   the EX/CST registries is acceptable (it mirrors "the invariant is universal; the boundaries are
   per-design").
3. **Standalone `spec/user_mediation.md` vs folding into `PNA_Spec.md`.** It is arguably more
   *foundational* than EX/CST (it underlies the whole AC-16/18/19/10/PRM family), which argues for a
   prominent home in `PNA_Spec.md` rather than a sibling file. Maintainer's call; recommend a sibling
   file + a prominent `PNA_Spec.md` pointer (parallels axes/use_cases/exceptions/constraints).
4. **Demonstrate-now vs wait-for-AI-writes** (the §4 gate). Recommend: stage the spec now, demonstrate
   the **minimum** (UM-1/UM-2 via #260's proofs + UM-3 via export/compose) immediately, and add the
   AI-propose/dispose boundary as a second attested boundary when the feature ships — rather than
   blocking the whole mechanism on unbuilt feature work.
5. **The comprehension bound — how loudly to state it.** The mechanism's honesty rests on *not*
   claiming comprehension. Recommend the spec states the bound **normatively** ("a handler MUST NOT
   imply the user comprehended; it attests separation + legibility + attribution only"), so a future
   design can't quietly over-claim — the dual of EX-H5's "reversibility is mode-only, MUST NOT imply
   undo."
6. **Reconcile against the merged Exceptions + Constraints as-built.** Both already landed upstream
   (Constraints via PR #18; Exceptions iterated to EX-H8) and share the `PNA-DEFINITION` sentinel, the
   validation-not-certification framing, and the lint header-tracing pattern. This contribution MUST
   build on that, not re-add it. Read `spec/exceptions.md` + `spec/constraints.md` +
   `tools/lint-spec-ids.py` on PNA Toolkit `origin/main` before drafting §3c/§3d.
