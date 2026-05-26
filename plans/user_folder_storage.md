# User-Folder Durable Storage

A plan to move the durable home of the user's private relationships data out of browser-managed OPFS and into a user-chosen folder on their filesystem, following the VS Code for Web pattern: **browser as runtime, filesystem as durable home.**

> **Status: UPDATED 2026-05-26.** Phases 0, 0b, 1, and most of Phase 2 have shipped (see § Phases for the per-PR breakdown). Phase 2 pivoted from the original *"hybrid OPFS-working + debounced folder sync"* design to **pure folder for folder-mode users** (mem-resident SQLite + atomic full-file folder writes per commit). The pivot eliminates a silent-data-loss failure mode that surfaced during Phase 2 scoping and aligns the data path with the project's MCP + multi-client trajectory. The architectural decision is recorded in [`docs/ac_decisions_log.md` § 2026-05-22](../docs/ac_decisions_log.md). § Architecture below describes the design; obsolete hybrid material has been removed (git history preserves the prior version).
>
> **Functionally remaining to close out Phase 2:** Web Locks multi-tab guard around folder writes, plus two E2E scenarios (permission revoked mid-session → retry; tab close with pending write-failed mutation). See § Phase 2 below.

## Context

Today, `relationships.db` lives in OPFS (Origin Private File System), owned by `vendor/sqlite-worker.js` per the local-first plan. OPFS is fast (sqlite-wasm gets `FileSystemSyncAccessHandle`), private to the app's origin, and survives Clear App Cache. But it has three load-bearing user-experience problems:

1. **Invisible.** Users can't see, browse, back up, or move their `relationships.db` from outside the app. The "Where your data is stored" copy in `users_manual.md` essentially apologizes for this.
2. **Browser-coupled.** Clearing site data, switching browsers, switching devices, or having Android `Clear Storage` invoked on the browser all silently destroy data. The auto-backup ring is also in OPFS, so it dies with the same wipe.
3. **No external observability.** Backup is a manual download-then-store-the-file flow the user has to remember. Auto-backups don't escape OPFS.

VS Code for Web shows the inverse model: open a folder, work in the browser, every save is a real write to the user's filesystem. Files behave like files. Other apps can read them, sync services (iCloud Drive, Dropbox, Syncthing) can replicate them, the user can `cp` them. The browser is just the runtime.

This plan brings that model to `relationships.db`.

## Goals

G1. **A real file at a real path.** After first-run setup, `relationships.db` exists at a user-chosen filesystem path. The user can browse to it in Finder / Explorer / `ls`. Auto-backups land in the same folder.
G2. **Durable across browser-data wipes.** Clearing site data, switching browsers (on the same machine), and switching browser profiles do not destroy the user's data — the folder survives.
G3. **Persistent permission across sessions.** A `FileSystemDirectoryHandle` saved in IndexedDB is re-acquired on every launch without re-prompting the user, when the underlying OS permission is still granted.
G4. **Honest "saved" semantics.** The UI displays "Saved to `<path>` at `<time>`" only after a successful write to the user's folder. Until then, status is explicit: "Pending save," "Browser-only (unsafe)," or "Folder inaccessible — re-select."
G5. **No silent data loss.** Under the pure-folder design, failures are surfaced honestly: a folder write that fails leaves the in-memory state with the un-persisted mutation and the badge displaying *"Last save failed — Retry to save again."* The user knows immediately. If they close the tab without retrying, the mutation is lost — same posture as any non-syncing draft editor. There is no scenario in which a stale storage substrate silently overwrites newer data.
G6. **Graceful degradation on unsupported browsers.** On Safari, Firefox, and mobile (no `showDirectoryPicker`), the app continues to work in today's OPFS-only mode with an explicit "Browser-only (unsafe)" badge and a documented manual-backup workflow. These users have **one source of truth (OPFS)**; no hybrid for them either.
G7. **Migration without data loss.** Existing Phase 1 users with both OPFS contents and a folder handle are migrated on first boot post-pivot to the pure-folder design — the newer of the two stores becomes canonical, the other is retired. See § Architecture → Migration.

## Non-goals

- **`fellows.db` moves too.** Out of scope. `fellows.db` is a refreshable snapshot of a remote source — losing it means re-downloading, not losing user-created data. Stays in OPFS.
- **Multiple folders.** One folder per origin. Power users with multiple "directories of relationships" can wait until there's evidence demand exists.
- **Conflict resolution for folders synced across devices** (Dropbox, iCloud Drive, etc.). The folder is a single-writer durable store. Two browsers pointed at the same Dropbox-synced folder will produce dueling writes; we'll warn but not resolve.
- **Live folder watching.** `FileSystemObserver` is landing in Chrome but we don't depend on it. Pure write-out; no read-on-external-change.
- **Cross-device handle portability.** A directory handle is scoped to one browser on one machine. Moving to another machine requires re-picking a folder (typically a synced folder pointing at the same backing storage).
- **Folder-first as the only mode.** Even on Chromium, "Browser-only" remains a valid (unsafe-flagged) state for users who decline to pick a folder. We surface the warning; we don't force the choice.
- **A hybrid OPFS-working + folder-mirror design.** The original plan had one. The revision dropped it for the reasons in [`docs/ac_decisions_log.md` § 2026-05-22](../docs/ac_decisions_log.md). The current design is two distinct storage modes, each with a single source of truth — see § Architecture.

## Refreshable assets (images, fellows.db, etc.)

The plan above is about `relationships.db` — *user-authored* data we cannot regenerate from any other source. A separate class of assets is *refreshable*: bytes the server can hand back any time, that lose nothing if locally destroyed. Today that's `fellows.db` (regenerated from the Knack source on every build) and the ~250 profile images served from `/images/<slug>`.

The plan keeps `fellows.db` in OPFS by design — the per-build SHA in `/build-meta.json` already handles "is my local copy stale?" — but it does not yet address **images**. The gap matters: images are session-gated on prod, so a user who installs while their session is expired (or whose first boot lands in api+idb fallback for any other reason) gets *zero* profile photos and no mechanism to fill them in until they re-authenticate. We have a real user-report of this in the wild.

Three options, listed in increasing scope:

**Option A — Skip prewarm on unauthenticated boot + completeness counter.** The current image prewarm fires ~500 doomed requests every cold boot in api+idb fallback. Gate it on `authStatus.authenticated`. Add an About-page row: `Images: 230 / 251 cached — Sign in to fetch the rest` (linking to `/?gate=1`). Smallest possible fix; doesn't make images durable across browser-data wipes. Shippable independently of any folder work.

**Option B — Bundle images in the static bundle.** ~250 × ~30 KB ≈ 7-10 MB added to `deploy/dist/`. Images become as durable as `app.js` and signed by the same manifest. Trade-off: every directory-data update re-downloads all images even if only one changed. Could be mitigated by per-image hashes in `build-meta.json`, but that's its own work.

**Option C — Sync images into the user's folder once folder-mode is active (Phase 1+).** Folder-mode users get full durability — images survive Clear Site Data, browser switches, even hardware moves through a synced folder. OPFS-only users (mobile, Safari, Firefox) still need Option A as the floor since folder-mode never lands for them.

**Recommendation:** Option A now (it's a current production bug). Option C with Phase 2 (along with auto-sync). Option B held in reserve in case the bundle-weight conversation tips that way later.

Out of scope either way: a sync strategy for `fellows.db` itself. That's an existing concern handled by Check for updates → Update directory data and is unchanged by this plan.

## Browser compatibility matrix

| Browser / mode | `showDirectoryPicker` | Persistent handle re-grant | Behavior in this plan |
|---|---|---|---|
| **Chrome / Edge / Brave (desktop, including PWA window)** | ✅ | ✅ via IndexedDB | Full feature. First-launch wizard. |
| **Arc** | ✅ (Chromium) | ✅ | Same as Chrome. |
| **Safari (desktop)** | ❌ (as of 2026 — `showOpenFilePicker` / `showSaveFilePicker` only; no directory) | n/a | Today's OPFS path, with persistent "Browser-only (unsafe)" badge + manual download/restore workflow. |
| **Firefox** | ❌ (no File System Access API) | n/a | Same as Safari. |
| **iOS Safari (incl. PWA)** | ❌ | n/a | Same as Safari desktop. |
| **Android Chrome (incl. PWA)** | ⚠️ Partial; directory picker exists but reliability and UX are mixed; OS app-data wipe via *Clear Storage* still beats the model. | ⚠️ Partial | **v1 treats mobile as unsupported.** Reuses the desktop-Safari fallback. Revisit when File System Access on Android matures. |

Bright line: **the user-folder feature is opt-in and additive.** Today's OPFS-only flow continues to work on every supported browser. We never block boot on the API being available.

## Architecture: two storage modes, one source of truth per user

Each session resolves to exactly one of two modes at worker boot, decided by whether a usable `FileSystemDirectoryHandle` is persisted in IndexedDB. There is no hybrid; the two modes do not share state and there is no sync between them.

```
┌──────────────────────────────────────────────────────────────────┐
│  worker (sqlite-worker.js) — mode resolved at boot                │
│                                                                   │
│  has folder handle + permission granted?                          │
│   │                                                               │
│   ├── YES ──► FOLDER MODE                                         │
│   │           ┌──────────────────────────────────────────────┐    │
│   │           │ relationships.db: mem-VFS (sqlite-wasm       │    │
│   │           │   in-memory DB, hydrated from folder bytes)  │    │
│   │           │                                              │    │
│   │           │ boot   : read folder/Fellows/relationships.db│    │
│   │           │          → sqlite3_deserialize into mem-VFS  │    │
│   │           │                                              │    │
│   │           │ commit : sqlite3_serialize → atomic write    │    │
│   │           │          to folder/Fellows/relationships.db  │    │
│   │           │          (createWritable → write → close)    │    │
│   │           │                                              │    │
│   │           │ backup : on successful commit, rotate the    │    │
│   │           │          folder-resident bak.<ISO> ring      │    │
│   │           │                                              │    │
│   │           │ fellows.db: stays in OPFS (refreshable,      │    │
│   │           │          read-only; not part of this mode)   │    │
│   │           └──────────────────────────────────────────────┘    │
│   │                                                               │
│   └── NO  ──► OPFS-ONLY MODE                                      │
│               ┌──────────────────────────────────────────────┐    │
│               │ relationships.db: OPFS-resident SAH-pool VFS │    │
│               │   (today's behavior, unchanged)              │    │
│               │                                              │    │
│               │ backup : OPFS-resident bak.<ISO> ring +      │    │
│               │          manual download-to-Downloads        │    │
│               │                                              │    │
│               │ durability: bounded by browser storage —     │    │
│               │   user is warned via the "Browser-only       │    │
│               │   (unsafe)" badge.                           │    │
│               └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### Why pure folder, not hybrid

The original plan chose a hybrid OPFS-working + debounced-folder-sync model. During Phase 2 scoping we identified a silent-data-loss failure mode (boot reads stale folder DB, overwrites unsynced OPFS data, recent mutations vanish without an error indication) and recognized that the hybrid's performance argument doesn't apply at our DB scale (sub-millisecond folder writes for our ~100 KB DB). Full reasoning lives in [`docs/ac_decisions_log.md` § 2026-05-22 — User-folder storage uses pure-folder semantics for folder-mode users, not a hybrid OPFS+folder mirror](../docs/ac_decisions_log.md).

Summary of the trade-offs we accepted:

- **Per-mutation latency.** Each commit now waits on a folder write. Sub-ms for ~100 KB DBs; ~tens of ms even at 10 MB; only user-noticeable if `relationships.db` ever exceeds several MB. Optimization paths (incremental writes, write-coalescing) are available if/when the DB grows.
- **In-memory state lost on tab crash.** If a user makes a mutation and the tab crashes before the folder write completes, the mutation is lost. The badge state reflects this honestly: "Pending save…" or "Last save failed — Retry to save again." Same UX posture as any non-syncing draft editor.

In exchange:

- One source of truth per session. No state-divergence bugs are possible because there is no second store to diverge from.
- The folder file IS the user's data, at all times. External readers (MCP servers, command-line `sqlite3`, manual `cp`, sync services like Dropbox) see the current state without needing to reason about staleness.
- Dramatically simpler worker state — no sync timers, dirty markers, in-flight guards, last-sync-attempt tracking, or boot-time divergence detection.

### sqlite-wasm details

- **Folder-mode worker** opens `relationships.db` with sqlite-wasm's `:memory:` (or equivalent mem-VFS). On boot, the folder file's bytes are deserialized into the mem-DB via `sqlite3_deserialize`. On each committed mutation, `sqlite3_serialize` exports the current DB to bytes; those bytes are written atomically to the folder file via `FileSystemFileHandle.createWritable() → .write(bytes) → .close()` (close commits atomically per the FileSystem Access API spec).
- **OPFS-only-mode worker** keeps today's behavior: `OpfsSAHPoolVfs` against an OPFS-resident slot; sync access handles for fast reads/writes; no folder involvement.
- **`fellows.db` is unchanged in both modes**: OPFS-resident, read-only, refreshable from the server. The folder-mode worker still uses OPFS for `fellows.db` (it's not user-authored data).

### Per-commit write path (folder mode)

For each mutating RPC (`createGroup`, `updateGroup`, `deleteGroup`, `setSetting`, `importRelationshipsBytes`, `restoreRelationshipsBackup`):

1. Mem-DB executes the SQL transaction; commits or rolls back as usual.
2. If the transaction committed, serialize the DB and write to `<parent>/Fellows/relationships.db`.
3. If the write succeeds, update `folderRecord.lastSavedAt`; badge stays "Saved."
4. If the write fails, set `folderRecord.lastError`; badge flips to "Last save failed — Retry." The mem-DB still holds the committed change — the user can retry, make another mutation (which re-attempts the write), or close the tab (in which case the change is lost honestly).

There is no debounce. There is no separate sync timer. Each commit attempts its own write. For very rapid-fire mutations (e.g., a multi-step bulk edit), the page-side code should batch into a single RPC where reasonable — but a series of sub-ms writes is also fine.

A single-flight guard around the folder write prevents concurrent `createWritable` calls from racing if RPCs land overlappingly (the worker is single-threaded for JS but mutation handlers are async).

### Auto-backup ring (folder mode)

- **Location**: siblings of `relationships.db` inside the `Fellows/` subfolder. Filenames: `relationships.db.bak.<ISO-timestamp>` (matches today's OPFS pattern). Visible in Finder.
- **Trigger**: same debounce as today's OPFS auto-backup — newest `bak.<ISO>` older than 1 hour means a new backup is due. Triggers from the per-commit write path: after a successful main-file write, check whether a backup is due; if so, write one and rotate.
- **Rotation**: keep newest N (currently 3); delete older ones from the folder.
- **Pre-import undo snapshot**: `importRelationshipsBytes` and `restoreRelationshipsBackup` still take a pre-restore snapshot first (today's behavior). In folder mode, that snapshot lands in the folder ring rather than OPFS.

### Boot sequence (revised)

1. Worker spawns.
2. Worker opens OPFS pool, attaches `fellows.db` RO (unchanged from today). This always happens; `fellows.db` lives in OPFS in both modes.
3. Worker reads the saved folder handle from IndexedDB (`fellows-fs-handles` / `relationships-folder` — already shipped in Phase 1).
4. **No handle persisted** → OPFS-only mode. Open `relationships.db` against `OpfsSAHPoolVfs`. Bootstrap schema if absent. Done.
5. **Handle persisted** → call `queryPermission({mode: 'readwrite'})`:
   - `'granted'` → **folder mode.** Read `<parent>/Fellows/relationships.db` bytes. If file exists, `sqlite3_deserialize` into mem-VFS. If folder is empty (handle present but no `relationships.db` yet) and OPFS contains a usable working copy from before the pivot, run migration (see below). Otherwise bootstrap schema into a fresh mem-DB and do an immediate folder write so the file exists. Set status to "Saved."
   - `'prompt'` or `'denied'` → **degraded folder mode.** Open `relationships.db` against `OpfsSAHPoolVfs` (today's behavior, as a fallback working store). Surface "Reconnect data folder" CTA. **Do not auto-prompt for permission** — no user gesture available at boot. Once the user clicks Reconnect and permission flips to `'granted'`, the worker migrates the OPFS state into the folder (treating OPFS as the canonical "what we have right now"), then closes the OPFS handle and continues in folder mode for the rest of the session. The badge transitions Inaccessible → Saved without an intermediate "Browser-only" state.
6. **Edge case: folder empty + no OPFS state** → bootstrap a fresh schema into mem-DB, immediately write to folder. New install.
7. **Edge case: folder file is corrupt / unreadable** → surface "Folder data unreadable — would you like to restore from a backup or start fresh?" Use the folder-resident `bak.<ISO>` ring (or, for migrating users, the OPFS backup ring as a last-ditch source).

### Migration from Phase 1 (one-time)

Existing Phase 1 users may have both an OPFS-resident `relationships.db` (Phase 1's working store) and a folder-resident copy (from manual saves). On first boot after the pivot:

1. **Both present:**
   - Read OPFS `relationships.db` bytes.
   - Read folder `relationships.db` bytes.
   - Compare: serialize each, hash, compare. If identical, use the folder copy (canonical going forward), close the OPFS slot.
   - If different, compare timestamps. The original plan trusted the folder by default — under the pivot, **trust the newer of the two**, on the rationale that the Phase 1 hybrid's biggest failure mode was OPFS being newer than the folder due to a sync miss. Write the newer one to the folder, retire OPFS.
   - In the unlikely case the user wants to inspect both, the just-retired OPFS state is preserved as an additional `relationships.db.bak.<ISO>` in the folder ring (with a `pre-pivot-` prefix to distinguish from normal rotation entries).
2. **OPFS only (folder handle exists but folder file missing)**:
   - The user picked a folder in Phase 1 but never manually saved. Write the OPFS state to the folder atomically, then retire OPFS.
3. **Folder only (no OPFS `relationships.db`)**:
   - A user who picked a folder, saved at least once, then had OPFS evicted. Load folder into mem. Done.
4. **Neither**:
   - Fresh install. Bootstrap schema into mem; immediate folder write.

Migration runs once per session for users who haven't yet migrated. A flag in `folderRecord` (`pivotMigratedAt: ISO`) is set on completion; subsequent boots skip the migration check.

### Multi-tab considerations

Both modes need a single-writer guarantee: two tabs writing to the same `relationships.db` (whether in OPFS or in the folder) will produce dueling writes. Phase 1 inherits the existing `multi_tab_ownership_takeover.md` design — one tab owns the worker at a time. The pivot does not change this; if anything it simplifies the boundary (the worker holds an exclusive folder-file handle while writing; other tabs see a "Another tab is using this folder" error if they try to spawn a competing worker).

### What stays from Phase 1

The 540 lines of folder code shipped in PR #181 are mostly unchanged by the pivot. Specifically:

- **IDB handle persistence** (`fellows-fs-handles` / `relationships-folder`) — unchanged.
- **Subfolder layout** (`<parent>/Fellows/`) — unchanged.
- **Subfolder collision handling** (auto / open-existing / create-new) — unchanged.
- **Permission lifecycle** (queryPermission + user-gesture requestPermission) — unchanged.
- **Status badge state machine** (6 states) — unchanged at the UI layer; the worker's state-snapshot RPC reports the same shape.
- **Settings UI** (Choose / Save / Refresh / Reconnect / Disconnect buttons) — unchanged. "Save now" becomes a manual override / retry button rather than the primary save mechanism (which is now every commit).
- **`writeRelationshipsToFolder` worker logic** — the actual atomic write is the same code, just called from a different place (per-commit rather than per-button-click).
- **E2E test scaffolding** — extended for the new boot path + migration.

## UI / UX

### Status surfaces: durability vs completeness

The status badge below tracks **where your data is saved** — Browser-only / Pending / Saved / Folder inaccessible. That is "data durability."

A separate concern, surfaced elsewhere, is **install completeness** — has the app downloaded every refreshable asset it depends on, so subsequent server-less use is fully functional? On a normal authenticated install, prewarm fills the image cache and the answer is yes. On an install whose first boot landed in api+idb fallback (expired session, anti-enum 403, etc.), the answer is no — *and the durability badge has no way to express that.* The user's data is durable; the install itself is partial.

Don't conflate the two in the same badge. Surface completeness on the About page (where the user already goes to ask "is everything okay with this install?") as a separate row, with a link to sign-in when items are missing. The signal evolves as Phase 1 / 2 land — once images sync into the user's folder, the same "X of N images present" check applies, just against a different storage substrate.

### Status badge (the load-bearing UI element)

Lives in Settings → top of the *Your saved data* section, and also as a small pill in the app's persistent header (mobile redesign mockup-compatible).

| State | Badge text | Color | Affordances |
|---|---|---|---|
| Saved | `Saved to /Users/rich/Documents/Fellows • 2 min ago` | green | "Show in Finder", "Change folder…" |
| Pending save | `Saving to folder…` | neutral | (none — transient, ~500ms) |
| Browser-only (no folder ever chosen) | `Browser-only — your data is not yet saved to disk` | yellow / warning | **"Choose a data folder…"** CTA |
| Folder selected but inaccessible | `Folder set but unreachable — reconnect to keep saving` | yellow / warning | **"Reconnect folder…"** CTA |
| Sync failed (last attempt errored) | `Last save failed (<reason>) • Retry` | yellow / warning | **"Retry now"** + "Change folder…" |
| Unsupported browser | `Browser-only — this browser doesn't support saving to a folder` | yellow / warning | Link to docs explaining the manual backup flow |

Critical rule: **"Saved" is shown only after a write to the user's folder has been acknowledged by the OS.** OPFS writes alone are never "Saved" — they're "Pending" or "Browser-only," depending on whether a folder has ever been chosen.

### First-launch wizard (was Phase 3 — deferred / likely absorbed)

The original plan had a Phase 3 banner + flow for OPFS-only users to switch to folder mode. Status now: **deferred**; likely absorbed into the MCP install wizard described in [`plans/easy_mcp_install.md`](./easy_mcp_install.md), since folder setup is the prerequisite for MCP integration and the natural moment a user becomes interested in switching modes. If a standalone first-launch wizard is still wanted post-Phase-2, the original shape applies:

1. Banner above the directory: *"Your data is currently only in this browser. Choose a folder to save it to disk."* Dismissible (continues OPFS-only mode), one click to engage.
2. On click, native folder picker. User picks (or creates) a folder.
3. App writes the current OPFS contents (relationships.db + the existing auto-backup ring) to the folder atomically — same migration path described in § Architecture → Migration.
4. Worker swaps from OPFS-only mode to folder mode for the rest of the session and future sessions.

### Settings page additions

In the existing *Your saved data* section, above the existing download / restore buttons:

- **Data folder:** `<path>` or `Not set` — with **Choose folder…** / **Change folder…** / **Disconnect folder** buttons.
- **Last saved:** `<ISO time>` or `Never`.
- **Open folder:** invokes whatever the platform's "show in file manager" call is (limited support; degrade gracefully).

The existing "Download my user data" stays — it's still useful for grabbing a snapshot to email someone, restore on another machine, etc. The new "Saved to folder" state doesn't replace it.

## Permission model & handle persistence

### Storing the handle

`FileSystemDirectoryHandle` is structured-clonable, so it can be put directly into IndexedDB. We store it in a new IDB database `fellows-fs-handles`, key `relationships-folder`. Single entry; no need to manage multiple.

This survives Clear App Cache (per the existing behavior; IDB is not site-data in the OPFS-strict sense — but **it IS cleared by "Clear site data" / full reset**). Worth being precise in docs.

### Permission lifecycle

On each session start, we call `queryPermission({mode: 'readwrite'})`. The three return values map to:

- `'granted'` — proceed silently. No user-visible prompt.
- `'prompt'` — the OS needs user gesture to re-grant. **We do not auto-`requestPermission` on boot** (no user gesture available, would fail or pop a confusing dialog mid-load). Instead surface a "Reconnect data folder" button; clicking it is the gesture.
- `'denied'` — same UX path. We say "Folder was selected previously but permission has been denied — reconnect to continue."

If the user explicitly clicks "Disconnect folder," we delete the IDB entry and revert to "Browser-only (unsafe)."

## Phases

### Phase 0 — Worker-direct export / import — **✅ SHIPPED**

**Shipped in PR #174.** Decouples the page-side `dataProvider` from the worker's relationship-DB byte operations, which Phase 2's per-commit folder write needs anyway and which fixes a current production bug for free.

The page-level `dataProvider` today exposes `exportRelationshipsBytes` / `importRelationshipsBytes` only when its `kind === 'worker'`. When the page falls back to `api+idb` (most commonly because the session-gated `/fellows.db` fetch returned 401/403 during boot), the warm worker is still alive with `relationships.db` open, but the Settings backup and restore controls can't reach it — so users on an expired session can't back up their data before reinstalling or switching browsers.

Phase 2's per-commit folder write (under the revised pure-folder design) is written from the worker's perspective and similarly cannot depend on the active page-level provider. The plumbing is the same: a worker-direct path to the bytes, addressable regardless of which provider the page picked at boot. Landing it here shortens Phase 2.

- New page-side helpers that reach `warmWorker.rpc` directly:
  - `warmWorkerExportRelationshipsBytes()`
  - `warmWorkerImportRelationshipsBytes(bytes)`
  - `warmWorkerListRelationshipsBackups()` (for the auto-backup list in Settings)
- Settings page wires the download / restore buttons through the warm-worker helpers when `dataProvider.kind !== 'worker'` AND `isWorkerOpfsCapableButInactive()` (the helper added in the never-SaaS copy cleanup, PR #173).
- When the warm worker is genuinely absent (no OPFS, no worker init), keep today's "this feature isn't available" panel — that's the honest case.
- E2E: extend `tests/e2e/test_never_saas_copy.py` (or sibling) to seed the api+idb-fallback scenario, click Download, assert a real `relationships.db` blob comes back; click Restore on a known-good blob, assert the worker accepted it.

Out of scope for P0: anything about user-picked folders, the status badge state machine, IDB handle persistence, the migration wizard. Those all stay below.

### Phase 0b — Worker-direct groups RPCs — **✅ SHIPPED**

**Shipped in PR #175.** Same shape as Phase 0, extended to the five groups RPCs (`listGroups`, `getGroup`, `createGroup`, `updateGroup`, `deleteGroup`) so the entire `relationships.db` read/write surface — settings, backups, AND groups — stays reachable when the page falls back to api+idb. Without this, a user with an expired session could back up their data (P0) but couldn't browse the groups they were trying to back up.

- Prereq: hoist `attachMemberNamesFromCache` and `withResolvedMembers` out of `createWorkerDataProvider`'s scope to module scope. Both read only the module-level `fellowsBySlug` cache; the hoist is mechanical.
- Extend `viaWarmWorker` (added in P0) to accept an optional post-process function so `getGroup` / `createGroup` / `updateGroup` can chain `withResolvedMembers`.
- Five new methods on `createApiPlusIdbDataProvider`, same dispatcher pattern as P0.

Out of scope for P0b: version-skew gating on mutating group ops in the api+idb path. The worker provider gates create/update/delete with `refuseIfVersionSkew`; the api+idb fallback doesn't, on the rationale that the fallback path is already exceptional and worker-vs-page version skew is a separate SW-upgrade-race concern surfaced by the existing reload banner. Worth revisiting if real-user telemetry shows skew-related failures.

### Phase 1 — Folder picker + status UI + manual save/restore — **✅ SHIPPED**

**Shipped in PR #181 (commit `a344c52`).** Validates the API surface, the handle-storage model, and the status UI. Originally framed as "no automatic sync — the user explicitly hits Save"; under the pivot, that manual Save button becomes a retry affordance and the per-commit auto-write lands in Phase 2.

What shipped:

- `vendor/sqlite-worker.js` RPCs: `getFolderState`, `setFolderHandle`, `clearFolderHandle`, `checkFolderPermission`, `getFolderHandleForReconnect`, `writeRelationshipsToFolder`, `readRelationshipsFromFolder`.
- IDB handle persistence (`fellows-fs-handles` / `relationships-folder`).
- Subfolder collision dialog (open-existing vs. create-Fellows-N).
- Settings UI: Choose / Save now / Refresh / Reconnect / Disconnect; 6-state badge.
- Permission lifecycle + `FOLDER_CONTROLLER` glue on the page side.
- Diagnostics panel `Data folder:` row.
- E2E test (`tests/e2e/test_user_folder_storage.py`).

### Phase 2 — Pivot worker data path to pure folder (folder-mode users) — **✅ MOSTLY SHIPPED**

**The pivot.** Replaces the originally-planned "automatic debounced sync from OPFS to folder" with a VFS swap: folder-mode users get an in-memory SQLite that's hydrated from the folder file on boot and serialized back atomically on every committed mutation. OPFS-only-mode users are untouched. The auto-backup ring moves to the folder for folder-mode (Option A — visible in Finder, comforting).

Shipped across four PRs:

| PR | What landed |
|---|---|
| **#190** — foundation | VFS mode resolution at boot; `_hydrateOpfsBufferFromFolder`; `_maybeWriteFolderAfterCommit` post-commit hook on `createGroup` / `updateGroup` / `deleteGroup` / `setSetting` / `importRelationshipsBytes`; `_maybeRunPivotMigration` with `pivotMigratedAt` skip flag; `_writeBytesToFolder` atomic helper. |
| **#191** — backup ring | `_listFolderBackups` / `_folderReadBackup` / `_rotateFolderBackups` primitives; `_isFolderBackupActive` routing layer so `maybeBackupRelationshipsDb`, `snapshotRelationshipsDbToBackup`, `handlers.listRelationshipsBackups`, `handlers.restoreRelationshipsBackup` all dispatch to the active store; `_maybeMigrateOpfsBackupsToFolder` opportunistic migration with OPFS-shadow deletion. (Promoted out of Phase 4 ahead of schedule — Q7 resolved.) |
| **#192** — folder-push banner | Top-of-page yellow banner for capable-browser OPFS-only users; sessionStorage dismissal; users-manual update reflecting post-pivot reality. |
| **#193** — UI clarifications | File path below Saved badge; "Refresh from folder" → "Reload from folder"; hide redundant Download in active folder mode. |

Engineering scope reference (now historical — all done unless flagged):

1. ✅ **Worker boot — VFS selection.** (#190)
2. ✅ **Per-commit write helper** `_maybeWriteFolderAfterCommit`. (#190)
3. ✅ **Mutating RPC integration** on the 5 mutating RPCs. (#190)
4. ✅ **Auto-backup ring (folder mode)** with OPFS shadow retirement. (#191)
5. ✅ **Migration from Phase 1 state** with `pivotMigratedAt` flag. (#190)
6. ✅ **Status badge** — existing states cover everything. (no PR needed)
7. ⏳ **Multi-tab guard — Web Locks API.** Not yet shipped. `navigator.locks` has zero references in `app/static/`. Scope: wrap `_writeBytesToFolder` (and the migration writes that bypass it) in `navigator.locks.request('fellows-relationships-folder', { mode: 'exclusive' }, …)`; surface a "Another tab is editing your data" message when the lock is held.

Acceptance criteria for Phase 2:

- ✅ A Chromium-desktop user with folder mode active makes 5 group edits in quick succession; the folder's `relationships.db` matches the in-memory state after every commit. *Covered by `TestPhase2Pivot::test_post_commit_auto_writes_advance_last_saved_at` in `tests/e2e/test_user_folder_storage.py`.*
- ⏳ A user revokes folder permission mid-session; the next mutation surfaces `write-failed`; the in-memory DB still has the change; clicking "Retry" after re-granting permission persists the change. *Not yet tested.*
- ⏳ A user closes their tab with an unsaved (write-failed) mutation pending; on next boot, the folder still has the previous-known-good state; the in-memory mutation is honestly lost; badge shows "Saved" against the previous content (no silent overwrite). *Not yet tested.*
- ✅ A Phase 1 user (OPFS + folder both populated, different content) opens the app post-pivot; migration runs; the newer of the two becomes canonical; the loser lands in the folder backup ring with `pre-pivot-<ISO>` prefix. *Implemented in `_maybeRunPivotMigration`; covered indirectly by the pivotMigratedAt code paths.*
- ✅ A Safari / Firefox user sees no behavioral change (OPFS-only mode unchanged). *OPFS-only branch in `init` is unchanged.*

Out of scope for Phase 2:

- A first-launch migration wizard for OPFS-only users who want to switch to folder mode (that's Phase 3 below; superseded by the folder-push banner in #192).
- Image sync to folder (held for a sibling plan / Phase 2.5).
- "Show in Finder" / "Open data folder" affordances (Phase 4 polish).

### Phase 3 — First-launch folder-setup wizard (deferred / absorbed)

**Status: most likely absorbed into the MCP install wizard** (see [`plans/easy_mcp_install.md`](./easy_mcp_install.md) post-pivot). The original Phase 3 was a banner + flow for OPFS-only users to switch to folder mode. Under the new MCP-install plan, the MCP setup wizard is exactly the moment a user becomes interested in folder mode (so MCP can read their data). The standalone "I want to set up a folder for its own sake" flow may still be worth shipping — open question for after Phase 2 lands.

If kept as a standalone Phase 3:

- Banner for OPFS-only-mode users: *"Your data is currently only in this browser. Choose a folder to save it to disk."* Dismissible.
- One-click "Choose folder & save now" flow.
- Bulk export of current OPFS contents into the chosen folder (relationships.db + the OPFS-resident backup ring).
- Once complete, the user is in folder mode for the rest of the session and future sessions.

### Phase 4 — Polish & accessibility (post-MVP)

- "Show in Finder" via `showDirectoryPicker` round-trip when supported.
- "Open data folder" deep link if any platform exposes it without re-picking.
- Diagnostic panel additions (resolved folder path, last write attempt + outcome, current permission state, migration status).
- Maybe-eventual: `FileSystemObserver` watch on the folder so external edits surface as conflicts.
- ~~**Investigate retiring OPFS auto-backup ring entirely for folder-mode users.**~~ **Done in PR #191**, ahead of Phase 4. The OPFS shadow is migrated and deleted on first folder-mode boot.

## Plan-polish items

**G1 — Post-commit hook on relationships.db RPCs.** ~~Phase 2's spec says "Worker enqueues a sync after every committed mutation."~~ **Obsolete under the pivot.** Phase 2's per-commit write happens *inside* each mutating RPC handler (synchronously after the SQLite COMMIT, before the RPC returns). There is no separate debounced "sync queue" to mark dirty for. The simplification is one of the goals of the pivot, not an item to track.

**G2 — `fellows.db.meta.json` sidecar location.** The SHA-keyed sidecar that drives the About → Check for updates flow lives in OPFS at `fellows.db.meta.json` (sibling of the SAH pool). **Resolution: stays in OPFS** under both modes. It tracks `fellows.db` freshness on this device — per-device by definition; a new device starts with an empty sidecar and re-fetches naturally. `fellows.db` itself stays OPFS-resident in both modes (it's refreshable shared data, not user-authored), so its sidecar belongs alongside it. No migration needed.

## Open questions — resolved during Phase 1 ship + pivot

All resolved; preserved here for traceability.

**Q1 ✅ Folder layout:** subfolder. User picks a *parent* folder; we own `Fellows/` (with N-suffix collision handling) inside it. Shipped in Phase 1. Subfolder name in code is `FOLDER_SUBFOLDER_DEFAULT = 'Fellows'`.

**Q2 ✅ Pre-existing `relationships.db` in the picked folder:** confirm dialog with `open-existing` vs. `create Fellows N` choices, surfaced by the worker's `setFolderHandle({mode: 'auto'})` returning `{requiresChoice, existing, suggestion}` when a collision is detected. Shipped in Phase 1.

**Q3 ✅ Mobile:** unsupported in folder mode. iOS / Android default to OPFS-only mode. Revisit when the Android picker matures.

**Q4 ✅ Diagnostic surface:** "Data folder" subsection in the `?diag` panel. Phase 1 added the row at `app.js:2548`; Phase 4 polish will fill it out with permission + recent-write detail.

**Q5 ✅ Naming:** "Data folder" — used consistently in the Settings UI shipped in Phase 1.

## New open questions (post-pivot)

**Q6 — Phase 3 standalone vs. absorbed by MCP install wizard?**

The original Phase 3 was a first-launch banner for OPFS-only users to switch to folder mode. Under the new sequencing (MCP install plan depends on Phase 2), the MCP install wizard becomes a folder-setup trigger for any user who wants Claude Desktop integration. Open question: does a *standalone* Phase 3 still ship, or do we say "folder mode is the implicit prerequisite for MCP integration; if you don't want MCP, OPFS-only mode is fine"?

Lean: skip standalone Phase 3 in v1. Re-evaluate after Phase 2 + MCP install land based on real user feedback.

**Q7 ✅ When to retire OPFS auto-backup ring for folder-mode users?**

Promoted out of Phase 4 into Phase 2 itself. PR #191 migrates each OPFS backup into the folder ring on first folder-mode boot, then deletes the OPFS originals (`_maybeMigrateOpfsBackupsToFolder`). The "rip the band-aid off / earlier is fine" call paid for itself — no live shadow store means no future divergence to reason about.

## Testing approach

- **Unit:** IndexedDB handle round-trip; per-commit folder-write logic against a stubbed `FileSystemDirectoryHandle`; mem-VFS hydration round-trip (serialize → deserialize); migration-from-Phase-1 newer-copy detection.
- **Playwright E2E (Chromium):** seed a folder handle via CDP, exercise full save / load / disconnect / reconnect flows. Verify status-badge state machine.
- **Manual smoke:**
  - Chrome desktop PWA: full happy path.
  - Chrome desktop PWA + revoke permission via Site Settings → permission-prompt path.
  - Chrome desktop PWA + user-moves-folder-out-from-under-us → "folder inaccessible" state.
  - Safari desktop: confirms unsupported-browser badge appears without spamming errors.
  - Firefox: same.
  - iOS Safari PWA: same.

### Mobile verification

The plan calls mobile "unsupported in v1" for folder-mode itself — neither iOS nor Android Chrome will see the folder picker until / unless we revisit. But **the OPFS-only fallback path IS the mobile experience** and that path absolutely needs verification: the image-prewarm-on-fallback bug bit a real mobile user before we noticed it, and "we tested on desktop Chrome" did not catch it. We're shipping a PWA primarily consumed on phones; not having a mobile test loop is the gap that lets bugs like that ship to the user before we notice.

Options for adding a mobile test loop, listed in increasing fidelity / cost:

- **Playwright mobile emulation** (we use it today in `tests/e2e/mobile/`). UA + viewport spoofing. Catches CSS / layout regressions; does *not* replicate WebKit-on-iOS (Playwright Chromium is still Chromium under the hood) or Android Chrome's storage-eviction behavior. Better than nothing; insufficient on its own.
- **BrowserStack / Sauce Labs / similar.** Real iOS Safari and Android Chrome, scriptable from CI. Costs money; replicates engine + storage quirks. Worth it for security and privacy-sensitive features once we have the appetite.
- **Manual ship checklist on a personal phone.** Per-deploy smoke (≈ a quarter-hour). Catches the worst bugs; can't be automated. Belongs in `docs/users_manual.md` or a sibling so any maintainer can run it.

**Recommendation for #165:** before Phase 1 ships, formalize the manual mobile checklist as the floor; revisit cloud-device testing in Phase 4 alongside other polish. Even on desktop-only features, run the manual mobile pass once to confirm the OPFS-only fallback didn't degrade.

This is also a good time to remember the AC-12 commitment in `docs/Architecture.md` (capability detection inside the worker): mobile is where AC-12 gets stressed the most, since iOS WebKit constraints differ from desktop Safari's in ways that don't always surface in Playwright.

## Risks

- ~~**OPFS and folder drift permanently if sync keeps failing.**~~ **Eliminated by the pivot** — there is no second store to drift from in folder mode. The OPFS-only and folder-mode users each have a single source of truth.
- **User picks a folder inside a synced location (Dropbox/iCloud) and runs the app in two browsers.** Multi-writer is unsupported. Mitigation: Q2's "already has data here?" dialog catches first-attach; Web Locks API guard around folder writes (Phase 2) prevents in-browser races; multi-browser users see a "Another tab/browser is editing your data" error from the Web Locks rejection.
- **`Clear site data` still wipes the IDB-stored handle**, forcing re-pick. Mitigation: the FOLDER survives, so the user just re-picks and the data is unchanged. Documented in `users_manual.md` as the recovery path.
- **Browser auto-revokes file system permissions on idle eviction.** Chrome does this for tabs backgrounded for a long time. Mitigation: the `'prompt'` state and reconnect CTA cover this; the next mutation after re-grant succeeds and the badge transitions back to "Saved."
- **In-memory state lost on tab crash mid-mutation (folder mode).** Honest failure mode — the user sees "Pending save…" or "Last save failed" before the crash and knows the change wasn't committed. Document in `users_manual.md`.
- **Per-mutation folder-write latency at scale.** Sub-ms at current DB sizes; ~tens of ms at 10 MB. If `relationships.db` ever grows past several MB and users feel it, optimization paths (incremental writes via FileSystemSyncAccessHandle when the API lands for non-OPFS folders, write coalescing, etc.) become available. Not a v1 concern.
- **Migration from Phase 1 hybrid state mis-detects which copy is newer.** Mitigation: preserve the "losing" copy in the folder backup ring as `pre-pivot-<ISO>.bak` so the user can recover manually. Migration runs once per session until completed; sets `folderRecord.pivotMigratedAt`.

## Links

- File System Access API spec: <https://wicg.github.io/file-system-access/>
- VS Code for Web architecture talk (the reference design): <https://code.visualstudio.com/blogs/2021/10/20/vscode-dev>
- sqlite-wasm OPFS VFS docs: <https://sqlite.org/wasm/doc/trunk/persistence.md>
- sqlite-wasm serialize / deserialize: <https://sqlite.org/wasm/doc/trunk/api-c-style.md#sqlite3_serialize>
- Related plan: [`local_first_worker_architecture.md`](./local_first_worker_architecture.md)
- Related plan: [`easy_mcp_install.md`](./easy_mcp_install.md) — depends on the pure-folder anchor from this plan
- AC decision: [`docs/ac_decisions_log.md` § 2026-05-22](../docs/ac_decisions_log.md) — full reasoning for the pivot
