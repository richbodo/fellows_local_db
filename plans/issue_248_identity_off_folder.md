# Plan — #248: gate workspace-identity minting so off-folder settings are literally empty

**Status:** OPEN. **Tracks:** [#248](https://github.com/richbodo/fellows_local_db/issues/248).
**Invariant (the tripwire):** `tests/e2e/test_private_data_enforcement.py::test_off_folder_settings_are_empty`
— a `@pytest.mark.xfail(strict=True)` that flips to XPASS the day this lands.

## 1. The residual in one paragraph

`plans/private_data_enforcement.md` (PRs A/B/C, shipped in #244/#243) made the
**load-bearing** guarantee true: off-folder, no durable private *user* data
(groups, prefs) is written — mutating `relationships.db` RPCs are refused at the
worker, and the boot reconciles no longer `setSetting` in browse-only. But it
deliberately scoped out one thing: the worker still mints **benign
workspace-identity metadata** into the OPFS `settings` table even off-folder, so
`getSettings()` is not *literally* `{}`. `_ensureWorkspaceIdentity(db)`
(`app/static/vendor/sqlite-worker.js:291`) is called unconditionally from
`bootstrapRelationshipsSchema(db)` (`:261`) on every relDb open, inserting
`workspace_uuid`, `device_label`, `created_at`, `write_generation`,
`last_written_at`. The enforcement tests work around this by *subtracting*
`_IDENTITY_KEYS` before asserting emptiness; `test_off_folder_settings_are_empty`
is the strict version that does **not** subtract, and it xfails. This is the
last gap between "no durable user data off-folder" (true) and
`CST-PWA-STORAGE-EVICTABLE`'s strongest reading ("browse-only is
localStorage-only", literally nothing durable in OPFS).

## 2. Why it wasn't already done — the real tension

The identity stamp is **not noise**; it is load-bearing for a *different*
constraint. `CST-PWA-NO-SYNC` uses `workspace_uuid` + monotonic
`write_generation` + `device_label` (the rows minted here) so the
content-previewed folder chooser can answer "which copy is canonical?" — see the
store-ranking read at `sqlite-worker.js:~2543-2588` ("highest `write_generation`,
then file mtime"). A first attempt to gate the mint on folder-mode **collided
with the folder-chooser identity/pivot flow** (`tests/e2e/test_folder_probe.py`)
and was reverted to a strict-xfail (see the `NOTE` at `sqlite-worker.js:292`).

The resolution rests on one observation: **identity only means something for a
canonical store.** Off-folder (browse-only) there is *no* canonical store to
disambiguate — so the stamp serves no purpose there, and not writing it is both
correct and what the invariant wants. Identity must still be minted onto a
**folder** store (and travel with its backups) so the chooser keeps working.

## 3. The fix

**A. Gate the mint (worker, load-bearing).**
- `_ensureWorkspaceIdentity` must only write when the relDb being bootstrapped
  is (or is becoming) the **canonical** store — i.e. the worker holds a
  permission-`granted` folder handle for it. Reuse the *same* folder-state
  signal PR A's durable-write guard uses (folder permission `granted`; see
  `:467`, `:789/810`, `:2164/2492`), so identity-minting and mutation-persistence
  share one definition of "off-folder."
- Off-folder: skip the mint entirely. Nothing durable lands in OPFS settings.
- The challenge to resolve head-on: **mode must be known at bootstrap time.**
  `bootstrapRelationshipsSchema` runs at init (and post-restore) and currently
  mints before folder resolution is necessarily complete (the chicken-and-egg
  behind the original collision). Two acceptable shapes — pick one in
  implementation:
  - **(i) Defer:** don't mint in `bootstrapRelationshipsSchema`; mint lazily at
    the *pivot to folder mode* and on the *first committed folder write* (where
    `_stampWriteGeneration` already runs — `:319`). Folder bytes hydrated from an
    existing store already carry identity, so only fresh-folder and
    OPFS→folder-pivot need the explicit mint.
  - **(ii) Condition:** keep the call site but pass the resolved folder-state in,
    and early-return when not canonical.
  (i) is cleaner — it ties identity to a durable write, which is exactly when it
  matters.

**B. Keep the chooser/pivot flow correct.**
- Minting onto a **folder** store at pivot/first-write is preserved, so folder
  users + their backups keep `workspace_uuid`/`write_generation`/`device_label`.
- The folder-probe ranking already tolerates absent identity (`id.device_label
  || null`, `writeGeneration ... != null ? ... : null` at `:2579-2580`) — confirm
  a candidate OPFS store with **no** identity ranks/handles gracefully (it should
  sort below any stamped folder store, which is correct: an unstamped browse-only
  OPFS slot is not a canonical copy).
- Off-folder, `_stampWriteGeneration` never fires anyway (mutations are refused
  by PR A), so no stray identity appears via the write path.

**C. Promote the tripwire + drop the workaround.**
- Remove the strict-xfail marker on
  `tests/e2e/test_private_data_enforcement.py::test_off_folder_settings_are_empty`
  — it becomes a hard guard.
- The other enforcement tests can drop the `_IDENTITY_KEYS` subtraction (off-folder
  there are now *no* identity keys, so `_user_keys` == all keys == ∅). Keep
  `_IDENTITY_KEYS` only if a folder-mode test still needs to ignore them.
- Close #248 **only** when the test XPASSes (then the marker is gone, so "close
  on green" is automatic, not manual — which is what burned us when #248 was
  closed by hand while the xfail was live).

## 4. Tests + folder QA (the pass the first attempt skipped)

**Automated:**
- `test_off_folder_settings_are_empty` (now a guard): browse-only boot →
  `getSettings()` is `{}`.
- `tests/e2e/test_folder_probe.py` — **must stay green.** It's the flow the first
  attempt broke; it's the gate on this change.
- `tests/e2e/test_user_folder_storage.py` (reconnect/chooser/identity stamp) —
  green: a folder store still carries identity; the chooser still ranks by
  `write_generation`.
- Add: after OPFS→folder **pivot**, the new folder store has a `workspace_uuid`
  (identity minted on becoming canonical).

**Manual folder QA (maintainer — put in the PR description):**
- Desktop Chromium: fresh folder attach → identity present in folder file;
  browse-only boot → OPFS settings empty.
- Reconnect / re-pick with two candidate stores → chooser preview + "most recent"
  recommendation still correct.
- OPFS→folder pivot (unlock) → identity minted onto the folder store; prior
  browse-only OPFS slot had none.
- Backup ring in folder mode still carries identity.

## 5. Out of scope
- The durable-write guard + pref routing (done, #244). Folder mode's full
  behavior (unchanged). The mobile shell. `RELATIONSHIPS_SCHEMA_VERSION` stays 1
  (identity is settings rows, not a schema change).
