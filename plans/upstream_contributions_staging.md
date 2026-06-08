# Upstream contributions — staging map (fellows_local_db → PNT)

> **What this is.** A single hand-off map of every PNT contribution that `fellows_local_db` is the
> demonstrating reference design for: current status, what's done on the fellows side, what remains
> upstream, dependencies, and the recommended filing order. The orchestrator drives the PNT agent
> from this; the per-contribution detail lives in the linked plan files.
>
> **Working model:** fellows is the *demonstrating design* + *staging ground*; a separate agent
> executes the actual edits in the [`personal_network_toolkit`](https://github.com/richbodo/personal_network_toolkit)
> (PNT) repo. Nothing here files into PNT without the maintainer's explicit go-ahead.
>
> Local paths: PNT repo `~/src/personal_network_toolkit`; this repo `~/src/fellows_local_db`.
> _Last staged: 2026-06-08._

---

## The matched set

The toolkit gains three **general mechanisms**, each discovered by building fellows and each riding
upstream with fellows as its demonstrating design. They are duals/siblings and share machinery
(`lint-spec-ids.py` header tracing, the `PNA-DEFINITION` sentinel, the validation-not-certification
framing, the three-layer lint/evaluate/human split):

| # | Mechanism | What it names | Origin | PNT status |
|---|---|---|---|---|
| 1 | **Exceptions** (`EX-*`) | a deviation the **user raises** and the app handles (exits PNA mode) | cloud-LLM finding (2026-05-30) | spec **not filed** — ready |
| 2 | **Constraints** (`CST-*`) | a ceiling the **platform imposes** and the app handles (stays in PNA mode) | PWA-private-store finding (2026-06-01) | **MERGED** — PNT PR #18 |
| 3 | **User-mediation** (working name) | the **human is the actuator**; the proposer stages, the human disposes | actuation-surface finding (2026-06-07) | spec **not filed** — scope staged, gated |

Plus one **finding/principle** (not a new mechanism) that updates an existing constraint's frontier:

| Finding | Principle | Feeds | Status |
|---|---|---|---|
| **EAR decision** (#258) | encrypt the artifact that **crosses a trust boundary**, not the store behind your own OS | `CST-PWA-NO-SYNC` / `CST-PWA-PRIVATE-SNAPSHOT` frontier (encrypt-then-email candidate) | recorded in fellows; upstream = frontier-note follow-up, gated on #257 |

---

## 1. Exceptions — READY TO FILE (fellows side complete)

- **Plan:** [`pna_toolkit_exceptions_contribution.md`](pna_toolkit_exceptions_contribution.md) (§3a–3f are execute-ready DRAFTs).
- **Demonstrating design:** shipped. `EX-CLOUD-LLM` handler (consent gate + "Going rogue" banner + `#/exception/<id>` explainer + return-to-PNA control + `<body data-pna-mode>` marker) landed in **PR #226**; issue **#156 closed** as done. EX-H7 propagation notice ships in the MCP `instructions` (`CLOUD_LLM_PROPAGATION_NOTICE`).
- **Attestation:** `docs/Architecture.md` § Exception attestation is built; the conformance report rates `EX-CLOUD-LLM` **conformant** with live e2e evidence (`tests/e2e/test_pna_exception_mode.py`, `test_mcpb_settings.py`, `tests/test_private_data_ops.py::test_instructions_carry_cloud_llm_propagation_notice`).
- **What this changes vs the plan as written:** the plan's §3f *gap analysis* (no AC attestation table, handler unbuilt, status `planned`) and *sequencing* steps 1–3 ("build handler first, backfill attestation, preflight") are **DONE**. The plan's status banner is now stale and has been refreshed — see its header.
- **Remaining work — all upstream, all in PNT:**
  1. `spec/exceptions.md` (concept + EX-H1..H7 handler contract + `Relaxes:`/`Reversible:` headers + `EX-CLOUD-LLM` registry entry) — §3a.
  2. One-line `PNA_Spec.md` pointer (vocab-pna) — §3b.
  3. `tools/lint-spec-ids.py` EX/Relaxes/Reversible checks — §3c.
  4. "Validation, not certification" framing promotion — §3d.
  5. SKILL Evaluate-flow exceptions pass — §3e.
  6. `reference_designs/fellows_local_db/` design-record bullet + Architecture.md copy + EX attestation — §3f.
- **Dependencies:** none blocking. Shares the `PNA-DEFINITION` sentinel + framing callout with Constraints — **but Constraints already merged (PR #18)**, so that machinery is already upstream. Confirm whether PR #18 introduced `PNA-DEFINITION` / the framing callout already (likely) so Exceptions doesn't re-add them; reconcile against PR #18 as-built.
- **Open questions for the maintainer:** §5 of the plan (handler-clause IDs `EX-H*`, `PNA-DEFINITION` vs `AC-PNA`, pointer placement). Several may already be settled by how PR #18 landed.
- **Version bump:** Minor (additive).

## 2. Constraints — DONE (merged upstream)

- **Plan:** [`pna_toolkit_constraints_contribution.md`](pna_toolkit_constraints_contribution.md).
- **Status:** **MERGED** — PNT PR #18 *"spec: add Constraints concept (CST-*)"* (merged 2026-06-03). `spec/constraints.md`, the lint CST checks, the `PNA_Spec.md`/`axes.md` pointers, the SKILL build+evaluate steps, and the fellows reference-design record + § Constraint attestation are upstream.
- **Fellows side:** § Constraint attestation in `docs/Architecture.md` is live and conformant; #260 just **strengthened** two rows (`CST-PWA-PRIVATE-SNAPSHOT`, `CST-PWA-STORAGE-EVICTABLE`) to cite the data-layer no-bypass guards. Those strengthenings are *newer than PR #18* — the PNT copy of fellows' Architecture.md may want a refresh at the next sync (low priority; additive evidence, no semantic change to the constraints).
- **Remaining:** nothing required. The plan's status banner still reads "FILED … pending maintainer merge" — stale; refreshed to MERGED.

## 3. User-mediation — SCOPE STAGED, GATED (test-first)

- **Plan:** [`pna_toolkit_user_mediation_contribution.md`](pna_toolkit_user_mediation_contribution.md) (NEW — scoping depth, not an execute-ready spec draft, by design).
- **Tracking issue:** **#252** — *"Workspace user-mediation invariant: name it, test it (test-first), then spec it."*
- **The mechanism (working name "user-mediation" / "informed-actuation"):** *the human is the actuator; the workspace is the locus of ground truth.* Every path that mutates the sovereign store or sends data out of it routes through a user-legible review in a surface the user controls; the proposer (AI / network / importer) only **stages**, the human **disposes**. Already load-bearing across AC-19/AC-16/AC-MCP-B/AC-10/AC-PRM-D/AC-PRM-A.
- **Why it is NOT yet a full spec draft (deliberate):** #252's central discipline is **test-first**. The enforceable claim is bounded to *separation + legibility + attribution* — **not comprehension** (you cannot test "a human understood"; that is the liveness arms race). Drafting the spec before the demonstrating tests exist risks an unenforceable "user MUST comprehend" line that `test_attestation_has_evidence.py` would reject. So the plan scopes the mechanism and the test-first sequence; the spec text is drafted *after* the tests prove the boundary.
- **Demonstrating design — GATED on the AI-write-proposals feature:** the cleanest demonstration is the propose/dispose MCP flow in [`ai_write_proposals_groups.md`](ai_write_proposals_groups.md) (plan **#254 merged**, *feature not built*). The #260 data-layer-enforcement proofs (`test_worker_is_load_bearing_off_folder_via_raw_rpc`, `test_no_durable_private_write_when_browse_only`, the `mode=ro` proofs) are the *same family* of negative-invariant test and the starting evidence, but the dispose-gate tests proper require the AI-writes feature.
- **Remaining work (sequenced in the plan):** (a) write the three demonstrating tests (no-bypass / separation / legibility); (b) audit every inbound/egress boundary (known gap: private-data **restore** legibility, vs AC-10's directory-import preview); (c) pin the workspace-AI stance before local-AI/`window.ai` ships; (d) attest in `docs/Architecture.md`; (e) THEN draft the PNT spec mechanism mirroring the matched set.
- **Dependencies:** the AI-writes feature (for the flagship demonstration) and/or accepting #260's existing data-layer proofs as the minimum demonstration. Maintainer's call on whether to demonstrate via the existing no-bypass proofs now or wait for the AI-writes dispose gate.

## 4. EAR principle (#258) — FRONTIER FOLLOW-UP, GATED

- **Not a new mechanism** — a finding/principle: *encrypt what crosses a trust boundary, not the store behind your own OS.* Recorded in fellows via **PR #258** (`docs/ac_decisions_log.md`, `docs/Architecture.md` non-goal note, `docs/architectural_findings.md`).
- **Upstream shape:** a **frontier-note refinement** to the already-merged `spec/constraints.md` — sharpens the `CST-PWA-NO-SYNC` / `CST-PWA-PRIVATE-SNAPSHOT` "encrypt-then-email-to-self" candidate from "unproven idea" to the stated principle (encrypt the *transit artifact*, keep the live store tool-readable — which is *why* app-EAR-for-the-live-store was rejected, per #256).
- **Gated on #257** (*Explore: cross-device private data over commodity channels*): until the encrypted portable-export feature is decided/built, there is no demonstrating code, so this stays a principle note, not an attested handling. No standalone plan — tracked here + in the constraints plan's frontier rows.

---

## Recommended filing order (for the PNT agent)

1. **Exceptions** — file next. Fellows side is complete; it's the highest-value unfiled mechanism and completes the Exceptions/Constraints matched pair upstream. First reconcile against PR #18 as-built (don't re-add `PNA-DEFINITION` / the framing callout if PR #18 already introduced them).
2. **Constraints Architecture.md sync** (optional, low priority) — refresh the PNT copy of fellows' § Constraint attestation with #260's strengthened evidence at a convenient sync.
3. **User-mediation** — not yet. Write the demonstrating tests first (gated on the AI-writes feature, or on accepting #260's existing no-bypass proofs as the minimum demonstration); attest; *then* draft the spec. The plan holds the scope until then.
4. **EAR frontier note** — fold into a constraints follow-up once #257 lands an encrypted-export to demonstrate it.

## Cross-cutting reconciliation note

All three mechanisms were planned to share machinery that **Constraints (PR #18) has now landed first**: the `PNA-DEFINITION` sentinel, the validation-not-certification framing callout, and the lint header-tracing pattern. Every subsequent contribution (Exceptions, User-mediation) must **build on PR #18's as-built**, not re-introduce these. The Exceptions and User-mediation plans were written assuming Exceptions-first; that assumption is now inverted — reconcile each against the merged constraints work before executing.
