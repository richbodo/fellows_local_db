# Plan — The User-Mediation Arc: invariant → demonstrators → upstream contribution

> **Status: ARC SPINE. The MVD path (§3) is the PRIMARY route and is READY NOW.** This is the single
> source of truth for the user-mediation arc: one invariant (the third general PNT mechanism, dual to
> Exceptions and Constraints), demonstrated by **two reference designs already in hand**, then
> contributed upstream. The arc has two satellites: the **deferred richer demonstrator**
> ([`ai_write_proposals_groups.md`](ai_write_proposals_groups.md) — the fellows AI-writes feature, *not
> on the critical path*) and the **staging map**
> ([`upstream_contributions_staging.md`](upstream_contributions_staging.md)).
>
> **Test-first, by design.** Per the tracking issue (**#252**) the demonstrating tests define the
> enforceable boundary and the spec is written to match what proved testable — never the reverse
> (writing the spec first risks an unenforceable "user MUST comprehend" clause that
> `test_attestation_has_evidence.py` would correctly reject as evidence-free). §6 sketches the *shape*
> of the PNT artifacts; the normative text is drafted only after the MVD's tests/attestation land (§3).
>
> **Decision recorded (2026-06-08): demonstrate now via the MVD, defer the feature.** The minimum
> viable demonstration (§3) carries the mechanism upstream **without** building the fellows AI-writes
> feature, because PRM already supplies the half fellows' MVD lacks (§4). Nothing files into PNT
> without the maintainer's explicit go-ahead.
>
> Local paths: PNT repo `~/src/personal_network_toolkit`; demonstrating design (this repo)
> `~/src/fellows_local_db`; second demonstrator `~/src/prm`. The canonical lesson-learned is
> [`../docs/architectural_findings.md` § 2026-06-07](../docs/architectural_findings.md).

---

## 0. The arc at a glance

One mechanism, **two demonstrators already in hand**, one upstream contribution — the same shape that
landed Exceptions and Constraints, but with a stronger evidence base than either had (each of those
rode up on fellows alone).

**The demonstration ladder** — what proves the invariant:

| Demonstrator | Substrate | Covers | Status | Role |
|---|---|---|---|---|
| **fellows MVD** | `opfs-sqlite-wasm` | UM-1 no-bypass (data-layer), UM-2 separation (`mode=ro` + no write tools), UM-3 legibility for **egress** (export/compose) | tests **already green** (#260/#261 + groups export/compose) | **PRIMARY — §3** |
| **PRM** | `native-sqlite-via-filesystem` + daemon | UM-1 (FK + absent tool), UM-2 (propose-only MCP), UM-3 legibility for **mutation** (propose→diff→apply) | **built** (M2–M5 merged); attests at **M6** | second demonstrator — §4 |
| fellows AI-writes feature | `opfs-sqlite-wasm` | UM-3 legibility for **mutation** (a 3rd boundary) | planned, **unbuilt** | deferred richer demo — §5 |

**Why the MVD is sufficient without the feature.** The only gap in fellows' MVD — legibility of a
proposed *mutation* diff — is exactly what PRM's propose→apply loop already covers, on a *second*
storage substrate. Together fellows (egress) + PRM (mutation) cover UM-1/2/3 across two substrates: a
stronger demonstration than fellows-alone-with-feature, and it needs no new feature build. The
AI-writes feature becomes a *richer* third boundary to add later if it earns product value, not a
prerequisite for the mechanism.

**Sequencing summary** (full detail §7): **(A)** fellows MVD prep runs **now, in parallel** with the
toolkit's Tier-0 keystone (different repo, different owner; off the critical path). **(B)** PRM carries
a user-mediation boundary list into its M6 attestation. **(C)** after the keystone frees the toolkit
instance, draft the upstream contribution (§6) test-first, citing fellows **+** PRM; Minor bump.
**(D)** optional: build the fellows AI-writes feature later.

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
sub-contract clauses (working IDs `UM-1..UM-3`; naming is an open question, §8):

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
attestation commitment AND a candidate normative line for the spec; §8.)

---

## 3. The MVD path — PRIMARY, ready now

The minimum viable demonstration carries the invariant upstream using evidence fellows **already has
green**, plus one honest gap declaration. **No new feature.** This section is the fellows-instance task
list; it runs in parallel with the toolkit's Tier-0 keystone (§7) and is off the critical path.

### 3.0 Preconditions (already satisfied — verified 2026-06-08)

- **UM-1 (no-bypass):** `tests/e2e/test_private_data_enforcement.py::test_no_durable_private_write_when_browse_only`
  and `::test_worker_is_load_bearing_off_folder_via_raw_rpc` — green (PR #261 / #260, enforced at the
  worker/data layer, not UI-only).
- **UM-2 (separation):** `mcp_servers/private_data_ops.py` is `mode=ro` with **no** write tools
  (`list_groups` / `find_group` / `get_group_members` only); `tests/test_private_data_ops.py::test_read_only_enforcement`
  green. The MCP surface can stage/read, never commit.
- **UM-3 (legibility, egress):** `tests/e2e/test_groups_export.py`, `tests/e2e/test_groups_compose.py`
  — deterministic, human-readable (names, not `record_id`s), `escapeHtml` on untrusted strings.
- **Built upstream machinery to build on:** the merged `spec/exceptions.md` + `spec/constraints.md` +
  `tools/lint-spec-ids.py` on PNT `origin/main` — do **not** re-introduce the shared machinery (§8 Q6).

### 3.1 Frame the existing tests under UM-1/2/3

Re-label / cross-reference the green tests above as the UM-1 / UM-2 / UM-3(egress) evidence rows. **No
new test code** is required for these three; this is the mapping that makes the attestation legible.

### 3.2 Boundary audit (the one piece of real work)

Enumerate every mutation/egress boundary and confirm UM-1/2/3 or honestly attest the gap. Known
boundaries: create/edit group, `group_members` add/remove, mailto-stage (AC-MCP-B), directory
re-import (AC-10), **private-data restore** (`importRelationshipsBytes`), export (PR-6).

- **Restore is the known gap.** Off-folder it now *refuses* (UM-1 holds — PR #261), but in folder mode
  its "what is changing" legibility is weaker than AC-10's orphan preview gives a directory import.
  **Attest the gap honestly; do NOT block on closing it.** The closure decision is tracked in **#259**
  (off-folder durability model + Restore-affordance tidy), explicitly *deferred / not urgent*. Cite
  #259 as the frontier. This is exactly the EX-H7-style "conformant for the mechanical half, gap named"
  honesty. (Note: #259 also flags a *visible-but-erroring* Restore button off-folder — a cosmetic-half
  issue to mention but not gate on.)

### 3.3 Pin the workspace-AI frontier stance

Record in `docs/Architecture.md`, *before* local-AI / `window.ai` lands: **any in-workspace AI is a
proposer subject to the dispose gate, never an actuator.** A frontier line, not a closed guarantee (§2).

### 3.4 Attest in fellows `docs/Architecture.md` § User-mediation

New section: the mediated-boundary list, each row citing a live test (UM-1/2/3) or an honestly-named
gap (#259). Run `tests/test_attestation_has_evidence.py` + the conformance report; keep the `just` gate
green.

### 3.5 SKILL preflight

Run the toolkit's evaluate/preflight flow against fellows; iterate until clean.

### Exit criteria (MVD done)

fellows attests a user-mediation boundary list with green UM-1/2/3 evidence + an honestly-named restore
gap (#259). At this point the invariant is *demonstrated*; §7 Step C drafts the spec to match.

---

## 4. PRM — the built second demonstrator

PRM (`~/src/prm`) already implements the same invariant on a *different* substrate
(`native-sqlite-via-filesystem` + local daemon): its v0.1 spine is "AI deduplicates via **propose →
review → apply**: the AI stages a merge changeset, the human reviews and applies" (PRM
`docs/roadmap.md`, `plans/v0.1-implementation-plan.md`), realizing the proposed AC-PRM-E/F ("MCP
stages, workspace applies"). M2–M5 are merged; the proposal-review UI exists.

- **It covers the half fellows' MVD lacks:** UM-3 legibility for a proposed **mutation** diff.
- **It rides up at PRM M6.** PRM's M6 attestation already carries the distribution-axis split (#39 /
  prm#8); add a **user-mediation boundary list** alongside it. The upstream contribution then cites
  *two* designs across *two* substrates.
- **Verify when attesting — don't over-claim now.** Confirm PRM's apply UI renders a deterministic,
  human-readable, escaped diff before the dispose action — i.e. that it actually meets UM-3, not merely
  "has an apply step." State it as a check to perform, not a settled fact, until the test is cited.

---

## 5. The deferred richer demonstrator — fellows AI-writes feature

[`ai_write_proposals_groups.md`](ai_write_proposals_groups.md) (plan #254 merged, **feature unbuilt**)
would add a *third* mediated boundary: AI-proposed writes to `groups` / `group_members` via a
folder-resident inbox, applied only by the worker after a workspace diff review. It is the cleanest
single-design propose→diff→dispose loop, but it is **no longer on the mechanism's critical path** — the
MVD (§3) + PRM (§4) already carry the upstream case. Build it later only if it earns product value on
its own; when it lands, add it as another attested boundary row in the fellows attestation. That plan
now carries a DEFERRED banner pointing here.

---

## 6. Proposed PNT artifacts (SHAPE ONLY — normative text drafted from the tests)

Mirrors the matched set's structure. **None of the normative text below is final**; it is drafted after
§3 (the MVD path), to match what the tests prove.

### 6a. NEW file: `spec/user_mediation.md` (or fold into an existing spec section — §8)

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

### 6b. Header conventions (mirroring `Relaxes:`/`Triggered-by:`)

- **`Mediates:`** — on a reference-design boundary entry, names what crosses the gate: a mutation of
  the sovereign store, or an egress of its data. Token form TBD from the tests (likely `mutation:<op>`
  / `egress:<transport>`).
- **`Proposer:`** — names the staging surface that has *no* actuation authority for this boundary
  (e.g. `mcp-inbox`, `network-import`, `in-workspace-ai`).
- **`Dispose:`** — names the attributable authorization surface + the test ref that proves UM-1/2/3.

### 6c. Extend `tools/lint-spec-ids.py`

Mirror the AC/EX/CST machinery: collect `UM-*` clause IDs and the `Mediates:`/`Dispose:` headers;
verify each boundary entry's `Dispose:` cites a resolvable test ref (the lint already validates
*shape + traceability*, not runtime behavior — same 80/20 line as the existing checks). **Build on
PR #18's as-built** (the constraints lint extension is the closest template).

### 6d. "Validation, not certification" framing

Already promoted by the Exceptions/Constraints work. Add the user-mediation clause: the evaluate flow
detects each mediated boundary and verifies UM-1/2/3 hold, reporting by boundary; an **un-mediated
mutation/egress path is a silent conformance failure** — the dual of an undeclared Exception
(deviation) and an undeclared over-reach (constraint). The three backstops then form a complete set.

### 6e. SKILL flow steps (`pna-build-eval-contrib/SKILL.md`)

- **Build flow:** when adding any mutation or egress path, route it through the dispose gate; the
  proposer stages only.
- **Evaluate flow — new pass (after the exceptions + constraints passes):** for each mutation/egress
  boundary, confirm UM-1 (no bypass — try to actuate from a raw RPC / console, expect refusal), UM-2
  (the proposer can't self-commit), UM-3 (deterministic, human-readable, escaped diff). **Backstop:**
  find an un-mediated path and flag it. Report by boundary.

### 6f. Demonstrating reference designs

- **(i) fellows `docs/Architecture.md` § User-mediation attestation** — the mediated-boundary list with
  UM-1/2/3 evidence. **Starting evidence already exists** (§3.0): the #260/#261 data-layer no-bypass
  proofs (UM-1), the `mode=ro` MCP proofs (UM-2), `test_groups_export.py` / `test_groups_compose.py`
  (UM-3 legibility before send / egress). The mutation-diff legibility boundary is supplied by **PRM**
  (§4), not by an unbuilt fellows feature.
- **(ii) PRM** — its M6 attestation carries a user-mediation boundary list for the mutation side (§4).
- **(iii) Reference-design records + Architecture.md copies** into `reference_designs/<design>/` for
  each, per the contribute flow.
- **Known gap to attest (not close):** private-data **restore** legibility vs AC-10's directory-import
  preview — surfaced honestly, frontier = #259 (§3.2).

---

## 7. Sequencing — MVD-primary

Dependency-ordered, not calendar-ordered. The MVD prep (Step A) is **off the critical path** and runs
now in parallel with the toolkit's keystone; the upstream draft (Step C) waits for toolkit-instance
bandwidth, not for any hard dependency.

- **Step A — fellows MVD prep (now; owner: fellows instance; parallel to the Tier-0 keystone).**
  Execute §3 (3.1–3.5). Output: a green user-mediation attestation in fellows + an honestly-named
  restore gap (#259).
- **Step B — PRM second demonstrator (with PRM M6; owner: prm instance).** Add a user-mediation
  boundary list to PRM's M6 attestation (§4). Output: a second design, second substrate.
- **Step C — upstream contribution (after the Tier-0 keystone frees the toolkit instance; owner:
  toolkit instance).** Draft §6 **test-first**, to match what A/B proved: `spec/user_mediation.md`
  (or a prominent `PNA_Spec.md` section), the `lint-spec-ids.py` `UM-*` / `Mediates:` / `Proposer:` /
  `Dispose:` machinery built on PR #18's as-built, the SKILL build+evaluate steps, the
  validation-not-certification clause. Cite fellows **+** PRM. **Minor** version bump (additive).
  **File only on the maintainer's explicit go-ahead.**
- **Step D — optional richer demo (later).** Build the fellows AI-writes feature (§5) if it earns its
  keep; add it as another attested boundary.

**Hard dependencies:** Step C builds on the merged Exceptions + Constraints (done). **Soft sequencing:**
C benefits from B (dual demonstrator) but fellows' MVD alone could carry it if PRM M6 slips. No PNT
issues/PRs are filed from this scope until Step C, on the maintainer's explicit go-ahead. This document
is the artifact the maintainer reviews.

---

## 8. Open questions / terminology notes

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
4. **Demonstrate-now vs wait-for-AI-writes.** **RESOLVED (2026-06-08): demonstrate now.** The MVD (§3)
   + PRM (§4) carry the upstream case across two substrates without the fellows AI-writes feature,
   which is deferred (§5). This removes the unbuilt feature from the critical path; the AI-propose/
   dispose boundary is added later as another attested boundary if the feature ships.
5. **The comprehension bound — how loudly to state it.** The mechanism's honesty rests on *not*
   claiming comprehension. Recommend the spec states the bound **normatively** ("a handler MUST NOT
   imply the user comprehended; it attests separation + legibility + attribution only"), so a future
   design can't quietly over-claim — the dual of EX-H5's "reversibility is mode-only, MUST NOT imply
   undo."
6. **Reconcile against the merged Exceptions + Constraints as-built.** Both already landed upstream
   (Constraints via PR #18; Exceptions iterated to EX-H8) and share the `PNA-DEFINITION` sentinel, the
   validation-not-certification framing, and the lint header-tracing pattern. This contribution MUST
   build on that, not re-add it. Read `spec/exceptions.md` + `spec/constraints.md` +
   `tools/lint-spec-ids.py` on PNA Toolkit `origin/main` before drafting §6c/§6d.
