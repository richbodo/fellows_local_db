# EPIC — Private-Data Capability Gate + Mobile Rebuild (the controller)

**Status:** NEARLY COMPLETE. **Created:** 2026-06-02. All in-app work landed: gate #235, unlock/probe/chooser #237, follow-ups #239, migration #240, mobile browse-only rebuild #241, and the **private-data enforcement** detour #244 (`d2706a9`) that closed the deferred data-layer write-refusal gap (`tests/e2e/test_private_data_enforcement.py`; `docs/Architecture.md` CST rows reconciled to `conformant`). The only remaining tail is **C4 — the upstream PNT constraints contribution** (Phase 4, maintainer-gated).
**This file does not restate the child plans — it sequences them, declares the dependency graph and file-ownership lanes, defines integration checkpoints, and tracks status.** Read the children for the *what*; read this for the *order* and the *how-to-parallelize*.

## Children (the cluster this controls)

| # | Plan | Role | State |
|---|---|---|---|
| C1 | [`private_data_capability_gate.md`](private_data_capability_gate.md) | **Trunk.** Folder-gated private data; browse-only everywhere else. The feature-gating lives here. | not started |
| C2 | [`mobile_redesign/PLAN_mobile_no_groups.md`](mobile_redesign/PLAN_mobile_no_groups.md) | Phone realization of browse-only mode + the `is-phone` layout (scroll/hamburger/CTAs/settings). | not started |
| C3 | `docs/feature_platform_matrix.md` (rewrite) | The "what works where" truth. Currently says *groups work everywhere* — the gate makes that false. Rewrite is a DOCS-lane deliverable. | stale, contradicts C1 |
| C4 | [`pna_toolkit_constraints_contribution.md`](pna_toolkit_constraints_contribution.md) | Upstream PNT PR. **Depends on building C1 first** (implement → learn → contribute). | PLAN ONLY, maintainer-gated |
| C5 | [`pna_toolkit_exceptions_contribution.md`](pna_toolkit_exceptions_contribution.md) | Upstream PNT PR (in-app `EX-CLOUD-LLM` already shipped; only the contribution is pending). | PLAN ONLY, maintainer-gated |

Already shipped and assumed as foundation (do not re-do): `user_folder_storage.md` (folder mode, PRs #181/#190/#191/#205/#209), `local_first_worker_architecture.md` Phases 1–5, `pre_ship_ui_fixes_2026-05-29.md` (PR #223). The pre-ship plan's #206 mobile baselines **will be redone** by C2 — expected.

## Dependency graph

```
                 ┌─────────────────────────────────────────────┐
                 │ Phase 0  analysis fan-out (read-only)        │  ← parallel, no isolation needed
                 └─────────────────────────────────────────────┘
                                     │ freezes the RPC contract + class names + edit-site map
                                     ▼
                 ┌─────────────────────────────────────────────┐
                 │ Phase 1  KEYSTONE  C1 PR1+PR2                 │  ← sequential, single owner of app.js core
                 │   gate resolver · body classes · shared-mode │
                 │   = localStorage-only · same-browser migrate │
                 └─────────────────────────────────────────────┘
                                     │ (merged to the epic feature branch)
        ┌───────────────┬───────────┴───────────┬───────────────┬──────────────┐
        ▼               ▼                        ▼               ▼              ▼
  Lane CORE       Lane WORKER              Lane STYLE       Lane DOCS      Lane TESTS
  (app.js)        (sqlite-worker.js)       (css+html)       (docs/*)       (tests/e2e/*)
  C1 PR3→PR4→PR5  probe·chooser·identity   C2 layout +      C3 + all C1    scaffolds vs
  →C2 app-half    ·migrate-copy backends   grayed/CTA css   doc deltas     Phase-0 spec
        └───────────────┴───────────┬───────────┴───────────────┴──────────────┘
                                     ▼
                 ┌─────────────────────────────────────────────┐
                 │ Phase 3  integration (sequential)            │  ← merge lanes, full suite,
                 │   resolve app.js↔css↔worker seams · re-base   │     re-baseline mobile snapshots LAST
                 └─────────────────────────────────────────────┘
                                     ▼
                 ┌─────────────────────────────────────────────┐
                 │ Phase 4  contribute upstream (maintainer-go) │  ← C4 (+C5), after real-device learning
                 └─────────────────────────────────────────────┘
```

The hard rule the whole graph obeys: **`app.js` is a single IIFE (CLAUDE.md: no modules/classes) → it has exactly one owner (Lane CORE) and is never split across concurrent agents.** Everything else parallelizes around it against frozen interfaces.

## Phases

### Phase 0 — analysis fan-out (read-only)
Five independent agents produce findings, no edits, nothing to isolate, nothing to coordinate → **plain parallel fan-out; no worktrees, no inter-agent comms.** Deliverables, which *freeze the interfaces* the lanes build against:
1. **Surface inventory** — every private-data render/wire site in `app.js`/`index.html`, with the gate each needs (`hidden` on phone vs `grayed+CTA` on desktop).
2. **Worker↔page RPC contract** — current RPCs + the new ones: folder probe, scan-all-`Fellows*` chooser, in-db identity read/write, OPFS→folder migrate-copy. Names, params, returns, `WORKER_RPC_VERSION` bump.
3. **Mockup→CSS/DOM map** — `mockups_no_groups/` → `styles.css`/`index.html`: classes to port + the DOM hooks `app.js` must emit.
4. **Test-gap audit** — existing e2e that breaks under the gate; new tests (lock/unlock, probe-failure, migration, chooser, reconnect); honors the port-8765 serialization rule.
5. **Docs rewrite outline** — C3 contradictions + the full doc delta (matrix, users_manual, browser_support, Architecture constraint attestation, persistence_and_upgrades, the troubleshooting page keyed by probe `reason` codes).

### Phase 1 — keystone (sequential)
C1 PR1 (gate foundation: `privateDataEnabled()`, `body.no-private-data`/`body.is-phone`, shared-mode = localStorage-only, `window.__privateDataTier`) + PR2 (same-browser OPFS→folder migration). **Single owner.** Must land together — the migration protects existing Chrome users the moment the gate bites.

### Phase 2 — lane fan-out (parallel worktrees, against the frozen Phase-0 interfaces)
| Lane | Owns (files) | Work | Parallel? |
|---|---|---|---|
| **CORE** | `app/static/app.js` | C1 PR3 gating → PR4 unlock → PR5 reconnect → C2 app-half | critical path, **sequential, single owner** |
| **WORKER** | `app/static/vendor/sqlite-worker.js` | probe backend, chooser scan, identity stamp, migrate-copy | ✅ vs CORE (RPC contract) |
| **STYLE** | `app/static/styles.css`, `app/static/index.html` | C2 scroll/drawer/CTA + grayed-out styles, mockup port | ✅ (class/DOM-id contract) |
| **DOCS** | `docs/*`, troubleshooting page | C3 + all C1/C2 doc deltas | ✅ fully parallel |
| **TESTS** | `tests/e2e/*` | scaffold vs Phase-0 spec; finalize after features | ✅ (baselines deferred to Phase 3) |

### Phase 3 — integration (sequential)
Merge lanes onto the epic branch, resolve the `app.js`↔css↔worker seams, run the full suite, **re-baseline mobile snapshots last** (pixels move until the UI is final — the pre-ship plan's own hard-won rule).

### Phase 4 — contribute upstream (maintainer-gated)
C4 constraints PR (+ C5 exceptions if not yet filed), sharpened by what Phase 1–3 taught us: `CST-PWA-PRIVATE-SNAPSHOT` handling/Detectability, `CST-PWA-STORAGE-EVICTABLE` (avoided, not just mitigated), `CST-PWA-NO-SYNC` (in-db identity answers "which copy is canonical"). No PNT PRs until the maintainer says go.

## Concurrency model (worktrees + agents)

- **One worktree per *lane*, not per PR.** Splitting `app.js` across worktrees = merge pain; splitting by file ownership = clean merges. Lanes WORKER/STYLE/DOCS/TESTS get their own worktree + branch; CORE stays on the epic feature branch.
- **Worktree setup:** `git worktree add ../fellows-wt-<lane> -b <lane-branch>` then `scripts/wt-setup.sh ../fellows-wt-<lane>` to symlink `.venv` + `app/fellows.db` (+ `mcp_servers/.venv`) so the worktree is test-ready instantly. Playwright browsers are a per-user global cache, shared once `.venv` is linked.
- **Port 8765 is a global singleton (CLAUDE.md).** Server-based test runs (`just test-api`/`test-e2e`/`test-mobile`) in two worktrees at once collide. **Serialize server-based test execution across lanes**; only `tests/test_database.py` (no server) is parallel-safe. This — not raw agent count — is the real cap on concurrent verification.
- **Inter-agent comms: not needed for fan-out.** Phase 0 and the Phase-2 lanes are *independent against frozen interfaces*; agents return findings/diffs to the orchestrator, which integrates. Reserve `SendMessage`-style coordination for the rare case where a lane discovers the frozen interface is wrong and the contract must change mid-flight — cheaper to let the orchestrator re-freeze and re-dispatch than to have lanes negotiate.
- **Honest ceiling:** the speedup comes from offloading WORKER/STYLE/DOCS/TESTS while CORE proceeds — *not* from parallelizing `app.js`. Don't expect linear scaling; the single-file frontend + single test port bound it.

## Status

| Item | Phase | State | Notes |
|---|---|---|---|
| `scripts/wt-setup.sh` | infra | ✅ done | worktree env-share helper |
| Phase 0 analysis fan-out | 0 | ✅ done | 5 agents → [`EPIC_phase0_findings.md`](EPIC_phase0_findings.md) (frozen interfaces) |
| C1 **PR1** gate plumbing | 1 | ✅ done | `privateDataEnabled()`, `body.is-phone`/`no-private-data`, `window.__privateDataTier`; **inert** (nothing consumes the classes yet). Verified: `node --check` OK, `just test-fast` 96✓, `test_directory.py` 4✓ |
| C1 **PR1 timing fix** | 1 | ✅ done | gate re-resolves at `provider_ready` (was stranding folder users in browse-only); diagnosed via runtime probe |
| C1 **PR3** desktop surface gating | 2 | ✅ done | `worker_data_folder`/`folder_attached_page` fixtures + `attach_verified_folder`; group/copy suite migrated to folder; desktop entry-point + composer-rail CSS gate (`no-private-data:not(.is-phone)`); `route()` group-route redirect→Settings (desktop, gate-resolved). **Full `just test`: 636 passed / 6 skipped / 0 failed.** |
| DOCS lane (PR7-docs) | 2 | ✅ done | 6 docs rewritten/created for the gate (pending maintainer review) |
| C1 **PR4** + **PR5** unlock/probe/chooser/identity | 2 | ✅ done | **PR #237** (merged) — staged empirical probe + reason codes, unlock UI, "Lock my private data", content-previewed chooser, live store switching; `WORKER_RPC_VERSION` 5 |
| C1 **PR5 follow-ups** | 2 | ✅ done | **PR #239** (merged) — self-describing export name, `HOW-TO-MOVE` marker, one-click reconnect |
| C1 **PR2** same-browser migration | 1 | ✅ done | **PR #240** (merged) — OPFS→folder rescue prompt (migration = existing pick→writeNow) |
| C1 **PR6** mobile browse-only rebuild | 2 | ✅ done | **PR #241** (merged, `6cfb459`) — scroll shell, hamburger drawer, strip group chrome + redirect, Email/Call CTAs, reduced Settings, hero/has-email match-the-mock, baselines re-promoted. Full `just test` green |
| PR3d has-email localStorage guard | 2 | ✅ done | resolved by the **private-data enforcement** detour — **PR #244** (`d2706a9`): prefs are localStorage-only off-folder + off-folder durable writes refused at worker + page; `tests/e2e/test_private_data_enforcement.py`. See [`private_data_enforcement.md`](private_data_enforcement.md) |
| Desktop grayed-out + "Enable on Chrome desktop →" CTA | 2 | deferred | PR3 currently *hides* desktop entry points (functionally correct); the discoverable CTA is a refinement |
| Integration + re-baseline | 3 | ✅ done | folded into each PR; phone baselines promoted in #241 |
| C4 constraints upstream | 4 | pending | **the last EPIC tail** — maintainer-gated; sharpen with PR1–6 learnings (`plans/pna_toolkit_constraints_contribution.md`) |
| C5 exceptions upstream | 4 | ✅ done | PNT PR #8 (landed) |

### Sequencing correction discovered during PR1 (important)

The desktop e2e suite + the `worker_data` wipe fixture (`tests/e2e/conftest.py:188-212`) run in a **no-folder** context but *expect* `relationships.db` to work — which is exactly the state the gate turns into browse-only. So **the has-email "localStorage-only" fix, the surface-gating (PR3), and a new folder-attached test fixture cannot land green separately — they are one coordinated landing.** PR1 was therefore kept to pure inert plumbing. Next coordinated unit: introduce a `folder_attached` e2e fixture that flips `privateDataEnabled()` true (the desktop group suite depends on it, behavior unchanged once unlocked) **together with** PR3 surface-gating + the shared-mode localStorage-only guards.
