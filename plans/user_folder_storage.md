# User-Folder Durable Storage

A plan to move the durable home of the user's private relationships data out of browser-managed OPFS and into a user-chosen folder on their filesystem, following the VS Code for Web pattern: **browser as runtime, filesystem as durable home.**

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
G5. **No silent data loss on permission lapse.** If the OS revokes folder access (user moved the folder, denied permission on session restart, etc.), the app continues to operate against the OPFS working copy, surfaces a prominent reconnect prompt, and refuses to declare anything "saved" until the folder is reachable again.
G6. **Graceful degradation on unsupported browsers.** On Safari, Firefox, and mobile (no `showDirectoryPicker`), the app continues to work in today's OPFS-only mode with an explicit "Browser-only (unsafe)" badge and a documented manual-backup workflow.
G7. **Migration without data loss.** Existing users with OPFS-only data are walked through folder setup on their first launch of the new version; their current OPFS contents are exported into the chosen folder before anything changes.

## Non-goals

- **`fellows.db` moves too.** Out of scope. `fellows.db` is a refreshable snapshot of a remote source — losing it means re-downloading, not losing user-created data. Stays in OPFS.
- **Multiple folders.** One folder per origin. Power users with multiple "directories of relationships" can wait until there's evidence demand exists.
- **Conflict resolution for folders synced across devices** (Dropbox, iCloud Drive, etc.). The folder is a single-writer durable store. Two browsers pointed at the same Dropbox-synced folder will produce dueling writes; we'll warn but not resolve.
- **Live folder watching.** `FileSystemObserver` is landing in Chrome but we don't depend on it. Pure write-out; no read-on-external-change.
- **Cross-device handle portability.** A directory handle is scoped to one browser on one machine. Moving to another machine requires re-picking a folder (typically a synced folder pointing at the same backing storage).
- **Folder-first as the only mode.** Even on Chromium, "Browser-only" remains a valid (unsafe-flagged) state for users who decline to pick a folder. We surface the warning; we don't force the choice.
- **Replacing OPFS as the working store.** sqlite-wasm performs best against OPFS-resident `FileSystemSyncAccessHandle`s. The working DB stays in OPFS; the user's folder is the durable mirror. See § Architecture.

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

## Architecture: hybrid storage (OPFS working, folder durable)

```
┌─────────────────────────────────────────────────────────────────┐
│  worker (sqlite-worker.js)                                       │
│                                                                  │
│  ┌───────────────────┐         ┌──────────────────────────────┐ │
│  │ OPFS working DB    │ ──────► │ Sync-out (debounced):        │ │
│  │ (today's location) │  every  │   read .db bytes from OPFS,  │ │
│  │ relationships.db   │ commit  │   write to user's folder     │ │
│  └───────────────────┘         │   via FileSystemFileHandle    │ │
│           ▲                    └──────────────────────────────┘ │
│           │                                                      │
│           └─── boot: copy folder's .db into OPFS, then attach    │
└─────────────────────────────────────────────────────────────────┘
```

### Why hybrid, not pure-folder

- sqlite-wasm's fast VFS (`OpfsSAHPoolVfs`) needs `FileSystemSyncAccessHandle`. Sync access handles are **OPFS-only.** Files in user-picked folders only expose async `FileSystemFileHandle` / `FileSystemWritableFileStream`.
- A pure-folder model would either need a custom async-only VFS (every read/write becomes a Promise — measurable hit even for small DBs; complex code) or have sqlite-wasm work entirely in-memory and rewrite the whole file on every commit (correctness risk on crash; thrashes the OS file cache).
- Hybrid keeps today's working-store performance unchanged. The only new code path is "after a committed mutation, copy the .db bytes out to the user's folder." That's cheap (the DB is tens of KB), debounceable, and idempotent.

### Sync-out cadence

- **Trigger:** every committed write RPC the worker handles for `relationships.db` enqueues a sync.
- **Debounce:** 500 ms after the last commit, or 5 s max wait, whichever fires first. Tunable.
- **Atomicity:** write to `relationships.db.tmp`, then `move` to `relationships.db`. The user never sees a half-written file. The renaming pattern matches what `Atomics`-flavored save flows use elsewhere.
- **Failure:** logged + surfaced as "Sync failed at `<time>`: `<reason>` — Retry?" in the status badge. **The committed change in OPFS is not rolled back** — the working DB and the durable mirror diverge until the next successful sync. This is the only state where they ever diverge, and it's visible.

### Auto-backup ring

- Existing auto-backup logic moves to the user's folder. Filenames continue to follow the `relationships.db.bak.<ISO timestamp>` pattern.
- Rotation continues server-side-equivalent — keep the newest N (currently 3) backups; on each new backup, prune older ones in the folder.
- If the user inspects the folder, the rotation is visible: `relationships.db`, `relationships.db.bak.2026-05-14T10-32Z`, etc.

### Boot sequence

1. Worker spawns.
2. Worker opens OPFS pool, attaches `fellows.db` RO (unchanged from today).
3. Worker reads the saved folder handle from IndexedDB.
4. **If handle missing** → "Browser-only (unsafe)" state. OPFS working DB is the source of truth. Bootstrap schema if absent. Continue.
5. **If handle present** → call `queryPermission({mode: 'readwrite'})`:
   - `'granted'` → read `relationships.db` from the folder, copy into OPFS, attach. **"Saved" state.**
   - `'prompt'` → don't auto-prompt. Continue against OPFS working DB but surface a "Reconnect data folder" CTA in the status badge that, on click, calls `requestPermission`.
   - `'denied'` → same as `'prompt'` plus an explicit "Permission was denied; you'll need to pick the folder again."
6. **If handle present but folder empty / file missing** → "Folder selected but empty: was your data moved?" with options to "Restore from this folder's backups" / "Restore from the auto-backups inside OPFS" / "Choose a different folder" / "Start fresh in this folder."

A new mutation always lands in OPFS first, then syncs out. So a stale-permission session is still safe: the data is preserved in OPFS even if the folder write keeps failing.

## UI / UX

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

### First-launch wizard (Phase 3)

When an existing user (OPFS data exists, no folder handle set) opens the new version:

1. Banner above the directory: *"Your data is currently only in this browser. Choose a folder to save it to disk."* Dismissible (continues "Browser-only"), one click to engage.
2. On click, native folder picker. User picks (or creates) a folder.
3. App writes the current OPFS contents (relationships.db + the existing auto-backup ring) to the folder atomically.
4. Status flips to "Saved to `<path>`."
5. Subsequent launches from this browser auto-reconnect via the saved handle.

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

### Phase 1 — Folder picker + status UI + manual save/restore

**Shippable on its own.** No automatic sync; the user explicitly hits "Save to folder" or "Refresh from folder" buttons in Settings. Validates the API surface, the handle-storage model, and the status UI before adding cadence logic.

- New `vendor/sqlite-worker.js` RPCs: `getFolderHandle()`, `setFolderHandle(handle)`, `writeRelationshipsToFolder()`, `readRelationshipsFromFolder()`, `checkFolderPermission()`.
- Settings page UI for choose / change / disconnect folder.
- Status badge with the six states from § UI / UX (only the manual subset is wired — Saved / Pending / Browser-only / Folder inaccessible).
- Unit test for the IndexedDB handle persistence.
- E2E test (Chromium-only) using Playwright's `BrowserContext.grantPermissions(['fileSystem'])` and the underlying CDP to seed a directory handle.

Out of scope for P1: auto-sync, migration wizard, fellow.db.

### Phase 2 — Automatic debounced sync

- Worker enqueues a sync after every committed mutation to `relationships.db`.
- Debounce: 500 ms quiet period, 5 s max wait.
- Atomic write via `.tmp` + rename.
- Sync-failed state surfaces in status badge with "Retry now."
- Auto-backup rotation moves to the user's folder (Phase 1 leaves auto-backups in OPFS).

### Phase 3 — First-launch migration wizard

- Banner for OPFS-only users on first launch after P3 ships.
- One-click "Choose folder & save now" flow.
- Bulk export of current OPFS contents into the chosen folder (relationships.db + auto-backup ring).

### Phase 4 — Polish & accessibility (post-MVP)

- "Show in Finder" via `showDirectoryPicker` round-trip when supported.
- "Open data folder" deep link if any platform exposes it without re-picking.
- Diagnostic panel additions (folder path, last sync time, sync-failure count, current permission state).
- Maybe-eventual: `FileSystemObserver` watch on the folder so external edits surface as conflicts.

## Open questions for @richbodo

Each one needs your call before phase 1 code lands.

**Q1: Folder layout — single file or directory?**

Option A: drop `relationships.db` straight into the folder the user picks (alongside whatever's already there). Pros: matches "it's just a file" intuition. Cons: auto-backups (`relationships.db.bak.*`) and any future metadata clutter the user's folder.

Option B: require an empty folder, treat the folder as ours, manage all contents (`relationships.db`, backups, maybe a `.fellows-manifest.json`). Pros: clean ownership boundary. Cons: more friction on first setup; pickier about pre-existing folders.

Option C: drop a subfolder. User picks a parent folder; we make `EHF Fellows Data/` inside it and own that. Compromise; mirrors how VS Code creates `.vscode/`.

**Recommendation:** C — clearest user mental model, no destructive collisions, naming visible in Finder.

**Q2: What happens when the picked folder already contains a `relationships.db`?**

Scenarios: user re-installs and points at their old folder (✓ we want to load that), user picks a colleague's folder by accident (✗ we should not silently merge), user picks the SAME folder another browser is also using (✗ split-brain).

**Recommendation:** if the chosen folder contains `relationships.db`, show a confirm dialog: *"This folder already has fellows data — `<groups summary>`. Use it?* / Keep my browser's data and back this folder's data up first / Cancel". Don't silently merge.

**Q3: Mobile in the matrix — pretend unsupported, or partial Android support?**

Android Chrome 121+ does support `showDirectoryPicker`, but with worse permission persistence and *Clear Storage* still nuking handles. v1 plan calls it unsupported; the alternative is "partial — works but bigger 'unsafe in Android Settings' warnings."

**Recommendation:** v1 unsupported. Treat mobile as today's OPFS-only flow. Revisit when Android File System Access feels solid.

**Q4: Diagnostic surface — how much state to expose?**

The full permission lifecycle (handle present, last permission query result, last sync attempt + outcome, current path) is useful for support cases. Could land in the existing `?diag` panel.

**Recommendation:** yes, add a "Data folder" subsection to the `?diag` panel. Low cost; high payoff when someone files a "I lost my data" issue.

**Q5: Naming.**

Settings UI calls it: data folder? backup folder? sync folder? save folder? Worth picking one and using it everywhere.

**Recommendation:** "**Data folder**" — implies durability and ownership; doesn't mislead users into thinking it's a backup of something else.

## Testing approach

- **Unit:** IndexedDB handle round-trip; sync-out write logic against a stubbed `FileSystemDirectoryHandle`.
- **Playwright E2E (Chromium):** seed a folder handle via CDP, exercise full save / load / disconnect / reconnect flows. Verify status-badge state machine.
- **Manual smoke:**
  - Chrome desktop PWA: full happy path.
  - Chrome desktop PWA + revoke permission via Site Settings → permission-prompt path.
  - Chrome desktop PWA + user-moves-folder-out-from-under-us → "folder inaccessible" state.
  - Safari desktop: confirms unsupported-browser badge appears without spamming errors.
  - Firefox: same.
  - iOS Safari PWA: same.

## Risks

- **OPFS and folder drift permanently if sync keeps failing.** Mitigation: status badge surfaces the divergence loudly; auto-retry on next mutation; "Save now" button always available.
- **User picks a folder inside a synced location (Dropbox/iCloud) and runs the app in two browsers.** Mitigation: Q2's "already has data here?" dialog catches the first case; multi-writer is documented as unsupported in `users_manual.md`.
- **`Clear site data` still wipes the IDB-stored handle**, forcing re-pick. Mitigation: the FOLDER survives, so the user just re-picks and the data is unchanged. Document this in `users_manual.md` as the recovery path.
- **Browser auto-revokes file system permissions on idle eviction.** Chrome does this for tabs that have been backgrounded for a long time. Mitigation: the `'prompt'` state and reconnect CTA already cover this. Tested.

## Links

- File System Access API spec: <https://wicg.github.io/file-system-access/>
- VS Code for Web architecture talk (the reference design): <https://code.visualstudio.com/blogs/2021/10/20/vscode-dev>
- sqlite-wasm OPFS VFS docs: <https://sqlite.org/wasm/doc/trunk/persistence.md>
- Related plan: [`local_first_worker_architecture.md`](./local_first_worker_architecture.md)
