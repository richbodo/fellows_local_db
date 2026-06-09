# Plan — Conformance report + gate (close the "cited-but-not-passing" seam)

**Status:** DONE (all three commits on #249). **Created:** 2026-06-04.

## The finding that motivates this

A `conformant` row in `docs/Architecture.md` (`CST-PWA-SANDBOX-SEALED`,
`CST-PWA-STORAGE-EVICTABLE`) cited
`tests/e2e/test_private_data_enforcement.py::test_off_folder_settings_are_empty`
as evidence — but that test is `@pytest.mark.xfail(strict=True)`. A
**known-false invariant was cited as proof of conformance**, and every gate we
run stayed green:

- `tests/test_attestation_has_evidence.py` only checks that the cited `::name`
  **resolves to a real `def`**. It never checks the test **passes** or that it
  isn't `xfail`/`skip`. Working as written.
- The PNT evaluate flow *does* specify "confirm the named test exists **and
  passes**" (`pna-build-eval-contrib/SKILL.md` line 46) — but that's a
  human/LLM audit nobody ran at merge time. PNT deliberately "does not ship a
  Python conformance test runner beyond trivial lints" (SKILL.md line 125).

So the "and passes" half lived only in a flow nobody invoked. The seam between
the **deterministic layer** (checks existence) and the **human/LLM layer**
(checks passing) was unowned.

Secondary finding: the xfail-needs-an-open-PR rule is unenforceable as prose.
`strict=True` is an **asymmetric tripwire** — it goes red the day someone
*fixes* the invariant and forgets to drop the marker (XPASS), but stays a
contented green xfail *forever* if the fix is abandoned. Our actual failure mode
(PRs closed, plan marked DONE, identity-gating fix dropped from scope) is
exactly the abandonment case strict-xfail is blind to. And the convention that
the xfail "names the PR that will satisfy it" is a prose reason string nothing
parses.

## Design principle

**Derive conformance status from the tests; don't assert it in prose.** The
*Realization* narrative in `Architecture.md` stays human-written. The *Status*
word must be a function of the cited tests' real state. A row may read
`conformant` only if every test it cites is green **and not xfail/skip**.

Keep one pane of glass. The validation surface for "is this release safe?" must
be **concentrated** — a single report, with the deferral count as a headline
number that is supposed to be zero. No standalone `DEFERRALS.md` ledger: a
ledger normalizes its own contents and invites minimum-effort box-ticking. A
counted, capped headline keeps creeping debt loud instead of archaeological.

## Boundary we must not blur

Two different "evaluate conformance" things:

- **Deterministic conformance checker** — existence + marker-state +
  structured-anchor + deferral-cap. Pure, offline, fast. *This* is pytest, runs
  in `just test`, gates `just ship`. Engine for the report.
- **LLM evaluate flow** — the architectural-judgment audit from the PNT skill
  ("does the realization actually satisfy the AC?"). Non-deterministic; cannot
  live in pytest. Stays a human/agent-initiated step + the upstream
  conversation. **Out of scope for this plan.**

The report is the *serialization of the deterministic checker*, not an LLM run.
That keeps the test suite hermetic.

## PR breakdown (this repo builds features in ~3 PRs)

### PR1 — Strengthen the checker + make current state honest (the load-bearing fix)

Pure pytest, offline. Closes the discovered hole and would have caught the
original bug. Self-contained and shippable alone.

1. **Marker-state check** in `tests/test_attestation_has_evidence.py`: for every
   `conformant` row, resolve each cited `::name` and fail the row if that
   function (or its enclosing class) is decorated `xfail` / `skip` / `skipif`.
   AST-based (stdlib `ast`), 3.8-safe (no `ast.unparse`): find the named
   `FunctionDef`/`AsyncFunctionDef`/`ClassDef` node, walk its `decorator_list`
   (+ enclosing class decorators for methods) for any `Name`/`Attribute` whose
   id/attr is in `{xfail, skip, skipif}`. File-only refs (no `::name`) can't be
   attributed and are skipped by this check (they still get the existing
   existence check).
2. **Structured-anchor lint** — new `tests/test_xfail_discipline.py`:
   - Every `@pytest.mark.xfail(strict=True)` reason must contain a machine
     anchor `tracking: #NNN` (issue, not PR — issues close when the *work* is
     done; PRs close when *something* merges).
   - **Deferral hard-cap: at most 3** strict-xfail tests in `tests/`. The 4th
     fails the build. (Three because this project builds most features in three
     PRs; a deferral load past one feature's worth is the smell.)
3. **Fix current state** (required for PR1 to be green once #1 lands):
   - Drop the `test_off_folder_settings_are_empty` citation from the two
     `conformant` CST rows in `docs/Architecture.md`. The other cited tests
     (`test_no_folder_resident_private_store_off_folder`,
     `test_prefs_stay_localstorage_only_off_folder`) already carry those claims;
     the xfail stays purely as the tripwire for the stronger invariant.
   - Add `tracking: #NNN` to the existing xfail's reason (file a GitHub issue
     for the deferred `_ensureWorkspaceIdentity` folder-gating work; the issue
     stays open until the test XPASSes).

Touching `Architecture.md` attestation rows + `tests/` together satisfies the
`conformance_guard.py` Stop hook.

### PR2 — Conformance report + log (the readout) — DONE

Shipped as `scripts/conformance_lib.py` (shared source of truth, imported by
both the gate and the report), `scripts/conformance_report.py` (generator +
abandoned-deferral `gh` probe), `tests/test_conformance_report.py`, and the
committed artifacts under `docs/conformance/` (report.json + report.md; log.jsonl
gitignored). The two PR1 test files were refactored to thin wrappers over the
shared lib so the gate and the report can never drift. Design as specified below.



Stdlib script (`scripts/conformance_report.py` or `build/`): emit an AC/CST-keyed
report — the serialization of PR1's checker — shaped after PNT's
`tools/evaluate-report.schema.json` so it's diffable and feeds upstream later.

- Per-row: cited tests + resolved status (green / xfail / skip / dangling).
- **Headline deferral count** at the top (the folded-in visibility from idea 4).
- Timestamp + git SHA.
- Best-effort `gh`-lifecycle check (fail-open if `gh` absent/offline): flag any
  `tracking: #NNN` whose issue is **closed while the test still xfails** — the
  abandoned-deferral detector that strict-xfail can't be.
- **Conformance log**: append-only record (timestamp, SHA, deferral count,
  pass/fail) at a fixed path.

### PR3 — Wire into `just` (the event-driven triggers; no cron, no clock) — DONE

Shipped: `just conformance` (gate, hard-fails on findings) + `just
conformance-refresh` (stale-only, offline, non-fatal); `just test` depends on
`conformance-refresh`; the hard gate (`--no-write`) runs in `deploy-preflight`
so every deploy route is covered. `--if-stale` (threshold `STALE_COMMITS = 10`,
distinct from the deferral cap) added to the report script. Design below.



- Deterministic checker already runs in `just test` (full `tests/`).
- Add the report+gate to **`deploy-preflight`** — the single chokepoint every
  deploy route (`ship`, `ship-fast`, `deploy`) passes through. Note: today
  `just ship` runs `test-fast`, which *omits* the attestation checker entirely,
  so conformance is currently outside the ship path. Preflight is the fix.
- **Staleness auto-regen**: any `just test*` recipe checks the log; if HEAD is
  ≥3 commits past the last logged SHA (`git rev-list --count <logged>..HEAD`),
  regenerate the report. Commit-distance is the proxy for "N PRs out of date".

## Upstream (PNT) — deferred, discussed after this works here

Two contributions, once the fellows side is proven:

1. **Strengthen the portable checker template**
   (`reference_designs/templates/.../test_attestation_has_evidence.py`) with the
   marker-state check — still a "trivial lint", still portable, every reference
   design inherits it.
2. **Close the documented-but-unenforced seam in the skill**: SKILL.md line 46
   says "exists and passes" but the shipped checker only does "exists", and
   nothing flags that the lint *cannot* do the "passes" half. Either make the
   template enforce marker-state, or make the skill explicit that "passes" is
   irreducibly a human/LLM/CI step the lint will never cover. The xfail-anchor +
   abandoned-deferral convention belongs in PNT's discipline doc too.

Different reference designs will wire the *running* differently per their build
(this repo: `just` + pytest). Keep the upstream contribution to the *form*
(checker template + skill + discipline doc), not the wiring.

## Follow-up — self-stable report commit (PR #267 hardening, 2026-06-09)

The deterministic evaluate-report emitter (#267) initially set
`candidate.commit` (and report.json's `meta.git_sha`) from raw `git rev-parse
HEAD`. That made both reports record the *parent* of the commit that generated
them (HEAD at generation time), so the archived keystone artifact
self-referenced a stale commit — and any fresh checkout or ≥10-commit staleness
refresh regenerated a *different* file (the commit bumped to the new HEAD),
dirtying the tree. Not a loop today (staleness is 10-commit-gated, the log is
gitignored, the refresh is non-fatal, no clean-tree CI), but a landmine for any
future clean-tree gate and a keystone artifact that mis-reports the evaluated
commit.

Fix: a shared `scripts/conformance_lib.input_commit()` derives the commit that
last touched the report's **inputs** — `git rev-list -1 HEAD -- docs/Architecture.md`,
the attestation source both reports derive from — falling back to `rev-parse
HEAD` when git can't resolve it. Inputs are Architecture.md **only**, *not* the
emitter scripts: a commit that edits the emitter (this one included) must not
move the recorded commit of the candidate it evaluates, or the fix would
reintroduce its own self-reference. Both `evaluate_report.py` (`candidate.commit`)
and `conformance_report.py` (report.json `meta.git_sha`) use the one helper, so
they name the same evaluated commit and the committed reports stay byte-identical
on regen. The staleness *log* keeps recording HEAD (the run point) — distinct
from the report's displayed commit — so `_commits_since` still measures distance
from the last run, not from the last attestation change. Regression coverage:
`tests/test_evaluate_report.py::test_candidate_commit_is_the_input_commit`,
`::test_build_is_invariant_to_committed_report_changing`,
`::test_report_files_are_not_their_own_input`. (report.json still carries a
wall-clock `generated_at`, so it churns on regen regardless — only the
no-timestamp keystone evaluate-report.json is truly byte-identical.)
