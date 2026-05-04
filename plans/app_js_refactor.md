# `app/static/app.js` Refactor Plan

A staged, behavior-neutral refactor to reduce the cognitive load of `app/static/app.js` (currently 7,527 lines) without breaking the project's hard "single IIFE, no build tools, no modules, no classes" constraint. The plan is sequenced so every phase ships independently and can be reverted in isolation.

## Context

`app/static/app.js` has accumulated five overlapping responsibilities — boot/auth, diagnostics, mobile-shell chrome, two parallel data providers, the groups feature, exports, and settings — in one IIFE. By LOC it is more than 2× the next-largest hand-written file (`styles.css`, 3,611). By function count it is ~386 functions, twelve of which are over 100 LOC.

Recent context that motivates this now:

- **The Phase-1 worker cutover landed in PR #102** (see `plans/local_first_worker_architecture.md`). The worker is now sole owner of OPFS, and the dev server retired `/api/groups` and `/api/settings`. Several methods on `createApiDataProvider` (`exportRelationshipsBytes`, `inspectRelationshipsBytes`, `listRelationshipsBackups`, …) are now stubs that always reject. Other methods (`createGroup`, `updateGroup`, `setSetting`, …) still issue HTTP calls against routes that exist on neither dev nor prod. This is a real correctness smell, not just clutter — see Phase 1 below.
- **The render/wire split pattern already exists** for `renderGroupDetailPage` ↔ `wireGroupDetailPage` (lines 5055 and 6267). It just hasn't been applied consistently. Five other render functions (the largest in the file) still build HTML and attach handlers in the same body.
- **HTML is built by string concatenation throughout** — 277 inline tag literals across 184 `innerHTML` assignments, with the recurring `'<…>' + escapeHtml(x) + '</…>'` shape repeated several hundred times. The escaping invariant from `CLAUDE.md` is honored, but proving that to a reviewer requires reading every concat.

The constraint side is firm: `CLAUDE.md` mandates "Frontend is a single IIFE in `app/static/app.js`. No modules, no classes." This plan respects that. The refactor target is *intra-IIFE* simplification, not file splitting and not tooling.

## Goals

Each goal is falsifiable, not aspirational.

- **R1.** Total LOC of `app/static/app.js` reduced from 7,527 to under 6,300 — a ≥1,200-line drop, primarily from dead-code removal (Phase 1) and helper consolidation (Phase 2).
- **R2.** No top-level function exceeds 200 LOC. Currently five do (`renderSettingsPage` 427, `bootDirectoryAsApp` 294, `collectDiagnosticsText` 240, `renderGroupDetailPage` 217, `createApiDataProvider` 214).
- **R3.** Every `renderXxxPage` function follows the established `buildXxxHtml(data)` (pure) + `wireXxxPage(rootEl, data)` (event wiring) split. The existing `wireGroupDetailPage` is the model.
- **R4.** All HTML construction routes through a single tagged-template helper (`h\`...\``) that auto-escapes interpolations, with no `'<x>' + escapeHtml(...) + '</x>'` patterns surviving in renderers — i.e., the escaping invariant becomes lexically obvious.
- **R5.** `createApiDataProvider` exposes only the read methods that prod's `deploy/server.py` actually serves (`getList`, `getFull`, `getOne`, `search`, `getStats`). Every relationships/settings method is removed; consumers branch on `typeof dataProvider.<method> === 'function'`, which they already do in many places.
- **R6.** Each phase is shippable on its own — Playwright e2e green at every commit on the refactor branch — and reversible without touching subsequent phases.

## Non-goals

Explicit bright lines so this plan stays small enough to actually finish.

- **Not splitting into ES modules or multiple files.** The single-IIFE constraint is load-bearing for the no-build distribution model. If the maintainer wants to revisit it, that's a separate plan.
- **Not introducing classes, arrow functions for ES5 reasons, or any new dependency.** The file uses `var` and `function ()` consistently; the refactor matches that style. Template literals are already used (22 occurrences) and are kept.
- **Not changing the data-provider contract surface visible to callers.** Methods that go away on the API provider go away because callers already feature-detect them; no new caller logic.
- **Not touching CSS or HTML.** Pure JS internal restructure.
- **Not changing test files except where a Playwright selector needs adjustment** (none expected — selectors are by ID, not by structure).
- **Not adding a build step** (Python concatenation, source maps, sourceMappingURL stamps, etc.). The dev server stamps the build label; that's the only "build step" the file needs.
- **Not touching the worker** (`app/static/vendor/sqlite-worker.js`). This plan is page-only.

## Why now, why not later

- **Phase 1 is correctness work**, not aesthetics. `createApiDataProvider.createGroup` issues a POST to `/api/groups` that 404s on every server it can ever reach today. Whether that POST also leaks any state (it doesn't, but a future contributor wouldn't know) is a question that disappears with the dead code.
- **The render/wire split is cheap right now** because no PRs in flight touch the affected renderers. A week from now it isn't.
- **Helper introduction (Phase 2) is the long pole.** Doing it before Phase 3 means the new renderers in Phase 3 are written in the new style.

## Phases

Each phase = one PR. Independent. Each lists scope, expected LOC delta, success criteria, and risk.

### Phase 1 — API provider deadcode removal

**Scope.** In `createApiDataProvider` (lines 753–966):

- Remove `listGroups`, `getGroup`, `createGroup`, `updateGroup`, `deleteGroup`, `getSetting`, `getSettings`, `setSetting`. None of these correspond to a route any server in this repo currently serves; the code path is unreachable in dev (per `app/server.py:7–11` comment) and was never reachable in prod.
- Remove `exportRelationshipsBytes`, `inspectRelationshipsBytes`, `countRelationships`, `importRelationshipsBytes`, `listRelationshipsBackups`, `restoreRelationshipsBackup`. All six already return rejected promises or `null`/`[]` stubs; no caller benefits from their presence over `typeof dataProvider.xxx === 'function'`.
- Remove `probeGroupsRoute` (line 778) and the `groupsRouteSupported` cache flag — no remaining caller needs the probe.
- Keep `getList`, `getFull`, `getOne`, `search`, `getStats`. These are the live read methods that hit `/api/fellows*` (still served by both dev and prod).
- Update the JSDoc/comment block to reflect the new shape: "API+IDB provider exists only as a read-only directory fallback for OPFS-incapable browsers; relationships and settings unconditionally surface the unsupported-browser panel via `renderLocalDataUnavailablePanel`."

**Audit step (must run before merging).** Grep every removed method name across `app/static/app.js` and tests. For each callsite that does *not* feature-detect (`if (dataProvider.xxx)` or `typeof dataProvider.xxx === 'function'`), either add a feature-detect branch or document why the call is only reachable on the worker provider. Worker-data e2e helper (`tests/e2e/conftest.py:worker_data`) drives the worker provider directly and is unaffected; API+IDB callsites typically already branch.

**Expected LOC delta.** −115 to −135.

**Success criteria.**
- `just test-fast` green.
- `just test-e2e` green, including the OPFS-unsupported flows in `tests/e2e/test_unsupported_browser.py` (the API+IDB provider's user-visible behavior must be unchanged: directory works, groups+settings show the unsupported panel).
- No grep hit for the removed method names from `app/static/app.js` (other than their definitions in the worker provider).

**Risk.** Low. This is removing code that already self-rejects. The only risk is a callsite that doesn't feature-detect and instead awaits the rejection. The audit step catches those.

**Rollback.** Single revert. Phases 2+ don't depend on this.

### Phase 2 — `h` tagged-template helper

**Scope.** Add one helper near the top of the IIFE, immediately after the `escapeHtml` definition:

```js
// Auto-escaping HTML tagged-template. Replaces the
// '<x>' + escapeHtml(value) + '</x>' pattern with h`<x>${value}</x>`.
// Interpolations are escapeHtml'd unless wrapped in safe() (for
// pre-built HTML fragments) or are arrays (joined and recursed).
function h(strings) {
  var values = Array.prototype.slice.call(arguments, 1);
  var out = strings[0];
  for (var i = 0; i < values.length; i++) {
    var v = values[i];
    if (v && typeof v === 'object' && v.__h_safe === true) out += v.value;
    else if (Array.isArray(v)) out += v.join('');
    else out += escapeHtml(v == null ? '' : String(v));
    out += strings[i + 1];
  }
  return out;
}
function safe(s) { return { __h_safe: true, value: String(s) }; }
```

Apply it to four self-contained builder functions first, where the impact is largest and the risk is lowest:

1. `buildExportIndexGrid` (line 5603)
2. `buildExportFellowSection` (line 5617)
3. `renderRailHeader` / `renderRailMembers` / `renderRail` (lines 3977, 4020, 4043)
4. `renderAuthDebugPrivate` (line 2902)

These are pure-string-builder functions — no DOM mutation, no async, no event wiring. They make a clean test bed for the helper without touching the bigger renderers in Phase 3.

**Expected LOC delta.** −180 to −240 across the four targets, plus +25 for the helper itself.

**Success criteria.**
- `just test-fast` and `just test-e2e` green.
- Manual visual check: export-as-HTML, export-as-PDF, groups composer rail, auth-debug panel all render byte-identical HTML modulo whitespace. (The helper preserves whitespace exactly as the template literal specifies, so byte-identity is realistic.)
- A small unit test in `tests/test_app_js_h_helper.py` is **not** added — keeping with the project's no-Node-test convention. Verification is via Playwright snapshot tests for the affected screens (already exist for export and rail).

**Risk.** Medium. Two failure modes: (a) double-escaping (passing an already-escaped string into `h` without `safe()`) — caught by visual diff; (b) accidentally putting interpolation inside an event handler attribute (e.g., `onclick="${expr}"`) where the auto-escape produces a syntactically broken attribute. The mitigation is a pre-merge grep for `on[a-z]+="\${` and the project's existing convention of attaching handlers in the wire functions, not inline.

**Rollback.** Revert touches the helper definition + four builders. Phase 3 is gated on this — see ordering note.

### Phase 3 — Render/wire split for the big functions

**Scope.** Apply the existing `renderGroupDetailPage` ↔ `wireGroupDetailPage` pattern to the remaining large render functions. For each:

- `buildXxxHtml(data)` returns a string. Pure. No DOM access.
- `wireXxxPage(data)` does `document.getElementById` lookups inside the freshly-rendered subtree and attaches listeners. No HTML construction.
- `renderXxxPage()` becomes a small orchestrator: fetch data, set loading placeholder, call `buildXxxHtml`, assign to `innerHTML`, call `wireXxxPage`.

Targets, in order of expected payoff:

1. **`renderSettingsPage`** (427 LOC, line 5827). Biggest function in the file. Mixes file-picker setup, restore-from-file confirm dialog, restore-from-backup picker, self-email reconcile, and "Clear App Cache" wiring. Split into `buildSettingsPageHtml`, `wireSettingsPage`, plus extract the confirm-dialog builder (`buildRestoreConfirmHtml`) which is reused between the two restore paths.
2. **`renderDetail`** (203 LOC, line 3691). The fellow-detail page. Already has clean structure (sections + work subheaders) but builds the whole DOM as one HTML string and then attaches the next/prev nav handlers and copy buttons inline.
3. **`renderSettingsPage`'s 427 lines hide a fourth target inside it: `renderRestoreBackupList`** — a sub-renderer that re-runs after every successful restore. Promote it to top-level alongside the other render functions.
4. **`renderAboutPage`** (112 LOC, line 4445). Smaller but easy.
5. **`renderGroupsList`** (90 LOC, line 4686). The handler-attaching loop is the bulk; extracting `wireGroupsList` is mechanical.

**`renderGroupDetailPage` (217 LOC) is already half-done** — `wireGroupDetailPage` exists; finish the job by extracting `buildGroupDetailHtml`.

**Expected LOC delta.** Net 0 to −150. The pure-string functions are slightly smaller than the equivalent inline builds (no `var html = ''; html += ...` plumbing); the wire functions stay the same size. The win is comprehension, not LOC.

**Success criteria.**
- R2 met: no function over 200 LOC.
- `just test-fast` and `just test-e2e` green.
- Mobile snapshot suite green (`tests/e2e/mobile/test_routes.py` — eight per-route × three viewport snapshots).

**Risk.** Medium. The big risk is dropping an event handler during the move. The mitigation is doing one renderer per commit (not one PR — one *commit* within the PR), running `just test-e2e` between each, and grepping the diff for `addEventListener` to confirm count parity.

**Rollback.** Per-renderer revert. Each commit stands alone.

**Ordering note.** Phase 3 builds *on top of* Phase 2 — the new build functions are written using `h\`\`` from the start. If Phase 2 doesn't ship, Phase 3 still works; it just produces less LOC reduction.

### Phase 4 — Routing and section index

**Scope.** Two small structural moves:

1. Move `route()` (line 4558) to immediately after the data-provider section, so the file's "spine" — providers, then routing, then renderers — is contiguous and readable in one scroll.
2. Add a top-of-file table-of-contents comment listing the section banners and their start lines, kept in sync by hand. Existing banners stay where they are.

**Expected LOC delta.** +20 (the index comment).

**Success criteria.** Smoke test: `just serve` + manual browse of every route. No tests should be affected — `route()` has no caller dependencies on its position in the file.

**Risk.** Trivial. Code movement only.

### Phase 5 — Unify `clearAllAppData` and `clearEverything`

**Scope.** Today, `clearAllAppData` (111 LOC, line 1156) and `clearEverything` (123 LOC, line 1268) duplicate teardown logic with two key differences: `clearEverything` also deletes OPFS contents and clears `fellows_authenticated_once`. Per `docs/persistence_and_upgrades.md`, this asymmetry is intentional and user-facing.

Consolidate into a single internal function with a shape like:

```js
function clearStorage(opts) {
  // opts: { wipeOpfs: boolean, wipeAuthOnceMarker: boolean }
  // Returns a Promise that resolves when teardown completes.
  // Does NOT reload — caller decides redirect target.
}
```

Then:

- `clearAllAppData()` becomes `clearStorage({wipeOpfs: false, wipeAuthOnceMarker: false}).then(() => location.replace('?cache_reset=' + ...))`
- `clearEverything()` becomes `clearStorage({wipeOpfs: true, wipeAuthOnceMarker: true}).then(...)`

The shared work — `clearCookiesBestEffort`, allowlisted localStorage clear, IDB delete, Cache API delete, SW unregister — lives in `clearStorage` exactly once. The asymmetry is two boolean branches, lexically visible.

**Expected LOC delta.** −80 to −100.

**Success criteria.**
- `tests/e2e/test_clear_app_cache.py` green.
- `tests/e2e/test_reset_everything.py` green.
- Manual end-to-end on a real Chrome: Clear App Cache preserves OPFS (verify via `?diag=1`); Reset Everything wipes OPFS root.

**Risk.** High *for this phase only*. These are user-data-destruction flows. The wrong branch on the wrong call deletes someone's groups. Mitigations:

- Land Phase 5 last, after every other phase has stabilized.
- Land it as a one-shot PR with no other changes. Reviewer can read the diff in one sitting.
- The diff should be expressed as a *refactor* commit (extracts `clearStorage` while preserving both call shapes literally) followed by a *consolidation* commit (replaces both function bodies with the new call). Each commit reviewable independently.
- E2E tests for both paths must be present and green before the PR opens — not deferred.

**Rollback.** Single revert. The refactor is internal; no callers change.

## Phase ordering and dependencies

```
Phase 1 (deadcode) ───┐
                      ├─→ ship anytime, independently
Phase 2 (h helper) ───┤
                      ├─→ Phase 3 (render/wire) builds on Phase 2's helper
Phase 4 (routing)  ───┤
                      └─→ Phase 5 (clearStorage) lands last, after stabilization
```

Phases 1, 2, and 4 are mutually independent and can ship in any order. Phase 3 wants Phase 2 in place first (else the new build functions ship in old style and need a follow-up rewrite). Phase 5 is gated on the rest stabilizing for at least one normal deploy cycle.

## Test strategy

The plan piggybacks on the existing test suite — no new test infrastructure.

- **`just test-fast`** runs after every commit. Catches DB + API regressions; fastest signal (~10× faster than e2e).
- **`just test-e2e`** runs at PR-open time and before merge. Catches DOM/handler regressions in the affected screens.
- **Mobile snapshot suite** (`tests/e2e/mobile/test_routes.py`) catches per-viewport visual regressions. Snapshots are byte-comparison; any unintended HTML/whitespace change fails immediately.
- **Manual smoke per phase** is documented in each phase's success criteria. The maintainer runs it once per PR; not automated.

No phase introduces a *new* assertion that wasn't already true. The refactor is behavior-preserving; tests prove the preservation.

## Risk register

| Risk | Phase | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Removed API method has a non-feature-detected caller | 1 | Low | Medium | Pre-merge grep audit |
| `h` helper double-escapes a pre-built fragment | 2 | Medium | Low | Visual diff via mobile snapshot suite |
| Lost event handler during render/wire split | 3 | Medium | Medium | One-renderer-per-commit + addEventListener count parity |
| Phase 5 wrong-branch destroys real user data | 5 | Low | **High** | Land last, two-commit decomposition, e2e green for both paths |
| `route()` move breaks something with closure capture | 4 | Very low | Low | Smoke test |

## Out of scope (might come up; not doing here)

- **Dropping `var` for `let`/`const`.** The file is internally consistent; mass conversion is a different style PR with its own review surface.
- **Replacing `XMLHttpRequest`-era idioms** (`addEventListener('click', function (ev) {...})`) with shorter patterns. Same reason.
- **Splitting into source files concatenated by `build_pwa.py`.** Real value, real cost; needs its own design discussion. Honors the no-bundler letter but bends the spirit. Defer.
- **A formal `dataProvider` interface contract** (e.g., a `// type DataProvider = { ... }` JSDoc block). Would be useful, but the current convention of feature-detecting in callers is itself a documented contract. If we drop more methods later, revisit.

## Headline

Today: 7,527 LOC, top function 427 LOC, twelve functions over 100 LOC, the largest hand-written file in the repo by 2×.

After all five phases: ~6,200 LOC, no function over 200 LOC, the `h` helper makes the escaping invariant lexically obvious, the API provider's surface matches what prod actually serves, the clear-vs-reset asymmetry is one branch instead of two functions.

The deeper win is that a future contributor — including Future Claude — can locate any feature in the file without having to hold the whole IIFE in working memory.
