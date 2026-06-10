# Pre-ship test plan

The maintainer's **manual** QA checklist to run before every deploy to prod.

**This plan holds only the tests that can't (yet) be automated.** Everything that
*can* be automated is automated and runs under `just test` — and is therefore
**not** repeated here. There is no third place: automated tests live in `just test`,
manual tests live in this file. When an item here becomes automated, delete it from
this plan in the same change that lands the test.

> **This revision covers the private-data capability gate + the mobile redesign
> (PR6).** Both land in the same ship that takes prod off the pre-gate build. The
> gate makes private data (groups, members, tags, notes, group-settings, MCP)
> **live only when a verified folder is attached**; off-folder the app is
> **browse-only**. On phones, private data is **hidden** entirely. The two
> highest-risk manual paths this introduces — the **real OS folder gestures** and
> the **existing-user OPFS→folder migration** — have no automated equivalent and
> are the focus of §§2–4 (Phase 1) and §2 (Phase 2). UI labels below match the
> shipped Settings → **Private data** section; if a label drifted, trust the app.

Two phases:

- **Phase 1** runs locally against `just serve-prod` (see
  [`local_staging.md`](local_staging.md)). The irreducible local pass is the part
  that exercises the **real `just serve-prod` launcher** end-to-end and the **real
  OS gestures** (folder picker, permission round-trip, file downloads) that the
  Playwright stubs can't reach.
- **Phase 2** runs against `https://fellows.globaldonut.com/` **after** the deploy
  lands — real devices, real Postmark, real Caddy, real Claude Desktop.

If you find a regression in Phase 1, fix it before deploying. If you find one in
Phase 2, fix-forward (ship a second deploy) or roll back.

This is a **living document** — items are tied to the current shipped feature set.
Past per-batch snapshots live in `plans/maintainer_test_plan_through_pr_*.md`.

Each checkbox is numbered `<section>.<item>` so a regression report can say
"step 4.2 failed" without restating the flow.

---

## Pre-flight (one-time setup)

```bash
git checkout main && git pull         # confirm merges are local
just doctor                            # .venv + DB + Playwright OK
just build-mcpb                        # produces deploy/dist/mcpb/*.mcpb
just test                              # full pytest + Playwright — MUST be green
```

`just test` is the gate. It already covers the auth decision-tree, MCPB Settings UI
and auth-gated routes, the **capability gate's data-layer enforcement** (browse-only
refuses durable writes, even via the raw worker RPC; permission-lapse → reduce →
reconnect), folder-mode write/lock/backup logic, **mobile layout + interactions +
snapshots**, the update-banner logic, and the app-basics regression set. If
`just test` is red, fix it (or explicitly accept a known flake) before touching the
manual steps below — a red suite means the thing you'd otherwise hand-test is
already broken.

`just build-mcpb` only needs re-running when MCPB code changes (most ships don't touch
it; safe to re-run anyway).

## Per-session setup (each time you sit down to test)

```bash
just serve-prod                        # foreground; Ctrl-C to stop
```

The startup banner prints the test email (default `you@local-staging.example`) and
the magic-link log path. Open a **new incognito / private window** at
`http://127.0.0.1:8766/`.

Why incognito: nothing carries over from prior sessions. You see what a first-time
visitor sees — gate appears because `authEnabled: true`, which is the prod posture.

---

## Phase 1 — Local staging (`just serve-prod`)

### 1. Real-launcher magic-link round-trip

> The auth **decision-tree branches** and the **verify-token round-trip** are covered
> by `just test` (`test_email_gate.py`, `test_magic_link_standalone_unlock.py`,
> `test_install_landing.py`). This manual pass exists only to exercise the **real
> `just serve-prod` launcher** end-to-end — the in-process test fixture can't catch
> launcher-level SW/precache/build-stamp drift, and the e2e suite mocks
> `/api/auth/status` rather than driving the real auth path. The browser-observable
> half can be driven with chrome-devtools-mcp ([`debugging.md`](debugging.md) § Recipe C).

- [ ] **1.1** Email gate renders in the fresh incognito window (you're not auto-authed).
- [ ] **1.2** Paste the test email → **Send link** → "Check your email…" appears.
- [ ] **1.3** `just serve-prod-link` (second terminal) returns the unlock URL.
- [ ] **1.4** Paste the URL → install landing appears → **Use the directory in this
      tab** → directory loads.
- [ ] **1.5** You land in **browse-only** mode (no folder attached yet): directory +
      search + a fellow's detail + Email/Call all work; this is expected and correct.
- [ ] **1.6** `#/about` build badge shows the current local `git HEAD` short SHA
      (confirms the launcher's build-label substitution path; the literal
      `__FELLOWS_UI_DIAG__` here is a bug).
- [ ] **1.7** Submit a non-allowlisted email (e.g. `wrong@example.com`) → UI still
      says "Check your email…" and `just serve-prod-link` shows **no** new entry
      (anti-enumeration).

### 2. Capability gate — browse-only default → unlock with the real OS picker

> The gate's enforcement (off-folder refuses durable writes; folder attach enables
> them; a permission lapse reduces capability and reconnect restores it) is covered
> by `just test` (`test_private_data_enforcement.py`, `test_browse_only_durability.py`,
> `test_user_folder_storage.py`) against a **stubbed** picker. This pass covers what
> the stub can't: the **real OS directory-picker gesture**, the **OS permission
> round-trip + persistence**, and **Finder visibility** of the on-disk file and marker.

Start in the browse-only state from §1.

- [ ] **2.1** Browse-only is real, not cosmetic: group / private-data surfaces are
      gated. Settings shows the **Private data** section with the nag *"Private data
      (groups, notes) isn't connected — pick a folder to enable it."* The directory,
      search, fellow detail, and Email/Call still work.
- [ ] **2.2** Settings → **Private data** → **Choose folder…** → pick
      `~/Documents/local-staging/` (or any fresh folder). The real OS picker opens; grant
      permission.
- [ ] **2.3** Probe passes → the gate flips **live**: the badge shows *Where your data
      lives: …/Fellows*, group surfaces light up, and you can now create groups.
- [ ] **2.4** In Finder, `Fellows/relationships.db` exists **and** a human-readable
      `HOW-TO-MOVE-THIS-DATA.txt` marker sits beside it.

### 3. Folder mode — per-mutation durability, lock, reconnect

> Per-mutation badge/write logic, the Web Lock, and the backup ring run under
> `just test` against the stubbed picker (`test_user_folder_storage.py`). This pass
> covers the **real on-disk write** and the **real permission-revoke round-trip**.

- [ ] **3.1** Create / edit / delete a group → the on-disk `relationships.db`
      size/timestamp advances each time; a `relationships.db.bak.<ISO>` backup appears
      in the folder.
- [ ] **3.2** Settings → **⬇ Download my private data** → a real, self-describing
      `.db` blob (dated filename) lands in `~/Downloads`.
- [ ] **3.3** Settings → **🔒 Lock my private data** → the app drops back to
      browse-only, group surfaces gray out, and the badge reports the folder is
      disconnected. Confirm no durable writes happen while locked.
- [ ] **3.4** Permission-lapse → reconnect: revoke the folder permission (Chrome →
      site settings → reset permissions, or just relaunch and let the permission lapse)
      → the app reduces to browse-only with *"Locked — data folder disconnected. Pick a
      folder to unlock again."* → **🔄 Reconnect your folder** → probe passes → group
      surfaces restore with your data intact.

### 4. Existing-user migration — OPFS groups → folder (highest-risk path)

> The OPFS→folder copy + identity stamp + the content-previewed chooser are covered by
> `just test` (`test_user_folder_storage.py`, `test_folder_probe.py`) against seeded
> data. The **authoritative** check is Phase 2 §2 against a **real pre-gate install**;
> this local pass is a best-effort rehearsal of the prompt + non-destructive copy.

The migration prompt fires when a Chromium-desktop browser has **pre-gate OPFS groups
but no folder**. To rehearse locally you must get groups into OPFS without a folder
(e.g. create them in folder mode, then relocate/clear the folder so boot resolves
browse-only while OPFS still holds rows). If you can't easily seed that state, **defer
the real check to Phase 2 §2** — do not skip it silently.

- [ ] **4.1** Boot with OPFS groups present but no folder → the prompt appears:
      *"…`relationships.db` on this device. Pick a folder to keep …"* (browse-only
      otherwise — your groups are not silently active).
- [ ] **4.2** Pick a folder → probe passes → the OPFS groups are **copied into**
      `<folder>/Fellows/relationships.db` and the gate unlocks; group counts match.
- [ ] **4.3** Non-destructive: the OPFS copy is left intact until the folder write
      verifies, so a cancelled/failed pick never loses data.
- [ ] **4.4** Content-previewed chooser: re-pick a parent that already holds a
      `Fellows*` folder → the dialog *"This folder already contains fellows data"* /
      *"Use existing data here?"* previews groups/members/last-changed and defaults to
      **Open existing data** (adopt, don't proliferate).

### 5. Claude Desktop end-to-end *(only with Claude Desktop on macOS)*

> The MCPB **Settings UI** flow (preamble, three-bundle list, warning banner, cancel,
> continue-dispatches-three-downloads, button relabel, localStorage persistence) and
> the **auth-gated `/mcpb/*` routes** (403/200/404/suffix/traversal/content-type/log)
> are covered by `just test` (`test_mcpb_settings.py`, `test_deploy_mcpb_routes.py`).
> The MCP **server logic** is covered by `tests/test_*_data_ops.py`,
> `test_comms.py`, `test_mcpb_parity.py`. What stays manual: the native Claude Desktop
> install handshake and a live AI query — neither tool reaches Claude Desktop.

Private-data MCP needs **folder mode** — off-folder there is no private store for
`private_data_ops` to read (the setup surfaces a folder warning). Attach a folder
(§2) before this section.

- [ ] **5.1** Settings → **Set up Claude Desktop integration** → **Continue** → three
      real `.mcpb` files (~3–4 MB each; needs `just build-mcpb`) land in `~/Downloads`.
- [ ] **5.2** Drag each `.mcpb` into Claude Desktop → install dialog → **Install**
      (approve the red banner).
- [ ] **5.3** `private_data_ops.mcpb` asks for a file → navigate to
      `<your-data-folder>/Fellows/relationships.db` (the folder picked in §2).
- [ ] **5.4** **Quit Claude Desktop (⌘Q) and reopen.**
- [ ] **5.5** Ask *"How many fellows are in the directory?"* → expect a number.
- [ ] **5.6** Ask *"List my saved groups"* → expect the groups (or "none yet").
- [ ] **5.7** Ask *"Draft an invite email to my [group] group, don't send"* → a
      mail-compose window opens with To/Subject/Body pre-filled.

(The AI-query path is local-only — Claude Desktop ↔ local MCP subprocesses ↔ local
SQLite. No server contact.)

### 6. Cross-browser data silos (post-gate)

> _(Automation candidate: the silo concept + export/import migration are modelable
> with two Playwright contexts. The **real Safari** browse-only path below is the residue.)_

- [ ] **6.1** Open `http://127.0.0.1:8766/` in **Chrome** (folder attached, has groups)
      AND **Safari**; sign in to both.
- [ ] **6.2** About page in each → different install codenames.
- [ ] **6.3** Silo + browse-only: groups exist in Chrome; **Safari is browse-only —
      no groups and no private store at all** (Safari has no `showDirectoryPicker`). The
      Private-data section in Safari points to the *back up → install Chrome → restore*
      path, not a Safari-side store.
- [ ] **6.4** Migration is **Chrome-side**: Chrome → **⬇ Download my private data**;
      then in Chrome (a fresh/second folder) → **Restore from backup** → the group
      appears. Restore lands in **folder mode** — you cannot restore into Safari
      (no durable store there).

*Note: Safari "Add to Dock" on localhost may refuse — the browse-only behavior still
tests fine in a regular Safari window. Real Safari install is Phase 2.*

### 7. Shutdown

```bash
# Ctrl-C in the serve-prod terminal, or:
just serve-prod-stop
```

`tmp/prod-local/` persists across sessions (intentional — lets you resume).
`just serve-prod-reset` for a clean slate.

---

## Phase 2 — Prod smoke (after `just ship`)

Run only after the deploy has landed.

```bash
just ship                              # build + test + deploy + smoke
just whats-running                     # confirm prod git_sha matches HEAD
just drift                             # SHA-aligned 3-line view (local / origin / prod)
just smoke                             # HTTPS health + manifest + diagnostics + COOP/COEP/HSTS headers
```

### 1. First-time-visitor smoke (real Postmark)

> The browser-side gate→landing flow can be driven on real Chrome via
> chrome-devtools-mcp ([`debugging.md`](debugging.md) § Recipe A). The **real inbox
> receipt** below is irreducible.

- [ ] **1.1** New incognito window at `https://fellows.globaldonut.com/` → gate appears.
- [ ] **1.2** Submit your real email (one Postmark can deliver to).
- [ ] **1.3** **Check the real inbox** — email arrives; subject is current copy; body
      has the unlock URL, the "expires in 30 minutes" notice, and the signing-key
      fingerprint section.
- [ ] **1.4** Click the link **from the inbox** (not copy/paste) → install landing.
- [ ] **1.5** Install the PWA → it opens standalone → directory loads in **browse-only**.
- [ ] **1.6** About page build label matches `just drift`.

### 2. Existing-user upgrade — the migration path (do this first; highest risk)

> This is the path with **no automated equivalent** and the most exposure: real users
> on the pre-gate build who already created groups. There is no server-side state, so
> nothing migrates for them automatically across the deploy — the in-browser
> migration prompt (Chromium) or the manual export/import bridge (Safari/iOS) is the
> whole story. Test with a **real pre-gate install that has groups** — ideally your own.

- [ ] **2.1 (Chromium desktop):** open your existing pre-gate install that has groups
      → on boot you get the *"…pick a folder to keep…"* prompt → pick a folder →
      groups migrate into `<folder>/Fellows/relationships.db` → counts match, nothing lost.
- [ ] **2.2 (Safari / iOS with groups):** open an existing install that has groups in
      Safari or on a phone → it becomes **browse-only**; the groups are not active
      in-app. Confirm the in-app guidance points to the export/import bridge. **This is
      the population the test-group email is for** — the manual *back up → install
      Chrome → restore* recovery (the 15-minute call) is the supported path; verify you
      can walk it end-to-end for one such user before relying on it.

### 3. Real iOS Safari install — browse-only + mobile redesign (irreducible)

> Mobile layout/interactions/route-redirects are covered by `just test`
> (`tests/e2e/mobile/`, snapshot baselines) under **Chromium emulation**. Real iOS
> Safari is the residue — emulation can't reproduce the bottom-bar / safe-area
> behavior (§3.6).

- [ ] **3.1** Open `https://fellows.globaldonut.com/` on a real iPhone; magic-link
      round-trip works (real email, real Postmark).
- [ ] **3.2** **Add to Home Screen** → app installs → opens standalone → directory loads.
- [ ] **3.3** **Browse-only is correct on phone:** no group/selection chrome, no
      "choose folder" affordance (private-data controls are **hidden**, not grayed).
      Search + a fellow's detail work.
- [ ] **3.4** Mobile redesign: the **hamburger drawer** navigates (the desktop tab
      strip is gone on phones); the fellow detail shows the **Email / Call** call-to-actions.
- [ ] **3.5** Group routes redirect: manually visiting `#/groups` (or a group link)
      **redirects to the directory** rather than showing a broken/blank group screen.
- [ ] **3.6** Watch for the "bottom bar takes half the screen" safe-area symptom that
      Chromium emulation can't reproduce.

### 4. Real Android Chrome install *(if you have an Android device)*

> _(Optional assist: tether the device and drive it via chrome-devtools-mcp over
> `adb forward` + `--browser-url` — see [`debugging.md`](debugging.md) § Recipe D.)_

- [ ] **4.1** Same flow as iOS §3 (Chrome shows an "Add to Home Screen" prompt instead
      of Safari's share sheet): install → directory → **browse-only** (private data
      hidden — Android Chrome has the picker but routes through the Storage Access
      Framework, which can't keep the durable promise) → hamburger nav → Email/Call
      CTAs → group routes redirect.

### 5. Real MCPB install *(if you tested it in Phase 1)*

- [ ] **5.1** On prod, download a `.mcpb` from Settings → Claude Desktop integration.
- [ ] **5.2** Confirm it installs into Claude Desktop as in Phase 1 §5.
- [ ] **5.3** Quick query: "How many fellows are in the directory?" — count matches the
      build's `fellows.db`.

### 6. Update flow on a real install

> The drift→banner *logic* is covered by `just test` (`test_update_check.py`). What
> stays manual: the **real SW update** on a **really-installed** PWA — drivable on
> real Chrome via chrome-devtools-mcp ([`debugging.md`](debugging.md) § Recipe B).

- [ ] **6.1** Open your existing installed PWA (phone or laptop).
- [ ] **6.2** Within ~30 s the "New version available — Reload" banner appears.
- [ ] **6.3** Click Reload → fresh shell loads → About shows the new build label.
- [ ] **6.4** A folder-attached install keeps its groups across the update (the folder
      is the canonical store; the SW update only swaps the app shell).

### 7. Worst-case rollback (don't run unless needed)

```bash
git revert <bad-merge-commit>          # or git revert --no-commit <range>
just ship                              # re-deploys reverted state
just smoke
```

---

## What this plan doesn't cover (irreducible gaps)

Even with `just test` green and both phases passed, these operate on trust:

| Gap | Why | Mitigation |
|---|---|---|
| **Existing Safari/iOS users with groups** | The gate makes them browse-only; their OPFS groups can't migrate in-app (no folder on those platforms). | Manual *back up → install Chrome → restore* bridge + the test-group email + a 15-min call (Phase 2 §2.2). ~1–2 users. |
| **External-process folder concurrency** | Web Locks are per-origin per-browser-profile. Dropbox / iCloud / Syncthing replicating the folder, or a second browser on the same synced folder, can corrupt the file. | Out of scope in `plans/user_folder_storage.md` § Risks. Tell users not to sync `relationships.db`. |
| **Cross-device sync** | Intentionally unsupported; `relationships.db` is per-device. | Export / Import recipe in `docs/users_manual.md` § Migrating from another browser. |
| **Real Postmark deliverability across providers** | Gmail / Proton / Outlook each spam-score differently. | Ship-and-watch: `just prod-stats` send/verify counts; investigate Postmark if verify rate drops. |
| **Older Claude Desktop versions** | `.mcpb` format may not be recognized. | Surface the version-incompatibility error per `plans/easy_mcp_install.md` § Risks. |
| **Multi-tab worker takeover** | `plans/multi_tab_ownership_takeover.md` unimplemented; the 2nd tab fails with a generic panel. | Cheap "another tab is open" panel shipped; full takeover is post-MVP. |
| **Signing-key fingerprint TOFU window** | First-install trust anchors on the `sw.js`-embedded `PROD_PUBLIC_KEY_HEX`. | Magic-link email body carries the fingerprint for out-of-band cross-check (`docs/DevOps.md`). |

---

## Related

- [`local_staging.md`](local_staging.md) — how to run `just serve-prod`.
- [`feature_platform_matrix.md`](feature_platform_matrix.md) — the authoritative per-platform feature map (private data = verified folder only; phones browse-only).
- [`folder_troubleshooting.md`](folder_troubleshooting.md) — folder-pick/probe failure paths and the migration bridge.
- [`debugging.md`](debugging.md) — attaching Claude Code to your real Chrome via chrome-devtools-mcp (assist for the Phase-2 manual steps).
- [`DevOps.md`](DevOps.md) — what `just ship` / `just deploy` / `just smoke` do.
- [`email_gate.md`](email_gate.md) — the magic-link decision tree.
- [`persistence_and_upgrades.md`](persistence_and_upgrades.md) — the storage-layer matrix (browse-only = localStorage-only).
- `plans/maintainer_test_plan_through_pr_200.md` — superseded per-batch snapshot example.
