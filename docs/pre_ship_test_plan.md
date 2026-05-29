# Pre-ship test plan

The maintainer's **manual** QA checklist to run before every deploy to prod.

**This plan holds only the tests that can't (yet) be automated.** Everything that
*can* be automated is automated and runs under `just test` — and is therefore
**not** repeated here. There is no third place: automated tests live in `just test`,
manual tests live in this file. When an item here becomes automated, delete it from
this plan in the same change that lands the test.

Two phases:

- **Phase 1** runs locally against `just serve-prod` (see
  [`local_staging.md`](local_staging.md)). The irreducible local pass is the part
  that exercises the **real `just serve-prod` launcher** end-to-end and the **real
  OS gestures** (folder picker, file downloads) that the Playwright stubs can't reach.
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
and auth-gated routes, folder-mode write/badge logic, mobile layout + interactions,
the update-banner logic, and the app-basics regression set. If `just test` is red,
fix it (or explicitly accept a known flake) before touching the manual steps below —
a red suite means the thing you'd otherwise hand-test is already broken.

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
- [ ] **1.5** `#/about` build badge shows the current local `git HEAD` short SHA
      (confirms the launcher's build-label substitution path; the literal
      `__FELLOWS_UI_DIAG__` here is a bug).
- [ ] **1.6** Submit a non-allowlisted email (e.g. `wrong@example.com`) → UI still
      says "Check your email…" and `just serve-prod-link` shows **no** new entry
      (anti-enumeration).

### 2. Folder mode — real OS picker

> Per-mutation badge/write logic runs under `just test` against a stubbed picker
> (`test_user_folder_storage.py`). This manual pass covers what the stub deliberately
> skips: the **real OS directory-picker gesture**, the **OS permission round-trip**,
> and **Finder visibility** of the on-disk file.

Settings → **Choose data folder…** → pick `~/Documents/local-staging/` (or any fresh folder).

- [ ] **2.1** Badge flips to **Saved to local-staging / Fellows · just now**.
- [ ] **2.2** In Finder, `Fellows/relationships.db` exists.
- [ ] **2.3** Create / edit / delete a group → the on-disk file's size/timestamp
      advances each time.
- [ ] **2.4** Settings → **⬇ Download my private data** → a real `.db` blob lands in
      `~/Downloads`.

### 3. Claude Desktop end-to-end *(only with Claude Desktop on macOS)*

> The MCPB **Settings UI** flow (preamble, three-bundle list, warning banner, cancel,
> continue-dispatches-three-downloads, button relabel, localStorage persistence) and
> the **auth-gated `/mcpb/*` routes** (403/200/404/suffix/traversal/content-type/log)
> are covered by `just test` (`test_mcpb_settings.py`, `test_deploy_mcpb_routes.py`).
> The MCP **server logic** is covered by `tests/test_*_data_ops.py`,
> `test_comms.py`, `test_mcpb_parity.py`. What stays manual: the native Claude Desktop
> install handshake and a live AI query — neither tool reaches Claude Desktop.

- [ ] **3.1** Settings → **Set up Claude Desktop integration** → **Continue** → three
      real `.mcpb` files (~3–4 MB each; needs `just build-mcpb`) land in `~/Downloads`.
- [ ] **3.2** Drag each `.mcpb` into Claude Desktop → install dialog → **Install**
      (approve the red banner).
- [ ] **3.3** `private_data_ops.mcpb` asks for a file → navigate to
      `<your-data-folder>/Fellows/relationships.db` (the folder picked in §2).
- [ ] **3.4** **Quit Claude Desktop (⌘Q) and reopen.**
- [ ] **3.5** Ask *"How many fellows are in the directory?"* → expect a number.
- [ ] **3.6** Ask *"List my saved groups"* → expect the groups (or "none yet").
- [ ] **3.7** Ask *"Draft an invite email to my [group] group, don't send"* → a
      mail-compose window opens with To/Subject/Body pre-filled.

(The AI-query path is local-only — Claude Desktop ↔ local MCP subprocesses ↔ local
SQLite. No server contact.)

### 4. Cross-browser data silos

> _(Automation candidate: the silo concept + export/import migration are modelable
> with two Playwright contexts. The **real Safari** install path below is the residue.)_

- [ ] **4.1** Open `http://127.0.0.1:8766/` in **Chrome** AND **Safari**; sign in to both.
- [ ] **4.2** About page in each → different install codenames.
- [ ] **4.3** Create a group in Chrome → open Safari → no groups (silo confirmed;
      Safari uses OPFS-only fallback, no `showDirectoryPicker`).
- [ ] **4.4** Migrate: Chrome → ⬇ Download my private data; Safari → ⬆ Restore from a
      file → the Chrome group appears in Safari.

*Note: Safari "Add to Dock" on localhost may refuse — the silo behavior still tests
fine in a regular Safari window. Real Safari install is Phase 2.*

### 5. Shutdown

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
- [ ] **1.5** Install the PWA → it opens standalone → directory loads.
- [ ] **1.6** About page build label matches `just drift`.

### 2. Real iOS Safari install (irreducible)

- [ ] **2.1** Open `https://fellows.globaldonut.com/` on a real iPhone.
- [ ] **2.2** Magic-link round-trip works (real email, real Postmark).
- [ ] **2.3** **Add to Home Screen** from the share sheet → app installs.
- [ ] **2.4** Open the installed PWA → directory loads.
- [ ] **2.5** Tap a fellow → detail loads; back returns.
- [ ] **2.6** Select a fellow → composer FAB appears → tap → sheet opens → create a group.
- [ ] **2.7** Watch for the "bottom bar takes half the screen" symptom that Chromium
      emulation can't reproduce.

### 3. Real Android Chrome install *(if you have an Android device)*

> _(Optional assist: tether the device and drive it via chrome-devtools-mcp over
> `adb forward` + `--browser-url` — see [`debugging.md`](debugging.md) § Recipe D.)_

- [ ] **3.1** Same flow as iOS, but Chrome shows an "Add to Home Screen" prompt instead
      of Safari's share sheet.

### 4. Real MCPB install *(if you tested it in Phase 1)*

- [ ] **4.1** On prod, download a `.mcpb` from Settings → Claude Desktop integration.
- [ ] **4.2** Confirm it installs into Claude Desktop as in Phase 1 §3.
- [ ] **4.3** Quick query: "How many fellows are in the directory?" — count matches the
      build's `fellows.db`.

### 5. Update flow on a real install

> The drift→banner *logic* is covered by `just test` (`test_update_check.py`). What
> stays manual: the **real SW update** on a **really-installed** PWA — drivable on
> real Chrome via chrome-devtools-mcp ([`debugging.md`](debugging.md) § Recipe B).

- [ ] **5.1** Open your existing installed PWA (phone or laptop).
- [ ] **5.2** Within ~30 s the "New version available — Reload" banner appears.
- [ ] **5.3** Click Reload → fresh shell loads → About shows the new build label.

### 6. Worst-case rollback (don't run unless needed)

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
| **External-process folder concurrency** | Web Locks are per-origin per-browser-profile. Dropbox / iCloud / Syncthing replicating the folder, or a second browser on the same synced folder, can corrupt the file. | Out of scope in `plans/user_folder_storage.md` § Risks. Tell users not to sync `relationships.db`. |
| **Cross-device sync** | Intentionally unsupported; `relationships.db` is per-device. | Export / Import recipe in `docs/users_manual.md` § Migrating from another browser. |
| **Real Postmark deliverability across providers** | Gmail / Proton / Outlook each spam-score differently. | Ship-and-watch: `just prod-stats` send/verify counts; investigate Postmark if verify rate drops. |
| **Older Claude Desktop versions** | `.mcpb` format may not be recognized. | Surface the version-incompatibility error per `plans/easy_mcp_install.md` § Risks. |
| **Multi-tab worker takeover** | `plans/multi_tab_ownership_takeover.md` unimplemented; the 2nd tab fails with a generic panel. | Cheap "another tab is open" panel shipped; full takeover is post-MVP. |
| **Signing-key fingerprint TOFU window** | First-install trust anchors on the `sw.js`-embedded `PROD_PUBLIC_KEY_HEX`. | Magic-link email body carries the fingerprint for out-of-band cross-check (`docs/DevOps.md`). |

---

## Related

- [`local_staging.md`](local_staging.md) — how to run `just serve-prod`.
- [`debugging.md`](debugging.md) — attaching Claude Code to your real Chrome via chrome-devtools-mcp (assist for the Phase-2 manual steps).
- [`DevOps.md`](DevOps.md) — what `just ship` / `just deploy` / `just smoke` do.
- [`email_gate.md`](email_gate.md) — the magic-link decision tree.
- [`persistence_and_upgrades.md`](persistence_and_upgrades.md) — the storage-layer matrix.
- `plans/maintainer_test_plan_through_pr_200.md` — superseded per-batch snapshot example.
