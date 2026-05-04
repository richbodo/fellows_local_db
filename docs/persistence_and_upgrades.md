# Persistence and Upgrades

> **Doc-state note:** the storage table's "Owner" column, the `fellows.db.meta.json` row, the new auto-backup trigger semantics (per-boot debounced, 5-slot rotation), and the removal of the `last_seen_sha.txt` row reflect the target architecture as of Phase 1 of [`plans/local_first_worker_architecture.md`](../plans/local_first_worker_architecture.md). The runtime catches up when the cutover ships. Until then, `app/static/app.js` still drives auto-backup from the main thread on a build-SHA-change trigger and writes `last_seen_sha.txt`. Remove this banner when P1 lands.

The PWA stores user state across several layers, each with different
survival semantics. This doc captures what survives what — so future
features can land without surprising existing users, and so we have a
shared mental model when triaging "why did my X disappear?" reports.

## Storage layers

The "Owner" column names the JS context that reads and writes the
layer (per [Architecture.md § Worker-owned OPFS](Architecture.md#worker-owned-opfs)).
"server" means an HttpOnly cookie that no JS context can see.

| Layer | Owner | Holds | Replaced on app update | Cleared by **Clear App Cache** button |
|---|---|---|---|---|
| Cache API `fellows-app-shell-vN` | service worker | HTML, JS, CSS, SW, manifest, icons, sqlite3.wasm, `vendor/sqlite-worker.js` | Yes — every CACHE_VERSION bump | Yes |
| Cache API `fellows-images-v1` | service worker | Profile photos | No (separate cache name) — re-fetched as needed | Yes |
| IndexedDB `fellows-local-db` | main (retired in Phase 6) | Offline-fallback full fellow rows | Regenerated on every successful boot | Yes |
| OPFS `fellows.db` | worker | Imported Knack contact data | **Re-imported** when `fellows.db.meta.json:sha` differs from `build-meta.json:fellows_db_sha` (Phase 3); otherwise reused | **No** (gap; see "Open questions") |
| OPFS `fellows.db.meta.json` | worker | `{sha, fetched_at, last_failure_at, last_failure_reason}` — the freshness sidecar that gates re-import of `fellows.db`. Sibling of `fellows.db` at the OPFS root, outside the SAH-pool dir, so a `relationships.db` restore can't desync it. | Updated after each successful re-import; otherwise untouched | **No** |
| OPFS `relationships.db` | worker | Groups, group members, fellow_tags, fellow_notes, settings — all user-authored | **Never** — that's the whole point of this file | **No** |
| OPFS `relationships.db.bak.<ISO>` | worker | Snapshots of `relationships.db`, rotated to keep newest 5 | Auto-created on every boot when the most recent backup is more than 1 hour old (debounced); pruned to 5 newest | **No** (preserved alongside `relationships.db` for recovery) |
| localStorage `fellows_authenticated_once` | main | "this origin has authenticated at least once" marker | Untouched | **Preserved by name** in `clearAllAppData` |
| localStorage `ehf_has_email_only` | main | Has-email filter pref (mirrored to `relationships.settings.has_email_only` for durability across Clear App Cache) | Untouched | Cleared, but rehydrated from `relationships.settings` on next boot |
| localStorage `ehf.group_draft` | main | In-progress group composer state | Untouched | Cleared (acceptable: drafts are unsaved) |
| localStorage `fellows_self_email` | main | User's "me" email for `mailto:?to=…` | Untouched | Cleared, but rehydrated from `relationships.settings` on next boot |
| Cookie `fellows_session` (HttpOnly) | server | HMAC'd session, 7-day TTL, contains `token_issued_at` | Untouched (still valid until TTL) | Cleared via `POST /api/logout` (server sends a clearing `Set-Cookie`). `clearCookiesBestEffort()` also runs from JS as a fallback for any non-HttpOnly cookies. |

Note: `last_seen_sha.txt` (the build-SHA sentinel previously used to
gate auto-backup) is retired in the target architecture. The newest
`relationships.db.bak.<ISO>` filename's timestamp is the new
debounce input. The worker's `init` op cleans up any orphaned
sentinel file from older bundles on first boot of a P1+ build.

**Reset Everything** (kebab → bottom item / desktop link below the red
button) clears every row above *including* the two OPFS files and the
`fellows_authenticated_once` marker. Use only when Clear App Cache
hasn't fixed the problem; the user loses all saved groups, notes, and
settings. Implementation: same teardown as `clearAllAppData` plus an
OPFS-root iteration that `removeEntry`s every top-level entry. See
[A user clicks Reset Everything](#a-user-clicks-reset-everything).

The key architectural decision: **`relationships.db` is a separate
OPFS file from `fellows.db`** rather than a set of new tables inside
`fellows.db`. That's because `fellows.db` is bundled with the build
and re-imported on every boot, while OPFS files we don't explicitly
touch are durable. Cross-DB joins use SQLite `ATTACH DATABASE
'fellows.db' AS f ?mode=ro`, which also enforces read-only access to
contact data at the SQLite level (any stray write into `f.*` raises
`OperationalError`).

The OPFS path is used in **both** standalone PWA mode and browser-tab
mode. Production's `deploy/server.py` does not serve `/api/groups` or
`/api/settings`, so OPFS is the only place groups and settings can
live for prod visitors regardless of how they opened the app. Browsers
that can't run OPFS + `FileSystemSyncAccessHandle` (Safari < 16.4,
Chrome/Edge < 102, Firefox < 111, insecure contexts) see the
unsupported-browser panel for those features instead — the rest of
the app still works (directory, search, profiles). See
[`browser_support.md`](browser_support.md) for the full version
floors and triage policy.

## Standard app update flow

1. Operator runs `just ship`. Bundle goes out to the droplet.
2. Existing user opens the installed PWA (or visits in a browser tab).
3. SW polls `/build-meta.json` and notices the new build SHA.
4. SW fetches new `sw.js` (which has bumped `CACHE_VERSION`); install
   event runs and pre-caches the new shell.
5. `app.js` shows the "New version available — Reload" banner.
6. User clicks Reload. New SW activates. Old shell cache deleted.
   Controlled tabs auto-navigate (see `sw.js`'s activate handler).
7. Fresh `app.js` runs against fresh shell against fresh `fellows.db`.

What survives the reload, end-to-end:
- The session cookie (still valid until its 7-day TTL).
- `fellows_authenticated_once` (the URL-just-works marker).
- `relationships.db` (the user's groups, tags, notes, and settings).
- The image cache.
- All localStorage keys (drafts, filter prefs, etc.).

What gets replaced (intentionally):
- App shell HTML, JS, CSS, SW, manifest, and `vendor/sqlite-worker.js`
  (precached together; CACHE_VERSION-busted as one unit).
- `fellows.db` in OPFS, **only when** `build-meta.json:fellows_db_sha`
  differs from the locally-recorded `fellows.db.meta.json:sha` — the
  worker's `ensureFellowsDb` op runs an atomic staging-slot import on
  mismatch and updates the sidecar. Two consecutive boots against an
  unchanged server produce zero `/fellows.db` requests.
- IndexedDB cache (regenerated on next successful `getList`; retired
  in Phase 6 per [`plans/local_first_worker_architecture.md`](../plans/local_first_worker_architecture.md#phase-6--retire-indexeddb)).

## Auto-backup of `relationships.db`

`relationships.db` is the only local file that's neither replaced on
upgrade (like `fellows.db`) nor easy to recover from a botched
migration or OPFS glitch (since it's per-user, never synced). To make
"upgrade ate my groups" — and "I just deleted the wrong group" — a
recoverable scenario rather than a data-loss scenario, the worker's
`init` op auto-snapshots it before serving any app RPC.

Mechanism (worker-internal, in `vendor/sqlite-worker.js`'s `init`,
runs after `installOpfsSAHPoolVfs` returns and before
`new OpfsSAHPoolDb('relationships.db')`):

1. List the OPFS root for `relationships.db.bak.*` siblings.
2. If `relationships.db` doesn't exist in the SAH-pool's file map →
   first install, no source to back up; return.
3. If the most-recent `bak.<ISO>` file's timestamp is **less than 1
   hour old** → debounced; return without writing a new snapshot.
   This keeps debug-session reloads from thrashing the rotation.
4. Otherwise:
   - `bytes = poolUtil.exportFile('relationships.db')` — snapshot read.
   - Write to OPFS root file `relationships.db.bak.<ISO timestamp>`.
   - Rotate: list backup files, sort by name (ISO timestamps sort
     chronologically), `removeEntry` the oldest until ≤5 remain.
5. On any boot where `last_seen_sha.txt` exists from an older
   bundle, remove it (one-time cleanup) and never write it again.

The trigger is **per-boot debounced**, not per-deploy. A
build-SHA-change trigger is keyed to deploy cadence, but the
recovery use case ("undo something I just did") is keyed to
user-edit cadence; debouncing per boot is more sensitive to that
without thrashing the rotation when a user reloads three times in
five minutes. Files are tiny (tens of KB even for an active user),
so a 5-slot rotation is cheap.

Backups live at the OPFS **root**, not inside the SAH pool — so they
survive normal sqlite-wasm operations (which only touch the pool dir)
but get cleaned up by `clearEverything()`'s root-iteration removal
along with the rest of OPFS.

The Settings page exposes the live `relationships.db` as a download
("Your saved data" → "⬇ Download my user data") so the user can stash
a copy off-device. Diagnostics lists the backup files with sizes and
mtimes.

### Restore

Two restore paths surface on the Settings page (added in #85, on top
of the auto-backup machinery from PR #84):

- **Restore from a file.** File-picker accepts a `.db` / `.sqlite`
  download from any device. The bytes are read into a temp SAH-pool
  slot (`relationships.db.restore-staging`), validated with
  `PRAGMA quick_check` plus a schema check against the five expected
  tables (`groups`, `group_members`, `fellow_tags`, `fellow_notes`,
  `settings`), and the user gets a confirm dialog with a row-count
  delta before any live data changes.
- **Restore from a recent auto-backup.** Same panel lists the
  `relationships.db.bak.*` files already in OPFS root, each enriched
  with the row counts inside (read via the same staging slot — done
  sequentially because the slot is shared). Picking one rolls back
  to that snapshot.

Both paths funnel through `dataProvider.importRelationshipsBytes(bytes)`,
which:

1. Validates via `inspectRelationshipsBytes` (the same staging-slot
   trick as the backup picker).
2. Calls `snapshotRelationshipsDbToBackup` — a forced version of
   `maybeBackupRelationshipsDb` that skips the SHA-change check.
   The pre-restore state lands in the same rotation slot, so a wrong
   restore is one click away from undo.
3. Closes the live `relDb` handle, calls `poolUtil.importDb('relationships.db', bytes)`
   to atomically replace the SAH-pool slot, opens a fresh handle, and
   reassigns the closure-captured `relDb` so every other provider
   method (`listGroups`, `getSetting`, etc.) sees the new DB without
   a page reload.
4. Re-runs `bootstrapRelationshipsSchema(relDb)` (idempotent CREATE
   IF NOT EXISTS) so a backup from an older schema gets the missing
   tables added.

The `last_seen_sha.txt` sentinel is intentionally NOT touched by
restore — restoring an old backup is not a deploy event, so the
next genuine SHA-change boot will still trigger an auto-backup.

What this does NOT cover (out of scope, no plan to add):
- Cross-device sync.
- Encrypted backups (use external tooling).
- Merging / diffing two DBs — restore is a full replacement.
- Server-side storage of the backup file.

## Per-user customization (or lack thereof)

The deployed bundle is identical for everyone. There is no per-user
packaging — the build does not generate a custom artifact per
recipient.

What looks "custom per user" is purely client-side state:

- The user's email is captured into `localStorage[fellows_self_email]`
  the first time they submit the magic-link gate.
- It is also written to the `relationships.settings` table so it
  survives Clear App Cache. On boot, `app.js` mirrors the settings
  value back into localStorage for fast read.
- The Settings page (`#/settings`) lets the user override — useful
  when someone wants exports addressed to a different mailbox than
  the one they sign in with.

A user moving between browsers / devices re-enters their email at
sign-in (the magic-link form already requires it). After verify, the
gate handler stashes it client-side. No server-side per-user state
beyond what the magic-link allowlist already requires.

## Edge cases

### A user has no `self_email` set yet

A fresh install (or a returning user from before the Settings page
shipped) opens the app with no `self_email` in
`relationships.settings`. The group-detail Export panel surfaces a
one-line nudge ("Set your email in Settings to enable 'email it to
me'"). No data loss; just a one-time setup step. After the user
signs in via the magic-link gate the value is auto-captured, so
most users hit this only once or never.

### A user clicks Clear App Cache

- localStorage clears (except `fellows_authenticated_once`).
- IndexedDB clears.
- All Cache API entries clear (shell + images).
- The HttpOnly session cookie clears via `POST /api/logout` (server sends
  a clearing `Set-Cookie`); JS-visible cookies clear via best-effort
  `document.cookie` overwrites.
- Service worker registrations are unregistered.
- **OPFS does not clear**, so `relationships.db` — and `fellows.db` —
  both survive.
- After reload: user re-prompted for a magic link (cookie gone), then
  comes back into the directory with their groups intact. Their
  `self_email` (PR 5) re-mirrors from `relationships.settings` on
  boot, so the Settings page already shows it.
- The in-progress group draft (`ehf.group_draft`) IS lost — drafts
  are by definition unsaved.

### A user clicks Reset Everything

The escalation past Clear App Cache. Same surface as Clear App Cache
(kebab on mobile, small muted link below the red button on desktop)
but explicitly destructive — the confirm dialog spells out what gets
lost.

- localStorage clears (including `fellows_authenticated_once`, unlike
  Clear App Cache).
- IndexedDB clears.
- All Cache API entries clear (shell + images).
- The HttpOnly session cookie clears via `POST /api/logout`.
- Service worker registrations are unregistered.
- **OPFS clears**: every top-level entry (`relationships.db`,
  `fellows.db`, and any `relationships.db.bak.*` siblings once
  auto-backup ships) is deleted via `removeEntry`. There is no
  per-origin "wipe OPFS" API, so the implementation iterates the root
  with `await for entry of root.values()` and removes each by name.
- After reload: user lands at the email gate as a first-time visitor.
  Their groups, notes, settings, and fellow tags are gone.

When to recommend this over Clear App Cache: only after Clear App
Cache hasn't helped. Common triggers — a corrupt OPFS-stored
`fellows.db` that re-import didn't fix, a `relationships.db` schema
that survived a botched migration, or the unsupported-browser panel
appearing on a browser you know is supported (suggesting a
locally-broken OPFS state rather than a real browser limit).

### A user installs on a brand-new device

OPFS is empty, so `relationships.db` is created fresh. Their groups
from the old device are NOT here — there is no cross-device sync.
This is consistent with the project's "local-only PWA, no SaaS
backend" stance. If sync becomes a requirement later, the relevant
data is already isolated in `relationships.db` (separate from
contact data, identifiable as user-authored), which makes
export/import a tractable feature.

### Browser-tab visit by an existing user

`fellows_authenticated_once` is preserved across upgrades, so
`shouldActAsApp()` returns true on browser-tab visits and the user
boots directly into the directory — no install-landing detour. The
"endless install loop" some devs see on `localhost` does **not**
affect production users; it's gated on
`authStatus.authEnabled === false`, which is a dev-only signal
(prod always returns true).

### A user with a stuck PWA on a stale shell

The "New version available — Reload" banner is the canonical recovery
path. If they ignore it, they keep running the old shell — fine.
If they hit a bug that's already fixed in `main`, route them to
either:
1. Click the in-app **Reload** banner.
2. Click **Clear App Cache & Reload** (red button, bottom right).
   Their groups, settings, and auth marker survive; only the shell
   is replaced.

## Open questions / future work

- **OPFS reset.** Clear App Cache does not touch OPFS. If a user ever
  ends up with a corrupt OPFS-stored `fellows.db`, there's no UI path
  to wipe just that file. If this surfaces, add a separate "wipe local
  data and re-download" hook that deletes `fellows.db` from OPFS but
  leaves `relationships.db` intact. (Note: the equivalent gap for
  `relationships.db` is now covered — see § Restore above.)
- **Future cross-device sync.** Out of scope today, but the layering
  here keeps the door open: `relationships.db` is a single
  self-contained file with stable schemas, suitable for an
  export/import flow or an opt-in sync against a future backend.
