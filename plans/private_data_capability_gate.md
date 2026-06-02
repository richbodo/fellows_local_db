# Plan — Private-Data Capability Gate (folder-required private store; browse-only everywhere else)

**Status:** PLAN ONLY. Not started. **Decided:** 2026-06-02.
**Supersedes** the phone-only framing of [`mobile_redesign/PLAN_mobile_no_groups.md`](mobile_redesign/PLAN_mobile_no_groups.md) — that plan's *feature* reduction is folded in here as the phone realization of **browse-only mode**; its *layout* work (scroll container, hamburger, CTAs, mobile Settings) survives unchanged as the `is-phone` shell.
**Motivated by** [`../docs/architectural_findings.md` § 2026-06-01](../docs/architectural_findings.md) and staged for upstream as [`pna_toolkit_constraints_contribution.md`](pna_toolkit_constraints_contribution.md).

---

## 1. The decision in one paragraph

A PWA cannot reliably preserve a user's private data on browsers without the File System Access API (Safari, Firefox, all of iOS) or on any browser where no durable real file backs the store. That is a **data-loss ceiling** (`CST-PWA-PRIVATE-SNAPSHOT` / `CST-PWA-STORAGE-EVICTABLE`), not a fellows wart. Rather than ship a "sketchy but full-featured" app that silently risks losing groups, fellows gates **all private data — groups, group members, fellow tags, fellow notes, and the group-related settings — behind a verified, attached folder** (a real file on disk we have proven we can write and read back). Until that folder exists, every install runs in **shared-data-only mode**: browse the directory, search, open a fellow, email or call them. Nothing private. The unlock can happen at any time on a Chromium desktop browser; off Chromium (and on every phone) there is no in-app unlock, and the documented migration path is *back up your `.db` → install on Chrome → restore into a new folder*. This makes fellows a **compliant, useful PNA** on every platform — just a smaller one where the platform can't keep the durability promise — instead of an over-reaching one. The architectural fix (a real durable cross-platform private store) is a future-version concern; for now we soldier ahead honestly.

---

## 2. The two orthogonal gates (the load-bearing idea)

Two independent questions, each with its own signal. **Conflating them is the trap** the prior mobile-only framing fell into.

| Gate | Question | Signal | Reliable? | Cost if wrong |
|---|---|---|---|---|
| **Feature gate** — `privateDataEnabled()` → `body.no-private-data` | Is there a **verified, attached, permission-granted folder** backing a durable real file? | feature-detect (FSA) + empirical probe + live permission | **Yes** | — (all data-loss consequences ride here) |
| **Layout gate** — `isMobileDevice()` → `body.is-phone` | Is this a **phone** (mobile shell)? | UA (`app.js:1226`) | Fuzzy | **Cosmetic only** — a cramped/hidden UI, never data loss |

The principle: **every data-loss / sovereignty consequence rides on a reliable feature-detect; only the cosmetic shell choice rides on the fuzzy UA signal.** A phone misread as desktop is harmless. The one error to avoid — a real desktop misread as a phone — is contained by keeping `isMobileDevice()` conservative (true phones only).

### The three real cells

| Cell | Resolves to | Private-data UX | Shell |
|---|---|---|---|
| Chromium desktop **with verified folder** | `privateDataEnabled() === true` | **Full**: groups/notes/tags/composer/private settings/MCP | desktop |
| Chromium desktop **without a folder** · Safari desktop · Firefox desktop | `no-private-data && !is-phone` | **Grayed-out** with an **"Enable on Chrome desktop →"** unlock affordance | desktop |
| All phones (Android + iOS) | `no-private-data && is-phone` | **Hidden** (group chrome deleted, screen reclaimed — the mobile plan) | mobile |

> "Hidden on phones, grayed-out-with-CTA on non-Chromium/no-folder desktop." On a phone there is no action the user can take to unlock on that device, so a grayed-out control is noise — delete it and reclaim the screen. On desktop there *is* a path (install/switch to Chrome, pick a folder), so a discoverable affordance belongs there.

`folderStorageOffered()` (`app.js:8660` = `browserSupportsFolderPicker() && !isMobileDevice()`) already draws the FSA-capable-desktop boundary — but it answers "should we *offer* folder mode?", not "is a folder *attached and verified*?". The feature gate is the stricter, attached-and-verified condition (§ 5).

---

## 3. Shared-data-only mode — `relationships.db` stays dormant

In shared mode the app **never relies on `relationships.db` for durable data**. Its two trivial prefs live in `localStorage` only:

- `fellows_self_email` — the user's "me" email for `mailto:?to=…`. Optional and editable (some users want a separate "fellows" address). Recoverable: auto-captured at the magic-link gate; on a phone it's filled from the launching device anyway.
- `ehf_has_email_only` — the has-email filter pref.

Nothing we care about ever lands in evictable OPFS. This is a stronger handling than "mitigate eviction" — we **avoid** `CST-PWA-STORAGE-EVICTABLE` for private data entirely.

**One read-only exception (legacy rescue):** on boot, a Chromium-desktop-no-folder user's OPFS `relationships.db` is *peeked* (counts only) to detect pre-existing groups and drive the migration prompt (§ 6). That's a read to rescue legacy data, not a durable write — the "no durable data off-folder" guarantee holds.

---

## 4. Ground truth (verified file:line anchors)

Gates / detection:
- `isMobileDevice()` — `app.js:1226` (UA). `detectBrowserSupport()` — `app.js:1232` (UA → name/version, for messaging).
- `folderStorageOffered()` — `app.js:8660`; `browserSupportsFolderPicker()` nearby.
- `navigator.storage.persist()` best-effort once/install — `app.js:4171`.

Folder controller (`app/static/vendor/sqlite-worker.js`):
- `FOLDER_SUBFOLDER_DEFAULT = 'Fellows'` — `1770`; folder lives at `<parent>/Fellows/relationships.db`.
- `_findOrCreateSubfolder(parent, mode)` — `1914`: `open-existing` / `create-new` (numbered `Fellows`, `Fellows 2`, …) / `auto` (probes default; on hit returns `requiresChoice` with **counts, size, lastModified** + suggested next name) — `1949-1969`.
- `queryPermission` wrapper — `2028`, `2444`; `requestPermission` (user-gesture) — `2501`.
- Handle persisted in IndexedDB `fellows-fs-handles` (key `relationships-folder`); hydrate at `1872-1906`.
- Backup ring `relationships.db.bak.<ISO>` (5-slot) — folder- or OPFS-resident per mode.

Folder UI / reconnect (`app/static/app.js`):
- `getFolderHandleForReconnect` — `4070`; `reconnect()` — `8774-8808`.
- Settings folder section glue `wireFolderSection()` — `9895`; collision dialog `settings-folder-collision-dialog` — `9901`; `badge()` states — `8719`, `BADGE_COPY` — `9908`.
- Manual backup download filename `relationships-<ts>.db` — `app.js:2429`.

Surfaces to gate (all desktop-shared — gate via body class, don't delete):
- `renderDirectoryList()` `5779` (per-row `.dir-mark` select); `groupDraft` `70`; `renderRail()` (composer) `6258`; `#bulk-select-bar`/`updateBulkBar()` `6324`; `enterEditMode()` `6449`.
- `renderDetail()` `5888` (contact rows `5951`/`5960`; add-to-group `5906-5915`).
- `renderSettingsPage()` `8975` (email `8984`, folder `8997`, download `9018`, restore `9037`, MCPB `9061`).
- `route()` `7171` (group/edit routes to redirect/lock when `no-private-data`).
- `RELATIONSHIPS_SCHEMA_SQL` mirror in `app.js` (the `settings` table that will hold the in-db identity stamp, § 7).

Tests: `tests/e2e/mobile/` (Pixel 5 / iPhone 13 / narrow-360); `test_user_folder_storage.py` (folder write/lock/migration); `test_unsupported_browser.py`; `test_settings.py` (restore). Recipes `just test-mobile`, `just serve-lan`, `just serve-prod`.

---

## 5. The unlock flow (Chromium desktop) + the empirical probe

Entry points to unlock: tapping a grayed-out private surface (e.g. **Create group**) or Settings → folder picker. Flow:

1. **Warning.** "Saved groups live in a folder on your computer and need a Chromium desktop browser (Chrome, Edge, Brave, Arc). Pick a folder to enable them." (On non-Chromium/phone this control is grayed/hidden and routes to the help page instead — no picker.)
2. **Pick** a parent folder (`showDirectoryPicker({ mode:'readwrite', id:'fellows-data-folder' })` — `id` makes Chromium reopen the last-used location). Resolve the subfolder via `_findOrCreateSubfolder` (§ 7 biases this toward **adopt**).
3. **Probe — the gate.** Unlock only if **every** stage passes; each failure carries a stable `reason` code mapped to an anchor on the GitHub troubleshooting page (§ 8):
   - `picker_cancelled` — no handle returned.
   - `subfolder_create_failed` — `getDirectoryHandle({create:true})` threw → *"couldn't create the data folder — permissions?"*
   - `write_failed` — sentinel write threw → *"couldn't write — read-only folder, denied permission, or disk full?"*
   - `readback_mismatch` — wrote sentinel, read back ≠ what we wrote → *"the folder didn't return what we wrote — this looks like a cloud-only (OneDrive/Dropbox online-only) or virtual folder; pick a real local folder."* **This stage is what proves the location is genuinely durable**, per M1 (capability presence ≠ usefulness).
   - `permission_not_persisted` — handle won't persist / re-query `granted` fails → *"the browser won't remember this folder."*
4. **Migrate** any existing OPFS `relationships.db` with data into the chosen folder (§ 6), then **unlock**: `privateDataEnabled()` flips true, group surfaces light up, `relationships.db` becomes live in the folder.

Probe failure → stay in shared mode, show the reasoned message + help link, never half-unlock.

---

## 6. Migration

**Same-browser (existing Chrome user with OPFS groups) — automatic, ships with the foundation.** On boot, if `no-private-data` resolves but the legacy OPFS `relationships.db` holds real rows (the read-only peek, § 3), show **"You have saved groups — pick a folder to keep using them."** On folder pick + probe pass, copy the OPFS `relationships.db` into `<folder>/Fellows/relationships.db` (reuse the worker's existing folder-write path), stamp identity (§ 7), and unlock. Non-destructive: the OPFS copy is left intact until the folder write is verified. **This must land with the gate** — otherwise existing Chrome users lose sight of their groups the moment the gate ships.

**Cross-browser / cross-device (Safari-with-groups → Chrome) — manual, deferred.** ~1–2 real users. The path is the shipped backup/restore machinery: **back up `.db` to Desktop → install on Chrome → restore into a new folder.** Handled with a personal email + video walk-through rather than auto-migration code. The self-describing export name (§ 7) and the restore preview's row-count delta make the right file recognizable.

---

## 7. Reconnect & disambiguation (the cork) — design

**Most reconnects need zero file-finding.** When permission lapses on restart, the handle is still in IndexedDB; a one-gesture `requestPermission` re-grants the *exact same folder*. In the gated world this becomes a **"Reconnect your folder to use groups"** prompt: features re-lock on a lapse, the re-grant re-unlocks, and **the data is never hidden or destroyed** (the file still exists). Only when the stored handle is *gone* (cleared site data / new install / new device) does a re-pick happen — and that's the only place the "which `relationships.db`?" confusion can arise. Fixes:

1. **Content-previewed chooser (generalize the existing collision dialog).** On re-pick, scan **all** `Fellows*` subfolders in the chosen parent (not just the default — today's `auto` mode only previews `Fellows`, so data in `Fellows 2` is invisible). Present each candidate as *groups N · members N · notes N · last changed `<date>` · created on `<device>`*. Recommend the newest; the user picks **by content, never by filename**. Because the user always picks a **folder, not a file**, the `.db`/`.bak.*` siblings inside are never something they choose among.
2. **In-db identity stamp** (survives backup/restore as a unit — read for free when we count rows). Add to the `settings` table: `workspace_uuid`, `device_label`, `created_at`, `last_written_at`, `write_generation` (monotonic). `write_generation`/`last_written_at` give a canonical "most recent" winner; `device_label` makes "created on this Chrome" legible. In-db (not a sidecar) so it can't desync.
3. **Bias to adopt.** A folder is now mandatory, so a *second* store is almost never intended — it is the source of the mess. Make **"Use the existing data here"** the default action in the collision/chooser dialog; demote create-new to an escape hatch. Stops most proliferation at the source.
4. **Self-describing exports.** Rename the manual backup from `relationships-<ts>.db` to `ehf-fellows-private-data-<YYYY-MM-DD>.db`. Combined with the restore preview's row-count delta, the restore-a-file pile becomes recognizable.
5. **Folder marker.** Drop a human-readable `HOW-TO-MOVE-THIS-DATA.txt` in the data folder ("this folder is your EHF private data; to move computers, copy the whole folder / the `.db` file; the app reads/writes `relationships.db`"). Makes Finder/Explorer navigation and the manual migration self-explanatory.

**Out of scope:** two computers with genuinely divergent data (a merge). Restore stays full-replace (consistent with today); the chooser shows both summaries and the user decides, flagged as replace-not-merge.

---

## 8. Implementation sequence (each PR independently shippable + revertible)

Ship in order; keep `just test-fast` + `just test-mobile-functional` green at each step.

### PR 1 — Feature-gate foundation (keystone)
- `privateDataEnabled()` resolver (verified-folder-attached + permission `granted`); `body.no-private-data` toggled from it; keep `body.is-phone` purely for layout. Expose `window.__privateDataTier` + a `?diag=1` line (mirrors `window.__dataProvider`).
- Shared mode = `localStorage`-only; do not open `relationships.db` for durable data when locked (legacy read-only peek allowed, § 3).
- **No visible feature change yet** beyond diagnostics — this PR just establishes the gate and the body classes.

### PR 2 — Same-browser migration prompt (must ship with/just after the gate)
- Boot detection of legacy OPFS groups → "pick a folder to keep using them" → folder pick + probe + copy OPFS→folder + identity stamp + unlock (§ 6, § 5, § 7.2). Protects existing Chrome users before the gate bites.

### PR 3 — Browse-only feature reduction (serves Safari/FF desktop AND phones)
- Gate every group/selection/composer/notes/private-settings surface on `body.no-private-data`. **Phones (`is-phone`): hidden** (delete chrome, reclaim screen — the mobile plan's PR3). **Desktop (`no-private-data && !is-phone`): grayed-out with "Enable on Chrome desktop →"** CTA. Redirect/lock `#/groups*` and `#/edit/*` when `no-private-data` (redirect on phone; route to unlock/help on desktop).

### PR 4 — Unlock flow + empirical probe + troubleshooting page
- The full Create-group → warning → pick → staged probe → unlock flow (§ 5). Add `docs/` or a GitHub-repo troubleshooting page keyed by `reason` code; wire each failure message to its anchor.

### PR 5 — Reconnect & disambiguation hardening
- "Reconnect your folder" re-grant prompt (handle-present); features re-lock on lapse without hiding data. Content-previewed chooser scanning all `Fellows*` (handle-gone); bias-to-adopt. In-db identity stamp. Self-describing export filename + `HOW-TO-MOVE-THIS-DATA.txt` (§ 7).

### PR 6 — Mobile shell (the mobile plan's layout PRs, `is-phone`-gated)
- Scroll container (mobile plan PR1), hamburger drawer (PR2), Email/Call CTAs on fellow detail (PR4), reduced mobile Settings (PR5). These are pure layout and stay gated on `is-phone` — they compose on top of the browse-only reduction from PR3.

### PR 7 — Docs, tests, baselines, memory
- `docs/users_manual.md` (folder-required groups, browse-only mode, mobile flow, unlock + reconnect + migration), `docs/feature_platform_matrix.md` ("private data = verified folder only"), `docs/browser_support.md` (the gate, not just folder-mode-as-additive), `docs/Architecture.md` **Constraint attestation** (§ 9), `docs/persistence_and_upgrades.md` (shared-mode = localStorage-only).
- Rewrite `tests/e2e/mobile/test_mobile_interactions.py` per the mobile plan; new e2e for the gate (locked → unlock → migrate → reconnect), the probe failure paths (mock `readback_mismatch`), and the chooser. Re-promote mobile snapshot baselines.
- Pre-install/gate guidance (a *recommendation*, not a blocklist, per `browser_support.md`): "for saved groups you control as a real file, use a Chromium desktop browser; on Safari/Firefox/phones it's browse-and-contact."
- Update memory: supersede `mobile_folder_storage_policy` and the `project_mobile_no_groups` framing with this gate; add a project memory for the capability gate.

> Batching: PRs 1–2 land together (gate + migration are a unit). PRs 3–5 are the substantive new UX/flows. PR 6 is the mobile polish. PR 7 lands with whichever PR first changes user-visible behavior, per CLAUDE.md (docs ship with the feature).

---

## 9. Upstream impact (we implement first, then sharpen the contribution)

Building this before filing [`pna_toolkit_constraints_contribution.md`](pna_toolkit_constraints_contribution.md) sharpens four spec fields with evidence:

- **`CST-PWA-PRIVATE-SNAPSHOT` — handling.** Becomes "the private store *requires* a verified real file; absent one, there is **no** private store" — and the timestamped `.db` export is the honest **portability bridge**. Stronger than the speculative encrypted-email candidate. Frontier stays **Open** (the real fix is an architecture change), declared truthfully.
- **`CST-PWA-PRIVATE-SNAPSHOT` — Detectability.** Currently `feature-detect`. The empirical probe (`readback_mismatch` catching cloud-placeholder/virtual folders) proves that FSA presence is necessary but **not sufficient** for a *durable, useful* store — so the durable-folder question is really `feature-detect` **+ `empirical-probe`**. A concrete correction to the registry.
- **`CST-PWA-STORAGE-EVICTABLE` — frontier.** We **avoid** it for private data (nothing durable in evictable OPFS) rather than merely `Mitigated`. Document the avoidance pattern.
- **`CST-PWA-NO-SYNC` — "which copy is canonical?"** The in-db workspace identity (`workspace_uuid` + `write_generation`) is a concrete answer the registry can cite.

The **Constraint attestation** table (§ 3f of the contribution plan) gets a `docs/Architecture.md` section mirroring the existing *Exception attestation*, with this gate as the realization — no false durability anywhere, which is exactly the "over-reach = silent conformance failure" backstop the contribution defines, now demonstrably satisfied by fellows itself.

---

## 10. Out of scope / unchanged
- The worker, two-DB architecture, auth/magic-link gate, SW, data-provider tiers — untouched (this is UI-gating + a folder-unlock flow on top of shipped folder machinery).
- Desktop Chromium **with** a folder: full app, unchanged.
- Cross-device sync; DB merge; encrypted backups; server-side storage of private data — all still out, consistent with `persistence_and_upgrades.md`.
- The architectural fix (a real durable cross-platform private store) — a future-version concern, not this plan.

## 11. Open questions (decide with the build in hand)
1. Exact `device_label` source (UA-derived string vs user-set nickname). Default: UA-derived, editable later.
2. Whether the grayed-out desktop CTA also appears inside an empty `#/groups` route or only on the directory/compose affordances. Default: both, routed to the unlock/help flow.
3. Whether to write the `HOW-TO-MOVE-THIS-DATA.txt` marker once at unlock or refresh it on schema changes. Default: write once; rewrite only if the copy changes.
4. Phone copy for "groups live on desktop" — a one-liner in mobile Settings/About, or nothing at all. Default: a single quiet line in mobile Settings.
