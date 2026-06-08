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
| 1 | **Exceptions** (`EX-*`) | a deviation the **user raises** and the app handles (exits PNA mode) | cloud-LLM finding (2026-05-30) | ✅ **MERGED** — PNA Toolkit main (evolved to EX-H1..H8) |
| 2 | **Constraints** (`CST-*`) | a ceiling the **platform imposes** and the app handles (stays in PNA mode) | PWA-private-store finding (2026-06-01) | **MERGED** — PNT PR #18 |
| 3 | **User-mediation** (working name) | the **human is the actuator**; the proposer stages, the human disposes | actuation-surface finding (2026-06-07) | spec **not filed** — scope staged, gated |

Plus one **finding/principle** (not a new mechanism) that updates an existing constraint's frontier:

| Finding | Principle | Feeds | Status |
|---|---|---|---|
| **EAR decision** (#258) | encrypt the artifact that **crosses a trust boundary**, not the store behind your own OS | `CST-PWA-NO-SYNC` / `CST-PWA-PRIVATE-SNAPSHOT` frontier (encrypt-then-email candidate) | recorded in fellows; upstream = frontier-note follow-up, gated on #257 |

---

## 1. Exceptions — ✅ ALREADY MERGED UPSTREAM (nothing to file)

> **Correction (2026-06-08, verified against PNA Toolkit `origin/main`).** An earlier draft of this
> map said "ready to file." That was **wrong** — it trusted the fellows-side plan's stale status
> instead of checking PNT main, where Exceptions was already merged (likely by the PNT agent).
> **Do not file it — that would duplicate merged work.**

- **Plan:** [`pna_toolkit_exceptions_contribution.md`](pna_toolkit_exceptions_contribution.md) — now marked HISTORICAL.
- **What is on PNT main:** `spec/exceptions.md` (concept + handler contract + `EX-CLOUD-LLM` registry), the `tools/lint-spec-ids.py` EX/Relaxes/Reversible checks (incl. the EX-H8 strength-class check), and the `reference_designs/fellows_local_db/Architecture.md` Exception-attestation copy. Initial filing `67d4622`, since iterated.
- **Evolved beyond our plan:** the handler contract is now **EX-H1..EX-H8** (our plan stopped at EX-H7) — adds a per-dimension **strength profile** (EX-H8), a **fail-closed EX-H7** RFC, EARL-style per-clause predicate reporting, and a "Personal Network Toolkit → PNA Toolkit" rename. The upstream version is *ahead* of the fellows-side draft, not behind.
- **Fellows demonstrating design:** complete — `EX-CLOUD-LLM` handler shipped in **PR #226**, **#156 closed**, `docs/Architecture.md` rates it **conformant** with live e2e evidence. The PNT reference-design Architecture.md copy already carries the EX-H1..H8 attestation.
- **The only residual (and it is a *Constraints* item, not Exceptions):** the PNT reference-design `Architecture.md` copy is ~29 lines behind fellows' current `docs/Architecture.md` — it predates #260's data-layer-guard evidence on `CST-PWA-PRIVATE-SNAPSHOT` / `CST-PWA-STORAGE-EVICTABLE`. See §2 — this is the optional low-priority sync.

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

1. **Exceptions** — ✅ **already merged; nothing to file.** (Was listed "file next" in the first draft of this map — corrected.)
2. **Reference-design `Architecture.md` sync** (optional, low priority) — refresh the PNT copy of fellows' `docs/Architecture.md` with #260's strengthened `CST-PWA-*` evidence (and any other drift; the PNT copy is ~29 lines behind). This is the one concrete upstream action currently available, and it is a **Constraints**-side sync.
3. **User-mediation** — not yet. Write the demonstrating tests first (gated on the AI-writes feature, or on accepting #260's existing no-bypass proofs as the minimum demonstration); attest; *then* draft the spec. The plan holds the scope until then. (Verified absent from PNT main 2026-06-08.)
4. **EAR frontier note** — fold into a constraints follow-up once #257 lands an encrypted-export to demonstrate it.

## Cross-cutting reconciliation note

All three mechanisms were planned to share machinery, and **both Exceptions and Constraints have now landed upstream** (Constraints via PR #18; Exceptions iterated to EX-H8) — they already share the `PNA-DEFINITION` sentinel, the validation-not-certification framing, and the lint header-tracing pattern. The only remaining new mechanism, **User-mediation**, must therefore **build on the merged Exceptions + Constraints as-built** (read `spec/exceptions.md` + `spec/constraints.md` + `tools/lint-spec-ids.py` on PNT main before drafting), not re-introduce that machinery.

> **Methodology note (why this map was wrong once).** The first draft (2026-06-08) staged statuses from the fellows-side `plans/*.md` banners, which lag the PNT agent's actual filings. **Always verify contribution status against PNA Toolkit `origin/main` (the spec files + lint), not the fellows-side plan**, before recommending a filing action.
