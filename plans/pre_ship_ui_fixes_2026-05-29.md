# Pre-ship UI fixes — #218, #219, #221, then #206 re-baseline

**Created:** 2026-05-29 · **Target ship:** ~2026-05-30 (`just ship`)

Three small install-landing / folder-banner UI bugs must land before the next
ship. They change the mobile UI, which invalidates the snapshot baselines — so
the **#206 mobile-snapshot refresh is deferred to the end**, after the UI is
final. (Discovered while working #206: the May-2 baselines are *already* stale
from a month of merged work — Filters button, dropped connection banner,
touch-target restyling — so the re-baseline captures all of that plus these
three fixes in one pass.)

All three UI bugs concentrate in `app/static/app.js` + `app/static/index.html`,
in the install-landing / `refreshFolderPushBanner()` machinery. #218 and #221
**edit the same function**, so they're done together.

## Ordering & rationale

1. **#219** — copy-only, zero interaction with the others. Quick warm-up.
2. **#218** — narrow *when* the folder banner shows (gate out install landing).
3. **#221** — add a *new state* the folder banner shows for (`write-failed`).
   Build on #218's gating so the two banner behaviors compose cleanly.
4. **#206** — refresh all 24 mobile baselines against the now-final UI. **Last**,
   because every step above moves pixels.

## Branch / PR strategy

Single branch `fix/pre-ship-ui-218-219-221` for the three fixes (they're
related, all install-landing/folder UI, all ship together, and #218+#221 touch
the same function). Land the three fixes + tests first; then **as the final
commit on the same branch**, run the #206 re-baseline so the committed PNGs
match the exact UI that branch ships. One PR, coherent story: "fix the banners,
re-baseline the screenshots the banner fixes (and prior drift) invalidated."

`just test` must be green before the #206 capture step (a red suite means the
UI we're about to bless is broken).

---

## #218 — Folder-push banner shows on install landing

**Bug:** `refreshFolderPushBanner()` (`app.js:8525`) shows the cream
"Save your fellows data to disk" banner whenever
`state.supported && state.workerAvailable && !state.hasHandle`. On the install
landing the worker is reachable but the user hasn't entered the app — there are
no groups/notes to lose, and the CTA navigates to `#/settings` where the button
is labeled "Choose folder…", not matching the banner's "Set up data folder".

**Fix:** add a gate so the banner only shows once the user is *in the directory
app* (past install landing), not on the landing itself. Concrete signal options
(confirm during impl):
- `installLandingEl` / `#install-gate-private` are hidden (not the active view), and/or
- the data provider has resolved — `window.__dataProvider && window.__dataProvider.kind` is truthy (on the landing the diagnostics show `dataProvider.kind: (none — boot incomplete)`).

Lead with the dataProvider-resolved check; it's the precise "boot ran" signal
the issue calls out. Keep the existing `supported / workerAvailable / hasHandle`
gates.

- **Edit:** `app/static/app.js` `refreshFolderPushBanner()` (~8536–8543).
- **Test:** extend `tests/e2e/test_install_landing.py` — assert
  `#folder-push-banner` is hidden while the install landing is showing.
- **Manual QA:** `just serve-prod`, incognito → magic-link → install landing →
  banner must NOT appear; click "Use the directory in this tab" → banner MAY
  appear (OPFS-only, capable browser).

## #219 — Install-landing fallback copy too technical

**Bug:** `index.html:196` leads with browser jargon: "No install prompt yet.
Two ways forward:". "Install prompt" is vendor-speak; "yet" implies waiting.

**Fix:** action-first copy. **Decided: the longer variant** (clarity wins; the
flow is genuinely hard to compress without losing users):
> **Open the existing install, or use the directory in this tab.**
> - If you've already installed this app on this device, open it from your dock,
>   Applications folder, or home screen.
> - Or **use the directory in this tab** below to skip installing for now.

- **Edit:** `app/static/index.html:195–203` — the
  `#install-unsupported-hint` lead `<p>` + two `<li>`s. Drop "install prompt"
  and "yet".
- **Test:** `tests/e2e/test_install_landing.py` (or `test_unsupported_browser.py`)
  — assert the rendered hint no longer contains "install prompt" and contains
  the new lead.
- **Manual QA:** install landing where `beforeinstallprompt` doesn't fire
  (already-installed Chrome profile, or click Install with no prompt) → the
  hint reads in plain language.
- **Docs:** if the wording is user-visible enough, note in
  `docs/users_manual.md` (install section) — likely not required for a hint
  string, confirm.

## #221 — Promote 'Last save failed' to a top-of-app banner

**Bug:** a failed folder write only surfaces as a pill badge inside
Settings → Private data folder. A user mid-brainstorm never opens Settings, so
they don't learn their last edit wasn't saved before closing the tab.

**Fix:** `badge()` (`app.js:8413`) already returns `'write-failed'`. Extend
`refreshFolderPushBanner()` to also fire when the badge is `write-failed`, with:
- urgent style (red/amber, not cream) — second CSS variant on the banner,
- copy: ⚠️ **Your latest change wasn't saved.** Another window has your data
  folder open — close it, then make any change to save. **[Open Settings]**
  (variant: surface `lastError.reason` when the cause isn't the Web-Lock case),
- the existing CTA repurposed/duplicated as **Open Settings** → `#/settings`,
  scroll to `#settings-folder-section` (the CTA already does this at 8557–8565),
- auto-clear when the next write succeeds (`lastSavedAt > lastError.at` — same
  state machine; banner becomes a second consumer of it).

Compose with #218: the banner now has three outcomes — hidden (in-app, folder
saved / not-yet-in-app), cream "set up folder" (in-app, OPFS-only, no handle),
red "last save failed" (in-app, `write-failed`).

- **Edit:** `app/static/app.js` `refreshFolderPushBanner()` + banner markup
  `index.html:119–128` (add the urgent-variant text/style); CSS in `styles.css`.
- **Test:** extend `tests/e2e/test_user_folder_storage.py` (the recent
  folder-write-failed badge UI test, commit `fd780b4`) — assert the top-of-app
  banner appears when the badge is `write-failed`, and clears on next successful
  write.
- **Manual QA:** maps to pre-ship plan §4.2 — once shipped, that step should
  also check the top banner (note this in `docs/pre_ship_test_plan.md`).

---

## #206 — Refresh mobile snapshot baselines (FINAL STEP)

After #218/#219/#221 land and `just test` is green:

```bash
just doctor
just db-rebuild                       # reproducible captures
just test-mobile tests/e2e/mobile/test_routes.py   # writes current_state/
# eyeball every route × device (about/settings changed by #205+#221;
#   directory/group-edit changed by #218 banner-gating; all 24 stale since May 2)
just test-mobile-promote              # copies ALL current_state/*.png → __snapshots__/
git add tests/e2e/mobile/__snapshots__/*.png
```

**Scope note for the commit:** refresh **all 24**, not the 6 named in #206.
The baselines are from May 2 and predate #205 + the Filters button + the dropped
connection banner (`b4403be`) + #179-PR-A touch-target restyling, none of which
re-baselined. All 24 current captures verified as healthy renders of `main`
during the #206 investigation (2026-05-29). Commit message should say so.

Proposed commit: `chore(mobile): refresh all 24 baselines after install-landing
banner fixes + accumulated UI drift (#206, #218, #219, #221)`.

---

## Decisions (locked 2026-05-29)

1. **#219 copy** — **longer variant** ("Open the existing install, or use the
   directory in this tab." + two bullets). User: clarity over brevity here.
2. **#218 gate signal** — **dataProvider-resolved** (`window.__dataProvider.kind`
   truthy) as the "boot ran / user is in the app" signal.
3. **#221 banner** — **one element** (`#folder-push-banner`) with a state class
   driving cream vs red copy/style.
4. **PR shape** — **single branch** `fix/pre-ship-ui-218-219-221`; #206
   re-baseline as the final commit.
```
