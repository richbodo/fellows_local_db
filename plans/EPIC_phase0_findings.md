# Phase 0 results — frozen interfaces (the contract the lanes build against)

Produced by the Phase-0 analysis fan-out (2026-06-02). This is the **frozen interface** Lane CORE / WORKER / STYLE / DOCS / TESTS build against in parallel. Anchors verified against the working tree at that date. Companion to [`EPIC_private_data_and_mobile.md`](EPIC_private_data_and_mobile.md).

## A. Worker↔page RPC contract (bump `WORKER_RPC_VERSION` 3 → 4)

`WORKER_RPC_VERSION = 3` (`sqlite-worker.js:53`), `EXPECTED_WORKER_RPC_VERSION = 3` (`app.js:40`). Bump **both to 4** in lockstep. `RELATIONSHIPS_SCHEMA_VERSION` stays **1** — the identity stamp is rows in the existing `settings` table, not a schema change. Transport: `{id,op,args}` → `{id,ok,result|error,errorCode?}`; dispatch map `sqlite-worker.js:2640-2667`; page wrapper `createSqliteWorkerRpc` `app.js:3852-3900`; provider façade `createWorkerDataProvider` `app.js:3907-4080`; mutation skew gate `refuseIfVersionSkew` `app.js:3913`.

New ops:

| Op | Params | Returns | Mutates | Gating | Reuse |
|---|---|---|---|---|---|
| `probeFolderWritable` | `{handle, mode?='auto'}` | `{ok,parentName,subfolderName,sentinelVerified,permissionPersisted}` OR collision `{requiresChoice,existing{counts,size,lastModified},suggestion}` | yes (transient sentinel + persists handle on full pass) | version-**tolerant** (note the write exception in the `:46-52` contract comment) | `_findOrCreateSubfolder` :1914, `_folderQueryPermission` :2029, `_folderRecordPersist` :1871; **new** `_probeWritableSentinel(subHandle)` returning staged reason |
| `scanFellowsCandidates` | `{handle}` (parent) | `{candidates:[{subfolderName,groups,members,notes,lastModified,deviceLabel,writeGeneration,invalid,invalidReason}],recommended}` | no | tolerant | enumerate `Fellows*` via `parentHandle.values()` (today's `auto` only previews default — the §7.1 bug); per-candidate `_probeSubfolder` :1993 + identity read; **sequential** (shared `RESTORE_STAGING_SLOT` :166) |
| `getWorkspaceIdentity` | `{}` | `{workspace_uuid,device_label,created_at,last_written_at,write_generation}` (nulls if unset) | no | tolerant | `getSettings` :947 |
| `ensureWorkspaceIdentity` | `{deviceLabel?}` | identity obj (mints `workspace_uuid` via `crypto.randomUUID()`, stamps `created_at` once) | yes | gated | `setSetting`/`dbRun` |
| `migrateOpfsRelationshipsToFolder` | `{}` | `{ok,bytesWritten,lastSavedAt,counts}` | yes (writes `<folder>/Fellows/relationships.db`; **non-destructive** — OPFS copy intact until verified) | gated | **≈ `writeRelationshipsToFolder` :2509** — prefer reuse + call `ensureWorkspaceIdentity` first; new op optional sugar |

Internal (not an RPC): `_stampWriteGeneration()` folded into the OPFS commit transaction of every mutating handler (`createGroup` :897, `updateGroup` :927, `deleteGroup` :937, `setSetting` :968) so `write_generation`/`last_written_at` advance **atomically with the data** and survive backup/restore.

**Probe reason codes** (each → a troubleshooting-page anchor): `picker_cancelled`, `subfolder_create_failed`, `write_failed`, `readback_mismatch` (the durability proof — catches cloud/virtual folders), `permission_not_persisted`.

**Reuse map (don't reinvent):** `_findOrCreateSubfolder` (auto/create-new/open-existing) :1914; `_probeSubfolder` :1993; `_folderQueryPermission` :2029; IndexedDB `fellows-fs-handles` persist/hydrate :1871/:1890; `_writeBytesToFolder` (atomic, Web-Lock-guarded) :2249; `writeRelationshipsToFolder`/`readRelationshipsFromFolder` :2509/:2571; `inspectBytes` (validate + counts) :582; backup ring :2315-2354; `getFolderHandleForReconnect` :2504; `_folderStateSnapshot` :2048.

## B. DOM / CSS contract (STYLE ↔ CORE must agree on these exact names)

- **Body flags:** `body.is-phone` (CORE sets at boot `app.js:11100`, layout only), `body.no-private-data` (CORE sets from `privateDataEnabled()`, feature gate). Scrollers (no rename): `#directory`, `#detail`, `#app-wrap`, `#site-header`, `.appbar`.
- **Nav drawer (new DOM):** `#nav-drawer`(`.drawer`), `#nav-scrim`(reuses `.sheet-scrim`); `.drawer__head/__title/__nav`, `.drawer-link`(+`--active`), `.drawer__foot`, `.build-tag`. Hamburger = repurpose `#appbar-kebab`.
- **Directory:** `.directory-row`, `.directory-row__name`, `.directory-row__go`(chevron); filter bar `.filterbar`, `.filter-btn`, `.filter-chip`, `.filter-chip__x`, `.filterbar__count` (state ids unchanged: `#filter-trigger`, `#has-email-filter`, `#filter-count`).
- **Fellow detail:** `.contact-cta`; button family `.btn/.btn--primary/.btn--ghost/.btn--danger/.btn--block` (disabled via `aria-disabled="true"`); `.fellow-hero`, `.fellow-photo`, `.fellow-name`, `.fellow-tagline`, `.tag-chips`, `.tag-chip`, `.section-head`.
- **Settings/About:** `.card`, `.stat-line(__label/__value)`, `.tool-row(--danger,__go)`, `.section-head`, `.hint`. Tool handlers reuse kebab proxy targets `#diag-toggle`, `#bug-report-button`, `#clear-app-cache-button`, `#reset-everything-button` (`app.js:3542-3582`).
- **Desktop gate state (new, NOT in mobile mockup):** `.settings-section--unavailable`, `.settings-section-gate`, `.settings-section-gate__badge`(`--unsupported`), `.settings-section-gate__cta`. Gated on `folderStorageOffered()` `app.js:8659`.
- **Shared, no rename:** `.appbar/.appbar__title/.appbar__kebab`, `.tabs` (CORE hides on phone, STYLE `body.is-phone .tabs{display:none}`), `.sheet/.sheet__handle/.sheet__head/.sheet-scrim`, `#filter-sheet`.

## C. Surface inventory — gate treatment per site (the CORE worklist)

Legend: **H**=hidden-on-phone (JS-skip render), **G**=grayed-on-desktop-no-folder (+ "Enable on Chrome desktop →"), **R**=route redirect/lock, **L**=leave-as-is.

- Boot: add both body-class toggles next to `setShellVisible(true)` `app.js:11100`.
- Directory select `.dir-mark` `5787-5800` (H+G); name link `5801-5806` (L); `#bulk-select-bar` `index.html:408` + `updateBulkBar` `6324` / `bulkToggleVisible` `6341` / `toggleDraftMember` `6306` (H+G/no-op).
- Composer: `#group-rail` `index.html:419` + `renderRail` `6258`; `updateComposerFabFromDraft` `3592` (force-clear `has-selection`); `#composer-fab/-scrim` `index.html:439` + `initComposerFab` `3648` (H).
- Fellow detail `renderDetail` `5888`: `.detail-add-to-group` `5906-5916` (H+G); `mailto:`/`tel:` rows `5951/5959` (L); add `.contact-cta` on phone.
- Edit: `enterEditMode` `6449`, `#edit-mode-banner` `index.html:321` (H/R).
- **`route()` `7171`** — NO guard exists today; add gate intercept before dispatch for `#/groups`, `#/groups/<id>`, `#/groups/<id>/directory`, `#/edit/<id>` (`7276-7296`): phone→`location.replace('#/')`; desktop-no-folder→unlock/help. Group sheets `index.html:453-494` (H).
- Nav: Groups tab `index.html:276` + `#tabs` (H); desktop `.site-nav` Groups link `index.html:316` (G); kebab `#appbar-kebab`/`#kebab-sheet` (H→hamburger).
- Settings `renderSettingsPage` `8975`: self-email `8984` (L, but H per mobile PR5); folder `8997` / download `9018` / restore `9037` / MCPB `9061` (H + G — these ARE the unlock entry / private surfaces); `wireFolderSection` `9895`; **dead-on-phone** badge branch `isMobileDevice()` `9945` (remove, don't leave).
- Always-available: `#has-email-filter` + `applyFilters` `5478` + filter sheet `5698` (L); About stats `7034` (L).
- CSS sites: scroll model `475/712`; desktop shell hide `4307`; mobile focus block `4323`; FAB/composer/group-sheet `4634-4740`.

## D. Shared-mode leaks to fix in PR1 (the gate's §3 "localStorage-only" is not true today)

1. **`saveHasEmailFilter()` `app.js:5246-5254`** mirrors to `relationships.settings`; **`reconcileHasEmailFilterOnBoot()` `5263-5283`** reads it back. In `no-private-data` mode these `dataProvider.setSetting/getSetting` calls must be no-ops (localStorage only) — else they open/write `relationships.db`, contradicting "do not open relationships.db for durable data when locked."
2. **`persistDraft()` `app.js:6377`** — confirm it's localStorage-only (group draft); if it writes `relationships.db`, same fix.
3. Self-email already localStorage (`FELLOWS_SELF_EMAIL_KEY` `app.js:258`) + mirrored to settings — same treatment: localStorage-only in shared mode.

## E. Test plan (drives Lane TESTS)

**Breaking (rewrite/fixture-change):** `mobile/test_mobile_interactions.py` (FAB/composer/create-group/kebab/groups-card — delete, add drawer/row→detail/CTA/redirect/reduced-settings); `mobile/test_routes.py` group screenshots (redirect state); `mobile/test_mobile_layout.py` (row selectors + assert bounded scroller); `mobile/test_folder_gate.py::test_download_button_stays_visible_on_mobile` (delete/invert); **desktop group suite** `test_groups_{index,compose,detail,edit,export}.py` (new **folder-attached fixture** that flips `privateDataEnabled()` true — behavior unchanged once unlocked); `test_settings.py` (split shared-mode email from folder-mode groups/restore); `test_route_focus_mode.py`, `test_unsupported_browser.py` (gated-copy).

**New:** gate-locked-default; unlock happy path; 5 probe-failure paths (esp. `readback_mismatch` via a stub handle returning wrong bytes); same-browser OPFS→folder migration; reconnect re-grant (handle present); chooser disambiguation (seed `Fellows`+`Fellows 2` w/ different recency); in-db identity stamp; grayed-desktop vs hidden-phone; `#/groups` redirect/lock; mobile scroll container; Email/Call CTAs; self-describing export filename + `HOW-TO-MOVE-THIS-DATA.txt` marker.

**Harness:** folder mode simulated by `_STUB_DIRECTORY_PICKER` (OPFS-backed real handle) `test_user_folder_storage.py:35-182`; mutations via `window.__dataProvider` (`WorkerDataHelper` `conftest.py:99-225`); gate read via new `window.__privateDataTier` / `body.classList`. Probe-failure tests need new stub variants that make the handle misbehave.

**Port serialization (the real concurrency cap):** `tests/conftest.py:75-107` `_free_port(8765)` does `kill -9` on whatever holds 8765 → concurrent server-based runs across worktrees are **mutually destructive**, not just flaky. Rule: **treat 8765+8766 as one global mutex** — at most one worktree runs any server recipe (`test`/`test-fast`/`test-api`/`test-e2e`/`test-mobile`) at a time. Parallel-safe everywhere: `tests/test_database.py` (`just test-db`) + pure-logic unit files (no server, no port).

## F. Resolved defaults for the small open decisions

- **`.tag-chip` has no data source** off-folder (per-fellow tags live in the hidden `relationships.db`). **Decision:** defer tag chips on phone — do NOT derive from cohort/fellow_type for v1; STYLE ships the CSS unused. Revisit if wanted.
- **`.fellow-photo` initials fallback** is new logic (current no-image path emits "Not Submitted" `app.js:5933-5936`). **Decision:** CORE computes initials from `name` for the phone hero square.
- **`write_generation` monotonicity on restore:** restoring an older backup carries a lower generation → could mis-rank the chooser "recommended." **Decision:** on restore, re-stamp `write_generation = max(local, imported) + 1` so the just-restored store is canonical.
- **`device_label` source:** **Decision:** UA-derived default string (editable later); `ensureWorkspaceIdentity` defaults it when the page passes nothing.
- **Re-init after unlock:** after probe+migrate, `_storageMode` is only resolved at `init` (`:712`). **Decision:** the unlock flow forces a worker re-init (or an explicit "switch to folder mode now" op) so `_maybeWriteFolderAfterCommit` starts mirroring without a reload — confirm path during PR4.
- **`auto` collision vs chooser overlap:** **Decision:** the chooser (`scanFellowsCandidates`, all `Fellows*`) supersedes `auto`-collision for re-pick; `probeFolderWritable` is used only for fresh-pick/create.
