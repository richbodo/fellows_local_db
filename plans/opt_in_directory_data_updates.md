# Opt-in directory data updates

## Why

`fellows.db` is a frozen archive. EHF's old directory has been shut down,
the canonical Knack source is gone (`docs/data_provenance.md`), and the
PWA's job from here on is "let fellows keep using the snapshot they were
given." In that world, silently re-importing `fellows.db` mid-session is
the wrong default:

- A user's profile view, search results, or saved-group member list can
  change underneath them without any acknowledgement.
- Group members reference fellows by `record_id` with no FK across DBs;
  if a record disappears in a future snapshot, the corresponding
  `group_members` row stays in OPFS but the INNER JOIN against the new
  `fellows.db` silently drops the member from every UI surface. The user
  loses context with no way to know it happened.
- The app's stated stance ("install once, works forever";
  `email_gate.md` invariant 10) treats the local copy as authoritative.
  Auto-refresh quietly contradicted that.

PR #113 (Phase 3 of `local_first_worker_architecture.md`) shipped a
silent SHA-keyed refresh + a `'Directory updated'` toast. The
mechanism is correct; the policy was wrong for this product. This plan
reverses the policy without disturbing the mechanism.

App-shell updates (bug fixes, UI improvements) keep their existing
auto-detect + reload-banner flow. The two have always been
independently versioned in `/build-meta.json` (`git_sha` for the shell,
`fellows_db_sha` for the data); we just expose that independence to the
user.

## Goals

1. **Directory data updates are opt-in.** The worker never re-imports
   `fellows.db` on its own after the first install. The user has to ask.
2. **Update availability is discoverable.** The About page shows two
   independent status lines (App / Directory data) and a single
   ceremonial "Check for updates" button that refreshes both.
3. **Group integrity is protected at update time.** Before swapping
   `fellows.db`, the worker computes which `group_members.record_id`s
   would no longer resolve and surfaces them in a confirm dialog.
4. **Past silent updates don't leave hidden damage.** A one-time soft
   scan on first boot of the new code surfaces orphaned group members
   that earlier auto-refreshes may have already created.
5. **Cold-start still works.** A fresh install (post–Reset Everything,
   or first-time visitor) still fetches `fellows.db` automatically as
   part of boot. "Opt-in" applies to *re-imports*, not initial install.

## Non-goals

- **No schema change to `relationships.db`.** Denormalizing
  `name`/`slug` into `group_members` would make groups robust to any
  future record removal but is deferred — Knack is shut down, frozen
  data is the steady state, and the diff dialog + soft scan cover the
  realistic risk. Revisit if data churn ever happens.
- **No silent removal of orphaned `group_members` rows.** The soft scan
  surfaces them; the user decides what to do.
- **No new server endpoint.** `/build-meta.json:fellows_db_sha` is
  already the freshness signal we need.
- **No change to the SW shell update path.** The "New version
  available — Reload" banner stays. The two flows are intentionally
  distinct.
- **No image-cache versioning work.** Profile images live in
  `fellows-images-v1` and are fetched lazily; they tag along with shell
  updates. Out of scope here.

## Product behavior

### About page

A single button — **Check for updates** — runs both checks in
parallel and renders two independent status lines:

```
App
  app: 2026-05-06-b4403be — up to date
  [no action]

Directory data
  Snapshot from 2026-04-08 — up to date
  [no action]

[Check for updates]   Last check: 2026-05-06T12:34Z
```

When something is available:

```
App
  app: 2026-05-06-b4403be → 2026-05-15-c0ffee1
  App update available  [Reload to apply]

Directory data
  Snapshot from 2026-04-08 → 2026-05-15
  Directory Data update available  [Update directory data]

[Check for updates]   Last check: 2026-05-15T09:00Z
```

Status-line text constants (literal):

- `"App update available"` — when `git_sha` differs.
- `"Directory Data update available"` — when `fellows_db_sha` differs
  from the locally-recorded sidecar SHA.
- `"up to date"` — otherwise.
- `"Couldn't check (offline?)"` — when `/build-meta.json` is
  unreachable.

The existing single-line status (`#about-update-status`) is removed in
favor of the two-block layout. The "Last update check" line
(`#about-last-update`) becomes "Last check" — the timestamp the
About-page button last successfully reached the server.

### Update directory data — confirm dialog

Clicking **Update directory data** triggers a worker preview. If no
group would lose members, apply silently and replace the status line
with `"Directory data updated."` (no toast — the user just acted, the
status block is the acknowledgement).

If members would disappear, render a confirm dialog:

```
Update directory data?

This update removes 2 fellows from your saved groups:

  • Alice Smith — in 'NZ Mentors', 'Investors'
  • Bob Jones   — in 'NZ Mentors'

After the update they will no longer appear in those groups.
Their entries will be flagged as 'Profile no longer available' so
you can review and remove them.

[Cancel]   [Update anyway]
```

`Cancel` discards the staged bytes. `Update anyway` commits the swap
and writes the orphan list to a new `fellow_orphans` synthetic source
(see § Orphan surfacing below).

### Orphan surfacing

In group detail and edit views, a member row whose `record_id` is not
present in the current `fellows.db` renders as:

```
[?]   Profile no longer available  (record_id: rec_abc123)   [Remove]
```

Compact, non-blocking, never auto-removed. The user gets a one-click
"Remove" affordance per row. No bulk-remove — too easy to misclick.

This row is also what the soft scan (next section) surfaces.

### Soft scan for pre-existing orphans

On first boot of the new code, the page asks the worker to enumerate
`group_members` rows whose `record_id` is not present in the current
`fellows.db`. If any exist:

- Set a one-shot `relationships.settings.orphan_scan_done = "1"`.
- Show a single non-blocking toast on the boot the scan first runs:
  `"Some group members are no longer in the directory. See group details for review."`
- The orphan rows surface using the same UI pattern above.

If `orphan_scan_done` is already set, skip — the scan has run before.
This handles the case where users were on PR #113 and got auto-updates
that already created orphans.

## Implementation

### Worker (`app/static/vendor/sqlite-worker.js`)

**`ensureFellowsDb` policy split** — gate the existing
fetch-and-import on a new `mode` arg, defaulting to `install-only`:

| `mode`         | When called                            | Behavior |
|----------------|----------------------------------------|----------|
| `install-only` | Boot, every page load                  | If `hasFellowsDb`, no-op. Else fetch + import (cold-start). |
| `refresh`      | User-clicks "Update directory data"   | Current Phase 3 behavior: fetch, validate, import, swap, update sidecar. |

The `serverSha` arg stays — `install-only` ignores it (other than for
trace logs); `refresh` uses it as the expected target SHA.

The page's boot flow today does:

```js
provider._ensureFellowsDb({ serverSha });
```

It changes to:

```js
provider._ensureFellowsDb({ serverSha, mode: 'install-only' });
```

and the post-handler `'Directory updated'` toast disappears.

**New RPC: `compareFellowsDbSha({ serverSha }) → { hasFellowsDb, localSha, dataUpdateAvailable }`**

Cheap. Reads `fellows.db.meta.json` (already exposed via
`_getFellowsDbMeta`, factor out the read), compares to `serverSha`,
returns the comparison without touching the network. The page calls
this as part of "Check for updates."

**New RPC: `previewFellowsDbSwap({ serverSha }) → { affectedGroups, newSnapshotDate, stagingId }`**

1. Fetch `/fellows.db` and validate (same path `refresh` uses).
2. Write the bytes to a new temp SAH slot
   (`fellows.db.swap-staging`), parallel to the existing
   `relationships.db.restore-staging` pattern.
3. ATTACH the staging slot, the live `fellows.db`, and `relationships.db`.
4. Run:
   ```sql
   SELECT gm.fellow_record_id, COALESCE(f_old.name, '?') AS name,
          GROUP_CONCAT(g.name, '|') AS group_names
   FROM relationships.group_members gm
   JOIN relationships.groups g ON g.id = gm.group_id
   LEFT JOIN fellows_old.fellows f_old ON f_old.record_id = gm.fellow_record_id
   LEFT JOIN fellows_new.fellows f_new ON f_new.record_id = gm.fellow_record_id
   WHERE f_new.record_id IS NULL
   GROUP BY gm.fellow_record_id
   ORDER BY name;
   ```
5. Return the affected list + an opaque `stagingId`. Don't commit yet.

**New RPC: `applyFellowsDbSwap({ stagingId }) → { ok, newSha }`**

Atomic-rename the staging slot into place via the existing
`poolUtil.importDb('fellows.db', bytes)` path the current `refresh`
uses, update the meta sidecar. If `stagingId` doesn't match (user took
too long, or the page reloaded), 400 — the page retries the preview.

**New RPC: `findOrphanedGroupMembers() → { orphans: [{ recordId, groupIds }] }`**

Used by the soft scan and by the group-detail render path (so a stale
orphan row stays accurate after a "Remove" action elsewhere). Pure
read.

The existing `ensureFellowsDb` `serverSha` param and meta sidecar
shape stay. Bump the worker handshake doc comment to note the policy
change but **do not** bump `WORKER_RPC_VERSION` — request/response
shapes haven't changed for existing RPCs, only added new ones.

### Page (`app/static/app.js`)

**Boot path**

In `pickDataProvider()`:
- Drop the `'Directory updated'` toast at line 7884.
- Pass `mode: 'install-only'` to `_ensureFellowsDb`.
- After successful directory render, call `findOrphanedGroupMembers()`
  iff `relationships.settings.orphan_scan_done` is unset; show the
  one-shot toast if any are returned; set the marker either way.

**About page**

Replace the single-status block (`renderAboutPage` ~line 4798) with
the two-block layout from § Product behavior. New IDs:

- `#about-app-status` (App line)
- `#about-data-status` (Directory data line)
- `#about-update-data-btn` (rendered only when data update available)
- The existing `#about-check-updates` button stays — it now drives
  both checks.

The existing `checkForServerUpdate()` helper handles the app-shell
half. Add a parallel `checkForDataUpdate()` that calls
`compareFellowsDbSha` against the freshly-fetched
`/build-meta.json:fellows_db_sha`. The button click runs
`Promise.all([checkForServerUpdate(), checkForDataUpdate()])` and
populates both lines.

**Update flow**

`#about-update-data-btn` click:
1. Disable button, status → `"Checking impact…"`.
2. `previewFellowsDbSwap({ serverSha })`.
3. If `affectedGroups.length === 0`, call `applyFellowsDbSwap` directly
   with status updates.
4. Else render the confirm dialog (existing modal helper). Confirm →
   `applyFellowsDbSwap`; cancel → discard the staging bytes via a new
   `cancelFellowsDbSwap({ stagingId })` RPC and restore the previous
   status.
5. On apply success, reload the directory list in-place
   (`bootDirectoryAsApp`'s data-only refresh path) so users see the
   new data without a full page reload.

**Group rendering**

In group-detail render (`renderGroupDetail` and the visual directory),
detect rows where the worker returned no fellow data for the
`record_id` and substitute the orphan row:

```
[?]   Profile no longer available  (record_id: <id>)   [Remove]
```

`Remove` calls the existing group-edit RPC to drop that
`fellow_record_id` from the group's member set.

### Build / server

No changes. `/build-meta.json:fellows_db_sha` is already emitted by
both `build/build_pwa.py` and `app/server.py`.

### Settings

Add one new setting key in `relationships.settings`:

| Key | Value | Purpose |
|---|---|---|
| `orphan_scan_done` | `"1"` | Marker that the one-time post-PR-113 orphan scan ran. |

Set on first successful scan completion (regardless of whether orphans
were found). Cleared by Reset Everything along with the rest of OPFS.

### Tests

E2E (Playwright, `tests/e2e/`):

- **`test_directory_data_update_flow.py`** (new):
  - Two boots with the same SHA produce zero `/fellows.db` requests
    (regression on auto-refresh removal).
  - Boot with mismatched SHA also produces zero `/fellows.db`
    requests (proves opt-in).
  - Click "Check for updates" with a mismatched SHA → "Directory Data
    update available" appears.
  - Click "Update directory data" with no group impact → directory
    re-renders, toast-free, status flips to up-to-date.
  - Click with group impact → confirm dialog appears with the right
    members, Cancel discards, Update anyway commits.
- **`test_orphan_soft_scan.py`** (new):
  - Seed `relationships.db` with a `group_members` row pointing at a
    `record_id` not in `fellows.db`. Boot. Toast appears once.
    Reload. Toast does not reappear (`orphan_scan_done` is set).
    Group detail shows the orphan row with Remove affordance.
- **`test_versioned_fellows_db.py`** (existing, amend):
  - Update the assertions: a SHA mismatch no longer triggers a
    `/fellows.db` fetch on its own. Add a clicks-the-button case for
    the new flow.

Unit (worker-driven via `window.__dataProvider`):

- `compareFellowsDbSha` correctness across (no local DB / matching /
  mismatched / serverSha-null) cases.
- `previewFellowsDbSwap` returns the right affected members across
  (no groups / groups with no overlap / groups with overlap / groups
  with multiple overlaps in same group) cases.
- `applyFellowsDbSwap` rejects an invalid `stagingId`.
- `findOrphanedGroupMembers` returns expected rows for seeded fixtures.

## Migration

No schema migration. The change is policy-only on the worker side and
purely additive on the page side (new RPCs, new UI, removed toast +
removed auto-refresh policy).

What existing users see on the boot of the new code:

1. App shell update banner appears (new `git_sha`). They click Reload
   in their own time — nothing different about that flow.
2. After reload, no data refresh happens automatically. Their
   currently-installed snapshot stays.
3. If they had pre-existing orphans from PR #113 auto-refreshes, the
   one-time scan toast fires once and those rows are visible in their
   group details.
4. Next time they visit About and click "Check for updates", they see
   the two-line status. If a data update is available, they decide
   whether to apply it.

## Doc updates

Same PR:

- `docs/users_manual.md` — rewrite **Updates** and **About** sections.
  Describe the two-line status, the **Update directory data** button,
  and the orphan-row UI. Keep the existing app-update reload-banner
  paragraph; add a parallel paragraph for directory-data updates that
  emphasizes opt-in. New screenshot of the About status block when an
  update is available.
- `docs/Architecture.md § Persistence and upgrades` — change
  "**Re-imported** when `fellows.db.meta.json:sha` differs from
  `build-meta.json:fellows_db_sha`" to "**Re-imported on user request**
  when the SHAs differ; never automatically after the first install."
- `docs/persistence_and_upgrades.md` — same edit in the storage-layer
  table; add a row for `relationships.settings.orphan_scan_done`.
- `plans/local_first_worker_architecture.md` — append a short note at
  the top of Phase 3 (or in the "open questions" tail): "The silent
  SHA-keyed refresh shipped here was superseded by opt-in updates;
  see `plans/opt_in_directory_data_updates.md`. The fetch/import
  mechanism is unchanged; only the trigger moved from boot to a user
  click."
- `README.md § Design Stance` — minor edit. Current bullet 2 is
  "Server contact is bounded to two purposes only: (1) the magic-link
  gate that authorizes a download, and (2) fetching new bundle / DB
  bytes on update." Tighten "on update" to "when the user opts in to
  an update" so the README matches the new default.

## Rollout sequence

1. **Worker changes** (mode split, new RPCs, new staging slot).
   Self-contained; existing call sites still work because
   `install-only` is the default new behavior and old callers don't
   pass `mode`.
2. **Page changes** (drop toast, switch to `install-only`, About-page
   UI, confirm dialog, orphan row, soft scan).
3. **Doc updates** in the same PR. Per CLAUDE.md, UI/UX changes ship
   with the user-manual update.
4. **Tests** as above. The existing `test_versioned_fellows_db.py`
   needs amending so its assertions reflect the new policy — leaving
   it untouched would land green and miss the regression.

One PR, but I'd structure the diff as three logical commits (worker /
page+UI / docs+tests) so review is easy.

## Open follow-ups (not this plan)

- Denormalize `name` + `slug` into `group_members` (schema bump on
  `relationships.db`, 1 → 2). Makes groups fully durable against
  record removal even without a diff dialog. Defer until / unless
  data ever actually changes.
- "Restore previous directory snapshot" — symmetrical to the
  `relationships.db` restore feature. Cheap to add post-hoc since the
  worker already knows how to atomically swap `fellows.db` slots; would
  need a sidecar of recent snapshots in OPFS, similar to the
  `relationships.db.bak.<ISO>` rotation. Probably overbuild for a
  frozen-data app, but the door is open.
