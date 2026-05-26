# Pre-ship test plan

The maintainer's manual-QA checklist to run **before every deploy to prod**.
Two phases:

- **Phase 1** runs locally against `just serve-prod` (see
  [`local_staging.md`](local_staging.md)). Covers everything the local
  staging server can reach: auth flow, MCPB routes, folder mode, lock
  behavior, cross-browser data silos.
- **Phase 2** runs against `https://fellows.globaldonut.com/` **after**
  the deploy lands. Covers only the irreducible real-device / real-network
  tests that local staging can't replicate.

If you find a regression in Phase 1, fix it before deploying. If you
find one in Phase 2, fix-forward (ship a second deploy) or roll back.
The point of the two-phase split is to keep Phase 2 small enough that
a real-world regression is rare and localized.

This is a **living document** — the test items are tied to the current
shipped feature set, not a snapshot of a specific batch. Past per-batch
snapshots live in `plans/maintainer_test_plan_through_pr_*.md`.

---

## Pre-flight (one-time setup)

```bash
git checkout main && git pull         # confirm merges are local
just doctor                            # .venv + DB + Playwright OK
just build-mcpb                        # produces deploy/dist/mcpb/*.mcpb
just test                              # full pytest + Playwright
```

`just build-mcpb` only needs re-running when MCPB code changes (most ships
don't touch it; safe to re-run anyway). If `just test` is red, fix or
explicitly accept the flake and continue.

## Per-session setup (each time you sit down to test)

```bash
just serve-prod                        # foreground; Ctrl-C to stop
```

The startup banner prints the test email (default
`you@local-staging.example`) and the magic-link log path. Open a **new
incognito / private window** at `http://127.0.0.1:8766/`.

Why incognito: nothing carries over from prior sessions. You see what a
first-time visitor sees — gate appears because `authEnabled: true`,
which is the prod posture.

---

## Phase 1 — Local staging (`just serve-prod`)

### 1. Magic-link auth round-trip

- [ ] Email gate renders (you're not auto-authed).
- [ ] Paste the test email shown on the launcher banner → click **Send
      link** → UI shows "Check your email…" (anti-enum response).
- [ ] In a second terminal: `just serve-prod-link` returns the unlock URL.
- [ ] Paste the URL into the same browser → install landing appears
      (`authStatus.authenticated && installRecentlyAllowed`).
- [ ] **"Back to email gate"** link returns you to the gate; cookie cleared.
- [ ] Re-submit gate, get a new link, paste → back at install landing.
- [ ] Click **"Use the directory in this tab"** → directory loads.
- [ ] Build badge in lower-right shows the current local `git HEAD` short SHA.

### 2. Email-gate edge cases

- [ ] Append `?gate=1` to a logged-in tab's URL → gate UI overrides
      (cookie still valid; just forces the gate view).
- [ ] Wait 30+ minutes after issuing a link, paste it → land at
      `/?gate=1&reason=expired` with the "that link expired" banner.
      (You can shortcut this by editing the token in the URL — wrong
      token also triggers `reason=invalid`.)
- [ ] Submit a non-allowlisted email (e.g. `wrong@example.com`) → UI
      still says "Check your email…" (anti-enum); `just serve-prod-link`
      shows no new entry.

### 3. MCPB Settings UI (was § 4 of the per-batch plan)

Navigate to `#/settings`.

- [ ] **Claude Desktop integration (beta)** section renders below Restore
      from backup.
- [ ] Click **Set up Claude Desktop integration** → preamble dialog
      opens. Three numbered bundles listed with privacy boundaries.
- [ ] Red install-warning preview banner is visible.
- [ ] **Cancel** → dialog closes; no downloads fired.
- [ ] Click **Set up** → **Continue** → three downloads arrive in
      `~/Downloads` (~3-4 MB each — these are the real bundles, unlike
      the dev server which 404s).
- [ ] Setup button relabels to "Re-download all extensions."
- [ ] Reload the page → state persists.

### 4. MCPB auth-gated routes (was § 6 of the per-batch plan)

- [ ] **Incognito window** (no session cookie):
      `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8766/mcpb/comms.mcpb` → expect `403`.
- [ ] Authenticated browser: `/mcpb/comms.mcpb` downloads ~3.4 MB.
- [ ] Repeat for `/mcpb/shared_data_ops.mcpb` and `/mcpb/private_data_ops.mcpb` (~4 MB each).
- [ ] `/mcpb/bogus.mcpb` → 404.
- [ ] `/mcpb/comms.txt` → 404 (must not serve under wrong suffix).
- [ ] Launcher terminal shows a `mcpb_download` JSON line for each hit.

### 5. Claude Desktop end-to-end (only if you have Claude Desktop on macOS)

- [ ] After downloads from step 3 land, drag each `.mcpb` into Claude
      Desktop → install dialog → **Install** (approve the red banner).
- [ ] `private_data_ops.mcpb` asks for a file → navigate to
      `<your-data-folder>/Fellows/relationships.db`.
- [ ] **Quit Claude Desktop (⌘Q) and reopen.**
- [ ] Ask: *"How many fellows are in the directory?"* → expect a number.
- [ ] *"List my saved groups"* → expect Claude to list groups (or "none
      yet").
- [ ] *"Draft an invite email to my [group] group, don't send"* →
      mail-compose window opens with To/Subject/Body pre-filled.

(The AI-query path is local-only — Claude Desktop talks to local MCP
subprocesses talking to local SQLite files. No server contact, real or
staging.)

### 6. Folder mode (Phase 2 happy path)

Settings → **Choose data folder…** → pick `~/Documents/local-staging/`
(or any fresh folder).

- [ ] Badge flips to **Saved to local-staging / Fellows · just now**.
- [ ] Open the folder in Finder — `Fellows/relationships.db` exists.
- [ ] Create a group "Test G1" with three fellows → badge subtitle
      updates ("just now"). Folder file size increases.
- [ ] Edit the group → folder file timestamp advances.
- [ ] Delete the group → folder file timestamp advances.
- [ ] Settings → **⬇ Download my private data** → returns a `.db` blob.

### 7. Folder Web Lock — manual verification

Open DevTools console:

```js
navigator.locks.request(
  'fellows-relationships-folder-write',
  { mode: 'exclusive' },
  () => new Promise(() => {})   // holds forever
);
```

- [ ] Create another group → badge flips to **"Last save failed — Change
      folder to re-pick"** within a second.
- [ ] Hover the badge or check the diagnostics panel — error reason
      reads *"Another window has this folder open — close it, then make
      any change to retry the save."*
- [ ] Reload the tab (releases the lock).
- [ ] Make a fresh mutation (rename a group, change a setting) → badge
      returns to Saved. Folder file now contains the previously-failed
      mutation too.

### 8. Honest mutation loss on tab close

- [ ] Open a new incognito window. Sign in. Pick the same data folder
      (open-existing path). Confirm group "Test G1" is visible.
- [ ] Create group "Doomed". Hold the lock in DevTools (same snippet
      as step 7).
- [ ] Create group "Lost". Badge says "Last save failed."
- [ ] **Close the window without releasing the lock.**
- [ ] Open a fresh incognito window. Sign in. Pick the same folder.
- [ ] Confirm "Test G1" and "Doomed" are visible; **"Lost" is gone**.
      (This is the honest mutation loss the badge warned about —
      verified end-to-end.)

### 9. Cross-browser data silos (was § 8 of the per-batch plan)

- [ ] Open `http://127.0.0.1:8766/` in **Chrome** AND **Safari**, sign
      in to both.
- [ ] About page in each → different install codenames.
- [ ] Create a group in Chrome. Open the Safari copy → no groups (data
      silo confirmed). Safari install uses OPFS-only fallback (no
      `showDirectoryPicker`).
- [ ] Migrate via the documented recipe:
      - Chrome: Settings → ⬇ Download my private data → save to a file.
      - Safari: Settings → ⬆ Restore from a file → pick the file.
      - Group from Chrome appears in Safari.

*Note: Safari "Add to Dock" on localhost may refuse. If it does, the
data-silo behavior still tests fine in a regular Safari window — you've
just hit the limit of local staging. Real Safari install testing is
Phase 2 (on prod).*

### 10. Mobile layout (Chrome DevTools responsive mode)

- [ ] DevTools → toggle device toolbar → iPhone 13 / Pixel 5 / 360px wide.
- [ ] Directory route: rows have ≥ 44×44 tap targets; no horizontal
      overflow.
- [ ] Select a fellow → composer FAB appears (the #179 fix — without
      this, mobile users can't create groups).
- [ ] Open the composer FAB → composer sheet slides up → type a name →
      Create new group works.
- [ ] Fellow detail: copy buttons, social links all clearly tappable
      (≥ 44×44).
- [ ] Settings: all buttons tappable; kebab menu opens cleanly.

### 11. App basics (regression guards)

- [ ] About page renders; install codename present; "Help from the
      user manual" link works.
- [ ] Directory search returns results.
- [ ] Click a fellow → detail page; back arrow returns to directory.
- [ ] Groups index → create, edit, delete group.
- [ ] Visual directory route for a group renders portraits.
- [ ] Settings: change "me" email, save → persists across reload.
- [ ] Bug-report button (bottom-left) pre-fills install codename +
      browser/OS + first-launch ISO.
- [ ] Update banner appears if you rebuild the dist (`just serve-prod-reset`
      → `just serve-prod` again — bumps the build label, SW notices on
      next visit).

### 12. Shutdown

```bash
# Ctrl-C in serve-prod terminal, or:
just serve-prod-stop
```

`tmp/prod-local/` persists across sessions (intentional — lets you
resume). `just serve-prod-reset` for a clean slate next time.

---

## Phase 2 — Prod smoke (after `just ship`)

Run only after the deploy has landed.

```bash
just ship                              # build + test + deploy + smoke
just whats-running                     # confirm prod git_sha matches HEAD
just drift                             # SHA-aligned 3-line view (local / origin / prod)
just smoke                             # HTTPS health + manifest probe
```

### 1. First-time-visitor smoke

- [ ] **New incognito window** at `https://fellows.globaldonut.com/` →
      gate appears.
- [ ] Submit your real email (the one Postmark can deliver to).
- [ ] **Check the real inbox** — email arrives. Subject line is the
      current expected copy. Body includes the unlock URL and the
      "expires in 30 minutes" notice. Signing-key fingerprint section
      present.
- [ ] Click the link from the inbox (NOT a copy/paste — verify the
      actual email flow). Land on install landing.
- [ ] Install the PWA from the install landing.
- [ ] App opens from the installed PWA window → directory loads.
- [ ] About page shows the build label that matches `just drift` output.

### 2. Real iOS Safari install (irreducible)

- [ ] Open `https://fellows.globaldonut.com/` on a real iPhone.
- [ ] Magic-link round-trip works (same email, same Postmark delivery).
- [ ] **Add to Home Screen** from Safari's share sheet → app installs.
- [ ] Open the installed PWA → directory loads.
- [ ] **Tap a fellow** → detail loads. Back arrow returns.
- [ ] **Select a fellow** → composer FAB appears. Tap → composer sheet
      opens. Create a group.
- [ ] **Check for the "bottom bar takes half the screen" symptom** that
      didn't reproduce in Chromium emulation. If it appears, it's a real
      iOS Safari viewport quirk we couldn't catch locally.

### 3. Real Android Chrome install (if you have an Android device)

- [ ] Same flow as iOS, but Chrome shows an "Add to Home Screen" prompt
      instead of Safari's share sheet.

### 4. Caddy header preservation

Inspect the response headers on a prod request — Caddy adds the headers
the python server omits. Quick spot check:

```bash
curl -sI https://fellows.globaldonut.com/ | grep -iE "strict-transport|cross-origin"
```

Expect:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Embedder-Policy: require-corp`

If any are missing, Caddy config drifted. See `docs/DevOps.md` § Architecture-at-a-glance for the COOP/COEP gotcha.

### 5. Real MCPB install (if you tested it in Phase 1)

- [ ] On prod, download a `.mcpb` from Settings → MCPB.
- [ ] Confirm it installs into Claude Desktop just like Phase 1.
- [ ] Quick query: "How many fellows are in the directory?" — confirm
      the count matches the build's `fellows.db`.

### 6. Update flow

- [ ] **Existing installed PWA** (your phone or laptop) — open it.
- [ ] Within ~30 seconds the "New version available — Reload" banner
      should appear (SW noticed the new build).
- [ ] Click Reload → fresh shell loads. About page shows the new
      build label.

### 7. Worst-case rollback (don't run unless needed)

If a Phase 2 finding is bad enough to need rollback:

```bash
git revert <bad-merge-commit>          # or git revert --no-commit <range>
just ship                              # re-deploys reverted state
just smoke
```

---

## What this doesn't cover (irreducible gaps)

Even with Phase 1 + Phase 2 both green, the following are still
operating on trust and not direct verification:

| Gap | Why | Mitigation |
|---|---|---|
| **External-process folder concurrency** | Web Locks are per-origin per-browser-profile. Dropbox / iCloud / Syncthing replicating the folder bytes, or a second browser pointed at the same synced folder, can corrupt the file. | Documented as out of scope in `plans/user_folder_storage.md` § Risks. Tell users not to use synced folders for `relationships.db`. |
| **Cross-device sync** | Intentionally not supported. The `relationships.db` is per-device. | Export / Import recipe in `docs/users_manual.md` § Migrating from another browser. |
| **Real Postmark deliverability across all email providers** | Gmail, ProtonMail, Outlook, etc. each apply their own spam scoring. | Ship-and-watch: `just prod-stats` reports send/verify counts; if verify rate is anomalously low after a deploy, investigate Postmark dashboard. |
| **Older Claude Desktop versions** | `.mcpb` format may not be recognized. | Surface the version-incompatibility error per `plans/easy_mcp_install.md` § Risks. |
| **Multi-tab worker takeover** | `plans/multi_tab_ownership_takeover.md` is unimplemented. Two tabs both attempting to open `relationships.db` will fail the second with a generic panel. | Cheap-fix landed earlier shows "another tab is open"; full takeover is post-MVP. |
| **The signing-key fingerprint TOFU window** | First-time install trust is anchored on the `sw.js`-embedded `PROD_PUBLIC_KEY_HEX`. | Magic-link email body includes the fingerprint for out-of-band cross-check (`docs/DevOps.md` § Out-of-band fingerprint publication). |

If any of these surface as recurring real-world issues, they're candidates
for a future sprint — but they're explicitly accepted gaps, not test-plan
oversights.

---

## Related

- [`local_staging.md`](local_staging.md) — how to run `just serve-prod`.
- [`DevOps.md`](DevOps.md) — what `just ship` / `just deploy` / `just smoke`
  do under the hood.
- [`email_gate.md`](email_gate.md) — the magic-link decision tree this plan
  exercises.
- [`persistence_and_upgrades.md`](persistence_and_upgrades.md) — the
  storage-layer matrix this plan's folder/OPFS tests touch.
- `plans/maintainer_test_plan_through_pr_200.md` — snapshot example of
  per-batch test plans (now superseded by this living doc).
