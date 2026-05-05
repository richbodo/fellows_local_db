# Local-First Worker Architecture

A formal plan to convert PR #99's worker fallback into the target architecture: a single dedicated worker that owns all OPFS access, with the main thread acting as an RPC client. The plan is sequenced for an environment where breaking changes are explicitly accepted (15 test users, no real `relationships.db` data, all happy to delete-and-redownload).

## Context

PR #99 (`fix(opfs): worker fallback for backup/restore + relationships ops`) shipped a dedicated `vendor/sqlite-worker.js` that can fully own OPFS-backed SQLite, but kept the main-thread path as the default and the worker as the fallback. Real-browser evidence (Safari, intermittent Firefox) shows the main-thread path is the brittle layer. Combined with the project's local-only / never-SaaS stance and `email_gate.md` invariant 10 (a stale session must not lock users out of cached data), the right move is to flip the default — the worker becomes the only OPFS owner, the main thread becomes a thin RPC client.

Background reading:
- The 8-point plan and its evaluation in conversation history (file-of-record: this plan).
- `docs/Architecture.md` § Design constraint, § Persistence and upgrades.
- `docs/email_gate.md` invariant 10.
- `docs/persistence_and_upgrades.md` § Storage layers.
- `docs/browser_support.md` § Required versions.

What this plan **does not** assume:
- Migration code for existing OPFS data. No real user data exists; test cohort is happy to clear and re-download.
- A legacy main-thread fallback. Remove it.
- A long parallel-architecture period. Single cutover for OPFS ownership.

What this plan **does** preserve, deliberately:
- The IndexedDB read fallback for invariant 10. Retiring it is its own phase (Phase 6) gated on real-browser evidence that the worker-owned cache holds. Bundling its removal with the OPFS cutover would delete the last independent read path at exactly the moment the new one is shaking out.

## Goals

Each goal is a runtime-falsifiable statement, not a vibe.

G1. **Single OPFS owner.** The dedicated worker is the only context that opens `FileSystemSyncAccessHandle`. The main thread holds zero OPFS handles.
G2. **Local-first returning boot.** On returning app-mode visits with local DBs present, the app renders directory + groups from local DBs before fetching directory data from the network. First-install boot — where there is no local cache — is the documented exception (see L4a).
G3. **Decoupled refresh.** A failed `fellows.db` refresh is a soft-warning state, never blocks `relationships.db` operations, and does not surface to the user as a fatal error.
G4. **Atomic, versioned bundle data.** `fellows.db` is re-imported only when the server-reported content identifier differs from the locally-recorded one. Every-boot re-import goes away.
G5. **RPC-version + schema-version handshake.** The main thread refuses mutating RPCs to a worker whose `WORKER_RPC_VERSION` or `RELATIONSHIPS_SCHEMA_VERSION` doesn't match its own. The build label is **not** part of this gate — see § Why build label is not the gate.
G6. **Persisted storage best-effort.** `navigator.storage.persist()` is attempted at least once per install, the call is recorded, and the resulting `persisted()` state is visible in diagnostics. A denied or unavailable result does not block boot. Lands in Phase 1, not at the end.
G7. **Test coverage of the architecture.** Worker-backed CRUD, stale-session boot, offline boot, version-mismatch transitions, worker-spawn-failure, and cold-start auth-gating are covered by automated e2e, not manual walk-throughs.

## Why build label is not the gate

Earlier drafts of this plan used the full build label (`<date>-<sha>`) as the mutating-RPC compatibility gate. That gate is too coarse: a CSS-only or copy-only deploy bumps the build label without touching the RPC contract or the schema, and would briefly lock writes on every such deploy until the user reloads. Equally, build-label drift between page and worker is already a *delivery* problem the service worker solves — `sw.js` bumps `CACHE_VERSION` per build and surfaces the existing "New version available — Reload" banner.

So we use two narrower primitives instead, both worker-internal constants:

- **`WORKER_RPC_VERSION`** — bumped only when the request/response shape of any RPC changes (parameters, return shape, error semantics). A pure code refactor that preserves the wire shape leaves it alone.
- **`RELATIONSHIPS_SCHEMA_VERSION`** — same value as `relationships.db`'s `PRAGMA user_version` (currently `1`). Bumped only on schema migrations.

The page reads both during the worker init handshake and refuses mutating RPCs (`createGroup`, `setSetting`, `importRelationshipsBytes`, …) on mismatch. Reads still work so the user can browse cached data while the SW's reload banner does its job.

## Non-goals — architectural

These are bright lines for the codebase, not just the plan. Add them to `Architecture.md`.

- **Service worker never owns a SQLite DB.** SW lifecycle (idle eviction, multi-instance, restart on push) is hostile to storage ownership. SW is app-shell + update detection only.
- **No parallel main-thread OPFS access.** After cutover, opening OPFS from anywhere other than the dedicated worker is a bug.
- **No server-side per-user state.** Production never gains `/api/groups`, `/api/settings`, server-side `relationships.db` storage, server-side backup, cross-device sync, or admin views. The dev-server routes for groups/settings become dead code once the worker is sole owner and are retired in Phase 1 (see § Open questions Q4).
- **No silent cross-device sync substrate.** Any future sync becomes an explicit, opt-in feature with its own design doc.
- **No multi-tab concurrent ownership.** OPFS sync access handles serialize per file; two tabs both opening `relationships.db` race on the SAH. Today's behavior — second tab fails to acquire — is preserved. A graceful "another instance is open" UI is out of scope for this plan; flag it as a follow-up.

## Non-goals — scope of this plan

Deliberately deferred:

- UI redesign of backup/restore (the underlying mechanism stays; the panel is fine).
- Encrypted backups.
- Auth flow changes.
- IndexedDB retirement — happens in Phase 6, not bundled with the cutover.
- Telemetry beyond the existing client-error sink.
- Multi-tab UX.

## Invariants this plan adds

Numbered to be peers of `email_gate.md`'s invariants. Each is runtime-checkable.

- **L1.** The dedicated worker is the only OPFS opener. Greppable: `navigator.storage.getDirectory` exists in `vendor/sqlite-worker.js` and nowhere else under `app/static/`.
- **L2.** All `relationships.db` operations are issued via worker RPC.
- **L3.** All `fellows.db` reads are issued via worker RPC.
- **L4.** On a returning app-mode boot (worker reports local `fellows.db` + `relationships.db` present), the page renders from local DBs before any request to `/api/fellows*` or `/fellows.db`. `/api/auth/status` is permitted in parallel — it is gate-decision input, not directory data. Cold-start boots are the documented exception, gated by L4a.
- **L4a.** The worker does not fetch protected bundle data (e.g., `/fellows.db`) until the page issues an explicit `ensureFellowsDb` RPC. The page sends that RPC only after the gate decision tree resolves to directory mode. A clean-profile, unauthenticated boot therefore makes zero `/fellows.db` requests.
- **L5.** A 4xx/5xx/network-error from `/fellows.db` or `/api/fellows*` does not block any `relationships.db` operation.
- **L6.** `navigator.storage.persist()` has been attempted on this origin at least once per install; `persisted()`'s resulting state is shown in diagnostics. A denied or unavailable result is non-fatal.
- **L7.** Mutating worker RPCs refuse to execute if the worker's `WORKER_RPC_VERSION` or `RELATIONSHIPS_SCHEMA_VERSION` differs from the page's expected values. Build label is **not** consulted (§ Why build label is not the gate).
- **L8.** `fellows.db` re-import is gated on a server-reported content identifier stored in worker-owned metadata (`fellows.db.meta.json` in OPFS root), independent of `relationships.db`. Restoring a `relationships.db` backup does not affect `fellows.db` freshness.

## Phasing

Phase 0 lands first. Phases 1–4 are sequential. Phase 5 is paired with each, not done at the end. Phase 6 is gated on Phases 1–4 having soaked in production.

### Phase 0 — Documentation preflight + COOP/COEP precheck

Goal: lock the architecture vocabulary before the refactor lands so reviewers have a stable target, and verify the worker context inherits the cross-origin-isolated environment SAH-pool needs.

Deliverables:
- **COOP/COEP spike (30 min).** `vendor/sqlite-worker.js` already exists (PR #99, ~575 LOC) and is the live worker. Do **not** overwrite it. Add a temporary `probeCoi` op to the existing worker that returns `{crossOriginIsolated, hasSAB: typeof SharedArrayBuffer !== 'undefined'}` and call it from a one-shot `?diag=coi` query handler in `app.js`. Verify both are `true` in dev (`app/server.py:end_headers` already sets COOP/COEP) and prod (Caddy reverse proxy). Revert the probe code before merging Phase 0 docs. If either flag is false, the entire plan stalls — fix the proxy/server first.
- `docs/Architecture.md`: new "Worker-owned OPFS" subsection under § Persistence; an explicit "Non-goals" section using the bullets above.
- `docs/persistence_and_upgrades.md`: rewrite the storage-layer table with "owner" column ("worker" / "main" / "service worker"); reframe the auto-backup section as a worker-internal mechanism (new trigger semantics — on every boot, debounced 1 h, 5-slot rotation; see Q-C resolution); **remove** the `last_seen_sha.txt` row (sentinel retired, derived from most recent `bak.<ISO>` filename); update the `relationships.db.bak.<ISO>` row to read "rotated to keep newest 5" and "Auto-created on every boot when the most recent backup is more than 1 hour old"; add `fellows.db.meta.json` to the storage-layer table.
- `docs/browser_support.md`: capability detection moves from main thread to worker — update the "How a user without OPFS reaches the panel" section.
- `CLAUDE.md` § Conventions: add "OPFS access only via the dedicated worker; main thread is an RPC client."
- **Doc-state stance.** Phase 0 docs describe the *target* architecture (worker-owned OPFS) and lead with a single-sentence banner: "This document describes the architecture as of Phase 1 — runtime catches up when the cutover ships." Removed when P1 lands. This avoids three rewrites of the same prose and gives reviewers a stable target.

Acceptance:
- COOP/COEP spike green in both dev and prod.
- A reviewer with no prior context can read `Architecture.md` and answer: which context owns OPFS? what is the SW for? what survives Clear App Cache vs Reset Everything?

Out of scope: docs for backup/restore UI changes (no UI changes in this plan).

### Phase 1 — Worker becomes sole DB owner

The breaking change. Inverts PR #99's default. This phase owns: cutover, auth-gated cold-start bootstrap, RPC + schema handshake, `persist()`, and retiring the now-dead dev-server routes.

Scope:
- `app/static/app.js`: delete the main-thread `sqlite3InitModule` + `installOpfsSAHPoolVfs` path. Delete `initOpfsDataProvider` and `createSqliteDataProvider` (the OPFS-direct branch). Delete `createHybridApiAndWorkerProvider` (the api+worker hybrid). Delete `maybeBackupRelationshipsDb` (~line 2938) and `snapshotRelationshipsDbToBackup` (~line 2989) — both call `poolUtil.exportFile` on the main thread; the worker already has equivalents at `vendor/sqlite-worker.js:213,245`. Delete `probeOpfsInWorker` (~line 3167) — replaced by the worker's `init` handshake. Delete the `last_seen_sha.txt` read/write sites (sentinel retired by Q-C resolution; one-time cleanup on first boot of new bundle removes the orphaned OPFS file). Keep only the worker-RPC client.
- **`dataProvider.kind` audit.** Today the Settings page (`app.js:6963`-ish) and diagnostics panel both check `dataProvider.kind === 'api+worker'` to decide whether to render local-data UI. After cutover the kind is `'worker'`; update every consumer. `grep -n 'dataProvider.kind' app/static/app.js` returns the full list — every match needs review.
- **Schema-version constant.** Introduce `RELATIONSHIPS_SCHEMA_VERSION` as a shared JS constant in both `app/static/app.js` and `vendor/sqlite-worker.js`. Today `PRAGMA user_version = 1` is hardcoded in three places (`app/relationships.py:40`, `app.js:597`, `sqlite-worker.js:108`); the JS constant lives next to `RELATIONSHIPS_SCHEMA_SQL` in the worker, the page imports the same value via `init` handshake.
- `app/static/vendor/sqlite-worker.js`: become the canonical implementation. Add handlers for any `relationships.db` op currently only on the main thread. Add `getList` / `getFull` / `getOne` / `search` / `getStats` over `fellows.db`. Carries `WORKER_RPC_VERSION` and `RELATIONSHIPS_SCHEMA_VERSION` as constants.
- **Diagnostics RPCs land in P1, not P4.** P4 reads OPFS file inventory and the worker's version constants; cheaper to expose them now than to bump the worker bundle later. Add `getOpfsInventory` (returns the OPFS root entry list) and `getVersions` (returns `{workerRpcVersion, schemaVersion, buildLabel}`). The existing `getTrace` op stays.
- **Worker init is network-free.** The `init` RPC does sqlite3 init + OPFS attach + reads `relationships.db` and (if present) `fellows.db` and `fellows.db.meta.json`. It does **not** fetch any HTTP resource. Init returns a handshake blob: `{workerRpcVersion, schemaVersion, buildLabel, opfsCapable, hasFellowsDb}`. This is the only RPC the worker self-initiates.
- **Auto-backup runs inside `init`** (per Q-C resolution). After `relationships.db` is open, the worker lists `relationships.db.bak.*` siblings; if the newest is missing or older than 1 hour, it snapshots `relationships.db` to `relationships.db.bak.<ISO>` and prunes to the newest **5**. Listed before any RPC is served so the snapshot reflects the user's last-saved state, not anything mutated this session. `last_seen_sha.txt` is removed if present (one-time cleanup) and never written again. Failure to snapshot is non-fatal — logged via the existing client-error sink, init proceeds.
- **`ensureFellowsDb` RPC (page-driven).** Separate RPC for "make sure fellows.db is present and reasonably fresh." The page calls this exactly once per session, only after the gate decision tree resolves to directory mode. Behavior:
  - If `hasFellowsDb` was false (cold start), the worker fetches `/fellows.db` (`fetch('/fellows.db', {credentials: 'include', cache: 'no-store'})`), validates with `PRAGMA quick_check`, imports via the staging slot, and writes the initial `fellows.db.meta.json`. The page renders a "Downloading directory…" skeleton during this.
  - If `hasFellowsDb` was true: in Phase 1 this is a **no-op** (no fetch, no re-import). G4 ("`fellows.db` re-imported only when content identifier differs") ships partially in P1 — one less round-trip per boot for returning visitors. Phase 3 adds the SHA-based refresh on top; until then, returning visitors get whatever bytes are already on disk and a fresh copy only when they Reset Everything.
  - On fetch failure during cold start, the worker surfaces a clear error to the page; the user gets a retry affordance. No main-thread fallback.
- **Worker spawn timing vs. email gate.** The worker is spawned eagerly (init only) in parallel with `/api/auth/status`, so OPFS handles and the sqlite3 runtime are warm by the time the page commits to a UI. The worker does **not** make a network request during this window — `ensureFellowsDb` is gated behind directory-mode confirmation. If the gate decision tree lands at the email gate or install landing, the worker is terminated without ever having reached the network. If it lands at the directory, the page issues `ensureFellowsDb` and the warm worker handles it immediately. This preserves the "URL-just-works" return path while keeping unauthenticated visitors invisible to protected endpoints.
- **RPC + schema handshake.** Page declares its expected `WORKER_RPC_VERSION` and `RELATIONSHIPS_SCHEMA_VERSION` as constants in `app.js`. On worker init, page compares against the worker's reported values. Mismatch → reads still work, mutating RPCs throw `VersionMismatchError`, the page surfaces a passive "Reload to finish update" badge but does **not** add a new banner (the SW's existing "New version available — Reload" is the canonical update affordance; we just defer to it).
- **`persist()` lands here.** After first successful boot, page calls `navigator.storage.persist()` once and caches the result. On Firefox the user sees a permission prompt — acceptable for an installed PWA. Diagnostics distinguishes `persisted: true`, `persisted: false (denied)`, `persisted: false (not asked)`. A denied or unavailable result is non-fatal — the boot proceeds normally.
- **Retire dev-only API routes — and migrate the e2e fixtures that depend on them.** `app/server.py`'s `/api/groups` and `/api/settings` handlers (POST/PATCH/DELETE/PUT and the matching GETs) are deleted. They become dead code with the worker as sole owner; keeping them creates a dev/prod asymmetry that drifts. The dev server still serves `/api/fellows*`, `/api/search`, `/api/stats`, static, images, and the auth/diagnostics stubs. **Test migration is part of P1**, not a follow-up: `tests/test_api.py` (delete the `groups`/`settings` test classes — `TestGroupsCRUD` lines 195–339, `TestSettingsAPI` lines 343–388, 18 tests total) and 7 e2e tests that use these routes as fixture setup (`test_copy_buttons.py`, `test_groups_compose.py`, `test_groups_index.py`, `test_groups_edit.py`, `test_groups_export.py`, `test_groups_detail.py`, `test_settings.py`) — rewrite their setup to drive the worker via `page.evaluate('window.__dataProvider.createGroup(...)')`. **Shim:** P1 exposes the worker-RPC client as `window.__dataProvider = dataProvider` immediately after worker init in `app/static/app.js`'s boot path. The IIFE is currently closed (no test-accessible globals); this one-line addition is what makes the helper drive the same code path the real app uses (catches integration bugs that a parallel test-only worker spawner wouldn't). Add a single helper in `tests/e2e/conftest.py` so the setup pattern doesn't sprawl across files.
- Build pipeline: `build/build_pwa.py` already substitutes `__FELLOWS_UI_DIAG__` / `__CACHE_VERSION__` in `app.js` and `sw.js` — extend the substitution list to include `vendor/sqlite-worker.js` so the worker carries the same build label for diagnostics. The dev server (`app/server.py`) must do the same.

Acceptance (run these as a manual checklist before merge):
- `grep navigator.storage.getDirectory app/static/app.js` returns no matches.
- `grep installOpfsSAHPoolVfs app/static/app.js` returns no matches.
- `grep -E '/api/(groups|settings)' app/server.py` returns no handler matches.
- Loading the app on Chrome / Edge / Safari 16.4+ / Firefox 111+ produces a working directory + groups CRUD with no console errors.
- **Clean profile bootstrap (authenticated path).** First-ever load on a profile with no OPFS state walks: gate → sign-in → directory render. The worker fetches `/fellows.db` only after the gate decision tree resolves to directory mode and the page issues `ensureFellowsDb`. No main-thread fallback in the network panel.
- **Cold-start gating (unauthenticated path).** A clean-profile boot that lands at the email gate makes zero `GET /fellows.db` requests — verified in DevTools Network. The worker is spawned (init phase only) and is then terminated when the gate UI commits.
- Inducing an RPC-version skew (manually edit the worker bundle to bump `WORKER_RPC_VERSION` while leaving `app.js`'s expected value alone) refuses mutating actions and surfaces the "Reload to finish update" badge; reads still work.
- A browser without SAH lands on `renderLocalDataUnavailablePanel` with the right copy. No silent degrade. **Coverage approach:** an automated e2e (`tests/e2e/test_unsupported_browser.py`, lands with P1) uses `page.add_init_script` to delete `FileSystemFileHandle.prototype.createSyncAccessHandle` before navigation — this exercises the panel-rendering branch in the real Chromium harness. The original plan called for a manual smoke on Safari < 16.4 here; that's been replaced because no naturally SAH-deficient device is on hand (the maintainer's older iPhone is on iOS 26.4.2). BrowserStack (or similar) is the deferred follow-up if/when a real-environment regression report comes in for the Samsung / Opera / weird-iOS-versions long tail.
- `navigator.storage.persist()` is attempted on first successful boot; the call is recorded; `persisted()`'s result is visible in diagnostics. A denied or unavailable result does not block the directory render.

Out of scope: changing the boot order (Phase 2). Changing the refresh policy (Phase 3).

### Phase 2 — Local-first boot, decoupled refresh

Restructure `boot()` so local DBs are primary; the network is a top-up. IndexedDB writes and reads stay untouched in this phase — the worker-owned `fellows.db` becomes primary, IDB drops to read-only fallback for invariant 10, retired in Phase 6.

Scope:
- `app/static/app.js`: new boot order. (a) Spawn worker (init only, per Phase 1's gate-aware timing). (b) In parallel, fire `/api/auth/status` for gate decision. (c) Worker reports `hasFellowsDb` + `relationships.db` ready. (d) If gate decision tree resolves to directory mode and `hasFellowsDb` is true, render directory + groups from local state immediately, then issue `ensureFellowsDb` for background refresh check. (e) If `hasFellowsDb` was false, render the "Downloading directory…" skeleton, issue `ensureFellowsDb`, and render once it returns.
- Decouple failure handling: the directory-refresh failure path renders a build-badge state (`server: offline · using cache`) and a soft toast, never blocks the page. Group-detail rendering when a member's `record_id` can't be resolved against the local `fellows.db` shows the `record_id` with a small "fellow data unavailable" hint instead of a hard error.
- Invariant 10 update: the canonical local cache is now the worker-owned `fellows.db`. The IndexedDB cache is still populated and still readable as a third-tier fallback (in case worker init itself fails on some browser we haven't seen yet). `email_gate.md` invariant 10 stays as written until Phase 6.

Acceptance:
- With Chrome DevTools "Offline" toggled on a returning visit with local DBs already populated, the app renders directory + groups from local state within 500 ms of navigation; build badge shows the offline marker. (We do not promise recovery from the SW being unregistered; that's a re-install scenario, not an offline-boot scenario.)
- Forcing `/api/fellows` to 401 on a returning visit: directory still renders (from worker-owned `fellows.db`), groups still mutate, the user sees a soft warning rather than a fatal panel.
- A first install on a clean profile still walks the install / first-fetch path correctly (Phase 1's cold-start contract holds).

Out of scope: versioned `fellows.db` (next phase); IDB retirement (Phase 6).

### Phase 3 — Versioned, atomic `fellows.db` updates

Stop re-importing `fellows.db` on every boot. Metadata is **worker-owned**, stored as a sibling OPFS file — explicitly not in `relationships.settings`, so a `relationships.db` restore can't desync `fellows.db` freshness.

Scope:
- **Server-side:** `build/build_pwa.py` computes a content SHA-256 of `deploy/dist/fellows.db` and writes it into `deploy/dist/build-meta.json` as a new field `fellows_db_sha`. Dev server (`app/server.py`) computes it on the fly. No HTTP-level ETag — the SHA in `build-meta.json` is the only freshness signal we need; ETag is parallel infrastructure that adds nothing.
- **Worker-side:** `fellows.db.meta.json` lives in OPFS root (alongside `relationships.db.bak.*` siblings, outside the SAH-pool dir). Shape: `{sha: "...", fetched_at: "ISO", last_failure_at: "ISO|null", last_failure_reason: "..."}`. Worker reads it during `init` and exposes the contents to the page. On `ensureFellowsDb`, worker compares `meta.sha` to `build-meta.json`'s `fellows_db_sha`. Equal → no-op. Different → fetch new bytes (`fetch('/fellows.db', {cache: 'no-store'})`), import to staging slot, validate, swap, then update `fellows.db.meta.json`.
- **SW interaction.** `sw.js` should not cache `/fellows.db`. The worker is now the cache for that file; double-caching megabytes in both SW and OPFS wastes quota and creates a third place a stale copy can hide. `/fellows.db` is **already absent from precache** (`APP_SHELL_ASSETS` in `sw.js:13` explicitly excludes it). What's missing is a **runtime-cache exclusion**: today the default `cacheFirstInto(request, APP_SHELL_CACHE)` branch in `sw.js`'s `fetch` handler (~line 114) will opportunistically cache `/fellows.db` if anything fetches it. P3 adds an explicit pass-through (`if (url.pathname === '/fellows.db') return;`) at the top of the `fetch` handler so the worker is the only cache layer. (The worker bundle and `sqlite3.{js,wasm}` are already correctly precached and version-busted via `CACHE_VERSION` — no change needed.)
- **Atomic import:** import to a staging slot (`fellows.db.staging`), `PRAGMA quick_check`, swap, then delete staging. If anything fails mid-flight, the previous DB is still the live one. `last_failure_at` / `last_failure_reason` get written to the meta file so diagnostics surfaces it.
- **Page-level UI:** silent refresh + small "Directory updated" toast (matches the "URL just works" / minimal-friction stance). Non-blocking.

Acceptance:
- Two consecutive returning boots with no server-side change make zero `GET /fellows.db` calls. Verify in DevTools Network.
- Bumping `fellows.db` on the server triggers exactly one re-import on the next boot; the page either reflects new data immediately or shows the "Directory updated" toast.
- Killing the network mid-import leaves the previous `fellows.db` intact; re-boot recovers cleanly. `fellows.db.meta.json` shows `last_failure_at` populated.
- Restoring an older `relationships.db` backup via Settings does not trigger a `fellows.db` re-fetch on next boot — proves the meta sibling correctly decouples the two files.

Out of scope: cross-version schema migration. The schema is single-version today; if it ever isn't, a separate plan covers it.

### Phase 4 — Diagnostics + UI vocabulary cleanup

After Phases 1–3, the app has only one user-facing mode: local. The server is contacted opportunistically for build-meta and SHA-keyed `fellows.db` refresh, never for primary reads. This phase brings the UI vocabulary in line with that, and surfaces the persistent server-contact signal (`fellows.db.meta.json`) in the two places it's actually useful: the developer's diagnostics panel, and the user's About-page update check.

The framing matters. To users, this is a desktop-app delivered by magic link — they install it, it runs, that's the model. Telling them "you're online" or "local-only mode" presumes a SaaS mental model the app was deliberately built to avoid. To developers, "is the server reachable right now?" is a less useful question than "when did the worker last successfully sync?" — the latter is persistent across sessions and is exactly what `fellows.db.meta.json` already records.

Scope:

- **Drop the main-UI connection banner.** `#connection-banner` ("You are online." / "You are offline. Showing cached data where available.") is leftover from the api+idb era. Post-cutover it tells the user something they don't need to know and contradicts the desktop-app mental model. Delete the element from `index.html`, the `updateConnectionBanner` function + `connectionBannerEl` reference in `app.js`, the `online`/`offline` window listeners, the per-route hide calls, and the `.connection-banner` CSS rule.

- **Surface "last server contact" on the About page.** That's the one place a user would ask the question — they're already there to check for updates. Add a passive line near the existing "Check for updates" control:
  - `Last update check: <ISO timestamp> — succeeded` when `fetched_at` is the most recent event.
  - `Last update attempt: <ISO timestamp> — failed: <reason>` when `last_failure_at` is more recent than `fetched_at`.
  - `No update checks recorded yet` when the meta is empty.
  - Source: `fellows.db.meta.json:fetched_at` / `last_failure_at` / `last_failure_reason`, read via a new worker RPC `getFellowsDbMeta` (thin wrapper over existing `readFellowsMeta()`).

- **Render `fellows.db.meta.json` contents in the Diagnostics panel.** Same `getFellowsDbMeta` RPC; show the full blob (sha, fetched_at, last_failure_at, last_failure_reason). Developer-grade detail belongs here, not on About.

- **Drop the build-badge "local-only mode" indicator from earlier drafts of this phase.** In a single-mode app there is no mode-change to indicate. The build badge keeps its build-label role; no new trigger is added. `setBuildBadgeOfflineOnly` is left untouched — it still fires harmlessly in the api+idb fallback path (browsers without OPFS) and is unrelated to the post-cutover happy path.

- **The rest of the Phase 4 panel content shipped in Phase 1** (worker version handshake, OPFS inventory, `persisted()` state). Verify they still render correctly post-Phase-3; no new code needed there.

Acceptance:

- Main-route DOM has no `connection-banner` element on any route. No `online`/`offline` window listeners remain.
- About page shows the last-update-check line, populated from the worker meta.
- Diagnostics panel shows the full `fellows.db.meta.json` contents — RPC-derived, no main-thread OPFS access.
- `tests/e2e/test_diagnostics_panel.py` (new) opens `?diag=1`, captures the panel text, and asserts each Phase 4 section renders. Same file asserts the connection banner is absent from the directory route.
- `docs/users_manual.md` reflects the About-page change (per CLAUDE.md: UI/UX changes ship with the doc update).

Out of scope: telemetry beyond the existing client-error sink. Renaming or restyling the build badge. A real-time "server reachable now?" indicator — the persistent meta is sufficient.

### Phase 5 — Test infrastructure (paired with each phase)

Don't save this for the end. Each phase ships with its own coverage.

Scope:
- `tests/e2e/` additions:
  - `test_worker_rpc.py` — every relationships op via RPC matches the legacy main-thread behavior. Lands with Phase 1.
  - `test_worker_cold_start.py` — covers both directions of L4a:
    - **Authenticated cold start.** Clean-OPFS profile + valid session → page issues `ensureFellowsDb` after directory-mode commit, worker fetches `/fellows.db`, imports, renders.
    - **Unauthenticated cold start.** Clean-OPFS profile + no session → page commits to gate UI, makes zero `/fellows.db` requests in the network log; worker is spawned (init only) then terminated.
    
    Lands with Phase 1.
  - `test_worker_spawn_failure.py` — fake `vendor/sqlite-worker.js` to 404 (or to a script that throws on init). Assert the unsupported-browser panel renders. Lands with Phase 1.
  - `test_version_handshake.py` — induce a `WORKER_RPC_VERSION` skew via `route.fulfill` rewriting the worker bundle; assert mutating actions are refused with `VersionMismatchError`, reads still work. Lands with Phase 1.
  - `test_persist_storage.py` — `persist()` was attempted on first boot (call recorded), diagnostics shows the persisted-state result, a denied/unavailable response does not break boot. Lands with Phase 1.
  - `test_local_first_boot.py` — directory + groups render with `/api/fellows*` mocked to 401 and `/fellows.db` mocked to 503 (returning visit, local DBs primed in fixture). Lands with Phase 2.
  - `test_versioned_fellows_db.py` — two boots with the same `fellows_db_sha` produce zero `/fellows.db` requests; one boot with a changed SHA produces exactly one; restoring an older `relationships.db` backup does not change the result. Lands with Phase 3.
- Pure-logic handler helpers (RPC payload validation, version comparison, SHA diff check, `fellows.db.meta.json` parsing) live in separately-testable modules with regular unit tests; the worker handler is a thin wrapper that calls the helper and posts the result. No Node `worker_threads` harness — see Q-A in the Resolved list.
- Chaos test (manual or scripted): kill the worker mid-RPC during a `setSetting` write; verify recovery on next page load with no OPFS corruption.

Fixture re-use guidance (so each agent doesn't reinvent the wheel): the deploy-server-mode harness lives in `tests/conftest.py:113` as the session-scoped `deploy_server` fixture (in-process `deploy/server.py` on port 8766 with a fake Postmark recorder, an in-memory allowlist, and direct `AuthState` access). It's already production-tested by `tests/e2e/test_install_landing.py`, `tests/e2e/test_magic_link_standalone_unlock.py`, and the `tests/test_deploy_*.py` unit tests. The cold-start auth tests should reuse it via `pytest` injection (`def test_x(self, deploy_server, …):`). Note: `tests/e2e/test_email_gate.py` does **not** use this fixture — it relies on `page.route` mocking against the dev server, which is a different pattern. `tests/e2e/conftest.py` is where the new "inject OPFS state via worker RPC" helper lands. The 7 fixture-migration rewrites (P1, see above) should produce that helper as a side-effect; P5 phases 2–3 then consume it.

Acceptance: each phase's PR is blocked on its corresponding e2e landing green.

### Phase 6 — Retire IndexedDB

Gated on Phases 1–4 having soaked in production for at least two weeks with no boot-path regressions reported (`just prod-errors` shows no worker-spawn or OPFS-init reports).

Scope:
- `app/static/app.js`: delete the IDB write path (the post-boot mirror of `/api/fellows?full=1` results into `fellows-local-db`). Delete the IDB read fallback in `getList()` / `getFull()`. The worker-owned `fellows.db` is now the only local read source.
- `email_gate.md` invariant 10: rewrite the fallback clause to reference the worker-owned `fellows.db` cache instead of the IndexedDB cache. The user-facing behavior is unchanged.
- `clearAllAppData()` / `clearEverything()`: keep the `indexedDB.deleteDatabase('fellows-local-db')` call. Users upgrading from older bundles still have an IDB to clean up; removing the cleanup would orphan that data on disk.
- `docs/persistence_and_upgrades.md`: drop the IndexedDB row from the storage-layer table.

Acceptance:
- `grep -i 'indexeddb\|fellows-local-db' app/static/app.js` returns only the cleanup calls in `clearAllAppData`/`clearEverything`, not any read or write of cached fellow rows.
- A returning user from a pre-Phase-6 bundle has their IDB cleaned up on first boot of the new bundle (cleanup path still runs).
- `email_gate.md` invariant 10 reads coherently with the new cache mechanism.

Out of scope: the post-Phase-6 cleanup of `clearAllAppData`'s IDB deletion call. That can stay forever — it's a few lines, and the cost of leaving it is zero.

## File-level scope sketch

Just enough to make the work concrete. Not a diff.

| File | Change |
|---|---|
| `app/static/app.js` | Delete main-thread OPFS path; replace direct `relDb` / `db` callsites with RPC; reorder `boot()` (Phase 2); add RPC + schema handshake; gate cold-start fetch behind directory-mode commit (Phase 1, L4a); gate refresh on SHA via worker (Phase 3). Phase 6: delete IDB read/write paths. |
| `app/static/vendor/sqlite-worker.js` | Canonical implementation. Adds: `init` (network-free; returns version handshake + OPFS readiness blob with `hasFellowsDb`; runs the per-boot debounced auto-backup), `ensureFellowsDb` (page-driven; cold-start fetch and/or SHA-based refresh), `getList`, `getFull`, `getOne`, `search`, `getStats`, `fellows.db.meta.json` reader/writer, atomic staging-slot import. Existing relationships ops become canonical. Carries `WORKER_RPC_VERSION` and `RELATIONSHIPS_SCHEMA_VERSION` as constants. New trigger: snapshot on init when newest `bak.<ISO>` is >1 h old; rotate to keep newest 5; cleanup any orphaned `last_seen_sha.txt`. |
| `app/static/sw.js` | Phase 3: drop `/fellows.db` from caching rules. No other behavioral change; verify it caches `vendor/sqlite-worker.js` and `vendor/sqlite3.{js,wasm}` and that they bust together on `CACHE_VERSION`. |
| `app/static/index.html` | Possibly preload the worker (`<link rel="preload" as="worker">`). |
| `build/build_pwa.py` | Stamp build label into `vendor/sqlite-worker.js`. Compute and emit `fellows_db_sha` in `build-meta.json`. |
| `app/server.py` | Phase 1: delete `/api/groups*` and `/api/settings*` handlers. Mirror the build-label substitution into `vendor/sqlite-worker.js`; emit `fellows_db_sha` (compute on the fly) in the synthesized `build-meta.json`. |
| `deploy/server.py` | Serve `build-meta.json` with `fellows_db_sha`. (No ETag work.) |
| `docs/Architecture.md` | Phase 0. |
| `docs/persistence_and_upgrades.md` | Phase 0 + Phase 3 update + Phase 6 update. |
| `docs/browser_support.md` | Phase 0. |
| `docs/email_gate.md` | Invariant 10 rewritten in Phase 6. |
| `CLAUDE.md` | Phase 0 — add convention. |
| `tests/e2e/*` | Phase 5 — per-phase tests. |

## Open questions

Most of the original open questions have been resolved into the plan above. What's left:

**Q-B. Worker bundle preload.** Whether to add `<link rel="preload" as="worker" href="/vendor/sqlite-worker.js">` in `index.html`. Default proposed: **yes**, after Phase 1's gate-aware spawn timing is in place. It shaves a roundtrip off the directory boot path and is a no-op for gate-only visitors (preload doesn't execute the worker).

Resolved (formerly Q1–Q8 + this round's clarifications):
- `fellows.db` moves into the worker (yes — L3, G1).
- IndexedDB retired in Phase 6, not the cutover envelope.
- `sqlite3.{js,wasm}` loaded only in the worker.
- Dev-server `/api/groups` and `/api/settings` retired in Phase 1.
- "Directory updated" UX is silent refresh + small toast.
- Auto-backup mechanism kept, simplified, moved fully worker-side.
- Phase 1 is a single PR; Phases 2–6 are separate PRs.
- COOP/COEP propagation verified in Phase 0 spike.
- Cold-start fetch is page-driven (`ensureFellowsDb`), gated behind directory-mode commit, never speculative.
- `persist()` is best-effort; denied/unavailable does not block boot.
- Worker-side unit harness: **no Node `worker_threads` harness.** Where fast handler-logic feedback matters, extract pure-logic helpers (RPC payload validation, version comparison, SHA diff check, `fellows.db.meta.json` parsing) from worker handlers into separately-testable modules; the worker handler becomes a thin wrapper that calls the helper and posts the result. Browser-coupled code stays in Playwright. Avoids a stub layer that could pass while real browsers fail, and avoids dual maintenance for overlapping coverage.
- Auto-backup trigger: changed from build-SHA-differs to **on every successful boot, debounced to skip if the most recent `relationships.db.bak.<ISO>` is less than 1 hour old**. Rotation increased from 3 to 5 (the files are tiny, ~tens of KB even for an active user). Rationale: a build-label trigger is keyed to deploy cadence, but the recovery use case ("undo something I just did") is keyed to user-edit cadence; a debounced per-boot trigger is more sensitive without thrashing the rotation during debug-session reloads. The `last_seen_sha.txt` sentinel is **retired** — debounce reads the most recent `bak.<ISO>` filename instead, eliminating one OPFS file. Build-SHA tracking is no longer needed for any other purpose post-cutover.

## Doc updates required

Tracking, so nothing rots:

- `docs/Architecture.md` — Phase 0 (vocabulary), then a small revision per phase to keep facts current.
- `docs/persistence_and_upgrades.md` — Phase 0 (owner column + `fellows.db.meta.json` row); Phase 3 update for SHA-keyed refresh; Phase 6 to drop the IndexedDB row.
- `docs/browser_support.md` — Phase 0 plus a Phase 1 update on where capability detection lives.
- `docs/email_gate.md` — invariant 10 rewritten in Phase 6 to reference the worker-owned cache.
- `docs/debugging.md` — add a "worker stuck on init" playbook after Phase 1.
- `CLAUDE.md` — Phase 0 convention addition.
- `README.md` — likely no change; Architecture.md carries the detail.

The user-manual is unaffected — this plan changes no user-visible behavior beyond "directory updates more efficiently" and "stale session is more graceful."

## What success looks like

After all phases land:

- A user with a healthy install — shell already cached and local DBs present — can disconnect their network and reload the page, and still see their groups and the cached directory within a second. (We do not promise recovery from the SW being unregistered; that's a re-install scenario, not an offline-boot scenario.)
- A user on a brand-new browser session reaches the directory in under 500 ms after the bundle is cached, with `fellows.db` re-fetched only if its content changed.
- A clean-profile, unauthenticated visitor reaches the email gate without ever issuing a request to a protected endpoint. The worker is spawned for warm-up but never dials out.
- A version-skewed boot (new `app.js`, stale worker from cache) does not produce a corrupt write — mutating RPCs are refused and the SW's existing reload affordance does its job. No new banner, no parallel update UI.
- A `relationships.db` restore does not affect `fellows.db` freshness, and vice versa.
- Adding a new feature backed by `relationships.db` is one thing: a new RPC handler in the worker plus its caller in the page. No "do I open OPFS here too?" decision.
- A reviewer reading `Architecture.md` and this plan can answer "where does state X live, and what owns it?" for every storage layer in the app, without grep.

## Execution

Operational guidance for the agent(s) that will land this. Sequencing, conflict avoidance, and what each phase's worktree must have on day one.

### Definition of ready, per phase

**Phase 0**
- Plan reviewed; resolved Q-A / Q-B / Q-C choices committed.
- Caddyfile + redeploy access available so the COOP/COEP spike can reach prod.
- Doc-state stance picked (this plan: target-state-with-banner — see Phase 0 deliverables).
- A reviewer slot booked — P0's whole acceptance is "a reviewer can read the docs cold."

**Phase 1**
- P0 merged.
- COOP/COEP spike returned `crossOriginIsolated=true, hasSAB=true` in **both** dev *and* prod.
- Decisions resolved (record in this plan before opening the worktree):
  - `ensureFellowsDb` semantics when `hasFellowsDb=true` (this plan: no-op).
  - Auto-backup move owner + new trigger (this plan: P1 deletes the main-thread copies and the `last_seen_sha.txt` sentinel; worker copies become the only path; trigger flips to "every boot, debounced 1 h, 5-slot rotation" per Q-C resolution).
  - Diagnostics RPCs (`getOpfsInventory`, `getVersions`) land in P1 (this plan: yes).
- Test-migration list locked: `tests/test_api.py` (groups+settings classes) plus the 7 e2e files.
- `tests/e2e/conftest.py` reviewed — confirmed where the new "inject OPFS state via worker RPC" helper goes.
- Deploy-server-mode harness verified working: `tests/conftest.py:113` `deploy_server` session fixture (already used by `tests/e2e/test_install_landing.py` + `tests/e2e/test_magic_link_standalone_unlock.py`). Cold-start auth tests reuse this. (Earlier drafts of this plan misattributed the harness to `tests/e2e/test_email_gate.py`; that file uses `page.route` mocking instead.)
- ~~A clean Safari 16.4+ device or VM available for the manual SAH-fail acceptance check.~~ Replaced by `tests/e2e/test_unsupported_browser.py` (Playwright init-script that strips `createSyncAccessHandle`). Real-device Safari < 16.4 smoke is deferred to a follow-up gated on a user report; the maintainer has Mac Studio (latest Safari) + Pixel (latest Chrome) + an iPhone on iOS 26.4.2 — all above the SAH floor. BrowserStack remains the option for the long tail if/when needed.

**Phase 2**
- P1 merged and prod-soaked at least one deploy cycle (`just prod-errors` shows no worker-spawn or OPFS-init regressions).
- IDB write-path fate decided: keep mirroring `getList` results (recommended) or freeze. Affects what tests assert.
- Build-badge offline-marker code path located (`setBuildBadgeOfflineOnly` already exists in `app.js`); new trigger condition (`worker OK + server fetch failed`) sketched.
- Group-detail "fellow data unavailable" hint UX agreed (one-line decision; lock it before review).

**Phase 3**
- P2 merged and prod-soaked one cycle.
- `fellows.db.meta.json` shape locked, including any P4 diagnostics fields.
- Dev-server SHA compute cost benchmarked (sha256 over a multi-MB DB on every `/build-meta.json` request — should be sub-100ms; verify).
- "Directory updated" toast surface located in `app.js`.

**Phase 4**
- P3 merged.
- `?diag=1` panel inventory taken; new rows merge cleanly.
- All diagnostics RPCs already exposed by worker (verified in P1's DoR).

**Phase 5 (per pairing)**
- DoR is the partner phase's DoR plus:
- Playwright OPFS-state injection helper landed (in P1's worktree as part of fixture migration).

**Phase 6**
- P1–P4 merged and prod-soaked **≥ 2 weeks**.
- `just prod-errors` over the soak window shows zero worker-spawn / OPFS-init regressions.
- journald shows no `event=client_error` reports pointing at IDB-fallback paths (proves users haven't been silently relying on the fallback).
- `email_gate.md` invariant 10 rewrite drafted and reviewed before code changes.
- Decision: keep IDB cleanup in `clearAllAppData`/`clearEverything` forever (this plan: yes).

### File-conflict surface

Files touched by more than one phase. Use this to decide which phases can run in parallel worktrees and which must wait for the prior PR to merge.

| File | P0 | P1 | P2 | P3 | P4 | P6 |
|---|---|---|---|---|---|---|
| `app/static/app.js` | | ✓ | ✓ | ✓ | ✓ | ✓ |
| `app/static/vendor/sqlite-worker.js` | (probe op, reverted) | ✓ canonical | | ✓ meta + SHA refresh | ✓ `getFellowsDbMeta` RPC | |
| `app/static/sw.js` | | | | ✓ runtime-cache exclusion | | |
| `app/static/index.html` | | ✓ (preload, Q-B) | | | ✓ delete `connection-banner` element | |
| `app/static/styles.css` | | | | | ✓ delete `.connection-banner` rule | |
| `build/build_pwa.py` | | ✓ worker label sub | | ✓ `fellows_db_sha` | | |
| `app/server.py` | | ✓ delete routes + worker label sub | | ✓ `fellows_db_sha` compute | | |
| `deploy/server.py` | | | | ✓ `build-meta.json` field | | |
| `docs/Architecture.md` | ✓ | ✓ small revision | ✓ small revision | ✓ small revision | | |
| `docs/persistence_and_upgrades.md` | ✓ | | | ✓ | | ✓ |
| `docs/browser_support.md` | ✓ | ✓ small revision | | | | |
| `docs/email_gate.md` | | | | | | ✓ invariant 10 |
| `docs/debugging.md` | | ✓ "worker stuck on init" playbook | | | | |
| `docs/users_manual.md` | | | | | ✓ About-page "Last update check" line | |
| `CLAUDE.md` | ✓ | | | | | |
| `tests/test_api.py` | | ✓ delete classes | | | | |
| `tests/e2e/conftest.py` | | ✓ OPFS-state helper | | | | |
| `tests/e2e/test_*.py` | | ✓ migrate 7 fixtures | ✓ new test file | ✓ new test file | ✓ new test file | |

The hottest seams are `app/static/app.js` (every phase except P0) and `vendor/sqlite-worker.js` (P1 + P3). **Worktree branches off P1 will conflict heavily with branches off P2/P3/P4 if P1 isn't merged first.** Do not parallelize P1 with anything downstream.

### Agent strategy, per phase

The plan's natural execution unit is one phase = one worktree branch off `main` = one agent invocation (with `isolation: "worktree"`). Branch naming: `feat/local-first-pN-<short-tag>`.

**Phase 0** — single agent.
- One worktree, doc-only changes plus the temporary COOP/COEP probe.
- Two PRs out of one worktree is fine: `chore(arch): doc preflight for local-first worker` (the doc work) and `diag(opfs): COOP/COEP probe in worker` (the probe, reverted in the same PR after green prod check).
- Deliverable: P0 PR merged + COOP/COEP confirmed green in prod.

**Phase 1** — single agent, one large PR. Do **not** split.
- Cutover semantics make it impossible to land in pieces without a half-state where some callsites use the worker and some still try main-thread OPFS.
- Estimated diff size: ~600–900 LOC net (mostly deletions in `app.js`, additions in worker + tests).
- Worktree pre-flight: confirm DoR items, then start. Agent prompt should explicitly say "this is the breaking change; expect to delete more than you add."
- Sub-agents inside this worktree (sequential, not parallel — they all touch overlapping files):
  1. Add worker-side `fellows.db` ops (`getList`/`getFull`/`getOne`/`search`/`getStats`) + diagnostics RPCs + version constants.
  2. Rewrite `pickDataProvider` to return only the worker-RPC client; delete the three other providers.
  3. Delete the main-thread auto-backup functions and `probeOpfsInWorker`.
  4. Delete `/api/groups*` and `/api/settings*` from `app/server.py`; extend build-label substitution to the worker bundle.
  5. Rewrite `tests/test_api.py` (delete classes) and migrate the 7 e2e fixtures using the new conftest helper.
  6. Wire `persist()` and the gate-aware spawn timing in `app.js`'s boot path.
- Acceptance gate is the manual checklist already in the plan, plus `just test` green.

**Phase 2** — single agent, off P1.
- Wait for P1 to merge before opening this worktree (every conflict in the table above hits P2).
- One PR. Boot-order rewrite is small but touches the central control flow in `app.js`.

**Phase 3** — single agent, off P2.
- Wait for P2 to merge.
- One PR. Bundles three loosely-related changes (server SHA emission, worker meta sibling, SW runtime-cache exclusion). They can't be split without an intermediate state where the SHA exists but the worker doesn't read it.

**Phase 4** — single agent, off P3, low-risk.
- Could in principle parallelize with P3 (different files mostly), but cheap to wait — agent picks up after P3 merges.
- One small PR.

**Phase 5** — not its own agent. Each phase's e2e tests land in that phase's PR. Pure-logic helper extraction (per Q-A resolution) lands inside the relevant phase's worktree alongside the handler implementation, with unit tests in the same PR.

**Phase 6** — single agent, run **after** the 2-week soak.
- Schedule a calendar reminder; do not start the worktree before the soak window closes and `just prod-errors` is clean.
- One PR.

### Hand-off artifacts between phases

Each phase's PR description must include the next phase's preconditions, so the next agent has a self-contained start.

| From → To | Hand-off |
|---|---|
| P0 → P1 | COOP/COEP screenshot from prod; confirmed CLAUDE.md convention text; explicit doc-state-banner reminder. |
| P1 → P2 | Names of new RPC ops with their request/response shapes; `dataProvider` shape after cutover (`kind` value, method list); name of the OPFS-state e2e helper. |
| P2 → P3 | Boot-order pseudocode (the `boot()` function as it stands post-P2); names of any new flags or state variables introduced. |
| P3 → P4 | `fellows.db.meta.json` shape (final); list of fields the diagnostics panel will read. |
| P1–P4 → P6 | The two-week prod-soak verification log (`just prod-errors` output snapshots); any known soft-warning paths that should *not* trip on a clean install. |

### Risks specific to this execution model

- **P1 PR review burden.** ~600–900 LOC is at the edge of what a single reviewer can hold in their head. Mitigate by aggressive use of the manual checklist in P1's Acceptance section; reviewers check items rather than re-read the diff.
- **e2e migration sprawl.** The 7 fixture rewrites in P1 are mechanical but tedious. If the conftest helper isn't right by file #2, all 7 inherit the bug. Land the helper standalone first (one commit), then the migrations (one commit per file).
- **Soak window vs. velocity.** P6 waits two weeks. If a regression is found in P1–P4 during soak, the clock resets. Be willing to ship a fix-forward to P1–P4 rather than rolling back; rollback re-introduces main-thread OPFS, which is exactly what cutover removed.
