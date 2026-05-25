# Maintainer test plan: features through PR #200

> **Captured 2026-05-23.** Snapshot of the maintainer test plan
> written during the MCP install ship-and-test cycle. Covers everything
> shipped in the 24-hour window roughly 2026-05-22 → 2026-05-23, plus
> the test-suite cleanup PRs that landed alongside.

## What's covered

| PR | Branch | Status | What it ships |
|---|---|---|---|
| #194 | `plan/easy-mcp-install-folder-anchor` | merged | Plan revision: folder anchor + Chromium-desktop Pareto + cross-browser silo acceptance |
| #195 | `docs/never-saas-definition` | merged | `docs/never-saas.md` — working definition + platform fitness matrix |
| #196 | `feat/install-codename` | merged | Per-install codename (`giraffe-gorilla-mouse`) + users-manual multi-install section + "Help from the user manual" relabel |
| #197 | `feat/mcpb-prod-routes` | merged | Auth-gated `GET /mcpb/<name>.mcpb` routes in `deploy/server.py` |
| #198 | `feat/mcpb-settings-ui` | merged | Settings UI + preamble dialog + walkthrough rewrite + migrate-from-browser hint (steps 6 / 7 / 8 of `plans/easy_mcp_install.md` § 12) |
| #199 | `fix/e2e-stale-ui-assertions` | merged | Unblocks 10 pre-existing e2e failures (build-badge removal aftermath + Playwright + showSaveFilePicker + User Guide rename) |
| #200 | `fix/about-update-check-flake` | merged | Fixes the last pre-existing e2e flake (TestAboutUpdateCheck — boot's `getFull` re-render clobbered `paintAppRow` output) |
| #201 | `feat/onboarding-clarity-pr200-followup` | open | Recommended-platform intro on users-manual, feature ↔ platform matrix doc, MCPB preamble restructure (warning to top, 6-step what-happens-next, three-extensions detail collapsed), Never-SaaS image |
| #203 | `feat/mcpb-preamble-feedback-pr202` | open | Round-2 preamble polish: new warning wording, removed redundant post-install panel, button label stays "Set up…", meta line bolded. Plus the test-plan section 4d/4e clarifications below. Stacked on #201. (Branch name says "pr202" because [GH issue #202](https://github.com/richbodo/fellows_local_db/issues/202) — data-folder "reveal in Finder" — took the number first.) |

After #200 merges, `just test` should run clean against `main` with no known failures or flakes from this 24-hour window.

## Test categories

- **(L)** Local — verifiable on the dev server (`just serve` or `just test`).
- **(S)** Ship — only verifiable against prod with auth gate + real
  `.mcpb` bundles + Claude Desktop.

## Pre-flight (do once)

```bash
just test      # full pytest suite, frees port 8765 first
just serve     # dev server on port 8765, foreground
```

`just test` runs `.venv/bin/pytest tests/ -v` and handles the venv +
port-free for you — no need to source the venv or type `python -m
pytest`. Other useful recipes:

- `just test-fast` — DB + API + prod-stats only (skips Playwright;
  ~10× faster, good for iteration).
- `just test-e2e` — Playwright e2e only. Supports a `-k` filter as
  the first argument: `just test-e2e mcpb` runs anything with `mcpb`
  in the test name.

If anything red after these PRs are merged, stop and debug.

---

## 1. Install codename (PR #196) — (L)

- [ ] **Window title** shows `EHF Fellows Directory · <three-word-codename>` after opening the app. Note the codename — call it CODE-A.
- [ ] **About page** (`#/about`) shows `This install: <CODE-A>` with a `(What's this?)` link.
- [ ] Clicking `(What's this?)` opens the users-manual on GitHub at the *Install name* anchor. The section renders.
- [ ] **About page** has `Help from the user manual` (was *User Guide*) — clicking it lands on the users-manual top.
- [ ] **Reload the tab** — codename is still CODE-A (not regenerated).
- [ ] **Click Report a bug** (small button bottom-left) — the dialog's pre-filled body contains `install codename: <CODE-A>` plus `install detected browser/OS:` and `install first launched (ISO):` lines.
- [ ] **Settings → Reset Everything**, confirm. Re-open the app — new codename CODE-B (different from CODE-A). This is intentional: a reset is a fresh start in every other respect too.

## 2. Never-SaaS docs (PR #195) — (L)

- [ ] `docs/never-saas.md` renders correctly on GitHub. Definition reads clearly. Platform-fitness matrix has the three categories (Strong fit / Stretched / Doesn't apply). PWA section explicitly calls out the user-authored-data stretch.
- [ ] No app-facing behavior to verify (docs-only).

## 3. Users-manual multi-install + migrate sections (PR #196 + #198) — (L)

- [ ] `docs/users_manual.md` now has, in order: **Multiple installs on the same device** (around line 106), **Migrating from another browser** (around line 189), then the existing **Where your data is stored**.
- [ ] All canonical browser uninstall links resolve (Apple Web Apps doc, Google PWA management doc).
- [ ] *Reporting a bug* section mentions install name.
- [ ] *About* section has the **Install name** subsection explaining the codename (reassuring tone, no instructional copy in-app).

## 4. MCPB Settings UI (PR #198) — (L)

Open the app, navigate to `#/settings`.

### 4a. Section renders
- [ ] **Claude Desktop integration (beta)** section appears below *Restore from backup*.
- [ ] Intro text reads correctly; **Walkthrough** link goes to GitHub.
- [ ] **Set up Claude Desktop integration** button visible.
- [ ] **Post-install panel** is hidden (no setup recorded yet).
- [ ] **Directory data update row** is hidden.

### 4b. Preamble dialog
- [ ] Click **Set up Claude Desktop integration** — preamble dialog opens.
- [ ] Dialog shows three numbered bundles: *Fellows directory (Shared)* / *Your saved groups (Private)* / *Email staging (Communications)*. Each has the privacy-boundary copy.
- [ ] Red **install-warning preview** banner is visible (gives the exact copy Claude Desktop will show).
- [ ] **Manual setup link** at the bottom points to `docs/use_with_claude_desktop.md`.
- [ ] If you have **no data folder set up**, the folder-warning yellow box is visible at the top of the dialog.
- [ ] If you're on **Safari or Firefox**, the browser-warning yellow box is visible at the top.

### 4c. Cancel flow
- [ ] Click **Cancel**. Dialog closes. No downloads fired. Status line empty.
- [ ] Setup button still says "Set up Claude Desktop integration."

### 4d. Continue flow (dev server returns 404 — that's expected locally)
- [ ] Click **Set up** → **Continue**. Status flips to *Downloading three .mcpb files…* then *Downloads triggered.*
- [ ] Browser pops up 3 download notifications (or starts 3 downloads). Each is a 404 / "File wasn't available on site" from the dev server. **Don't worry — that's expected; real bundles are served from prod.**
- [ ] **Setup button label is unchanged** — still says "Set up Claude Desktop integration." (This was a maintainer-flagged regression; the post-setup state lives in the meta line below the button now, not in a relabel.)
- [ ] **Setup-meta line** below the button is now visible: "Last set up: **just now**. Re-running this will replace the extensions you have installed in Claude Desktop." (The "just now" fragment is bold.)
- [ ] **Reload** the page — meta line persists with updated relative time ("Last set up: **a minute ago**").

### 4e. Directory-data-update affordance

> **Order matters** — the row only renders during `renderSettingsPage`, which runs on hash navigation. Don't expect the row to appear *on the same page view* where you set localStorage; navigate away and back.

- [ ] First confirm 4d above has been done so a `fellows_mcpb_setup` record exists (with a real `fellowsDbSha`).
- [ ] Open DevTools console (⌥⌘I) and run:
  ```js
  const s = JSON.parse(localStorage.getItem('fellows_mcpb_setup'));
  s.fellowsDbSha = 'stale-sha';
  localStorage.setItem('fellows_mcpb_setup', JSON.stringify(s));
  ```
  (Or if no setup record exists yet: `localStorage.setItem('fellows_mcpb_setup', JSON.stringify({setupAt: new Date().toISOString(), refreshedAt: new Date().toISOString(), fellowsDbSha: 'stale-sha'}))`)
- [ ] **Navigate away** from Settings (`#/about` works) then **navigate back** (`#/settings`). This triggers re-render; just clicking *Settings* in the nav also works.
- [ ] **Directory data update row** is now visible above the *Set up Claude Desktop integration* button, with a *Re-install Fellows directory* button.
- [ ] Click *Re-install Fellows directory* — single download fires (`shared_data_ops.mcpb`).
- [ ] To clean up: `localStorage.removeItem('fellows_mcpb_setup')` + reload.

## 5. Migrate-from-another-browser hint (PR #198) — (L)

- [ ] Settings → *Restore from backup* section now has the inline hint "Migrating from another browser? See the recipe..."
- [ ] Click the link — lands on the users-manual *Migrating from another browser* section. Recipe is the two-step *Download from source → Restore in target* flow.

---

## 6. /mcpb prod routes (PR #197) — (S)

These routes only exist in `deploy/server.py`, not in the dev server.
So this section requires deploying.

After deploy:

- [ ] **Incognito window** (no session cookie): visit `https://fellows.globaldonut.com/mcpb/comms.mcpb` — expect `403 Forbidden`. No bundle bytes in the response body.
- [ ] **Logged-in browser** (magic-link gate passed): visit the same URL — expect a download to start, file ~3.4 MB.
- [ ] Repeat for `/mcpb/shared_data_ops.mcpb` (~4 MB, carries `fellows.db`) and `/mcpb/private_data_ops.mcpb` (~4 MB).
- [ ] Visit `/mcpb/bogus.mcpb` (logged in) — expect `404 Not Found`.
- [ ] Visit `/mcpb/comms.txt` (logged in) — expect `404` or `403`. Should NOT serve the .mcpb bytes under a .txt suffix.
- [ ] Server-side: `journalctl -u fellows-pwa` should show a `mcpb_download` JSON line for each successful hit, with `name`, `size_bytes`, and a UA prefix.

## 7. Full Claude Desktop integration flow (PR #198 + #197 + bundles deployed) — (S)

This is the flagship demo. Requires the `.mcpb` bundles uploaded to
`deploy/dist/mcpb/` on prod.

### 7a. Build + deploy the bundles

```bash
just build-mcpb   # produces deploy/dist/mcpb/{comms,shared_data_ops,private_data_ops}.mcpb
# Then your normal deploy
```

### 7b. End-to-end install on a fresh Mac (Chromium)

- [ ] Open the app in Chrome on macOS. Sign in via magic link.
- [ ] **Settings → Data folder → Choose data folder…** — pick a folder. Confirm `relationships.db` lands at `<folder>/Fellows/relationships.db`.
- [ ] **Settings → Set up Claude Desktop integration** → **Continue**.
- [ ] All three `.mcpb` files arrive in Downloads.
- [ ] Open `shared_data_ops.mcpb` → Claude Desktop install dialog appears → **Install** (approve the red banner).
- [ ] Open `private_data_ops.mcpb` → install dialog asks for a file → navigate to `<folder>/Fellows/relationships.db`, select → **Install**.
- [ ] Open `comms.mcpb` → install dialog → **Install**.
- [ ] **Quit Claude Desktop (⌘Q) and reopen.**
- [ ] Open a new chat: *"How many fellows are in the directory?"* — expect a number back.
- [ ] *"List my saved groups"* — expect Claude to list your groups (or "none yet" if you have none).
- [ ] *"Draft an invite email to my [group] group, don't send"* — expect a mail-compose window to open in your default mail app with To/Subject/Body filled in.

### 7c. Refresh flows

- [ ] In the Fellows app, **modify a group** (add a member or rename). In Claude Desktop, ask about the group — expect the new state visible immediately (no .mcpb reinstall needed; private_data_ops reads relationships.db live from the folder).
- [ ] **Simulate a directory update**: in prod, ship a new `fellows.db` snapshot. Reload the Fellows app — *About* shows *Directory Data update available*. Click *Update directory data* to refresh `fellows.db` locally.
- [ ] Settings → Claude Desktop integration (beta) now shows the **Directory data update available** row. Click *Re-install Fellows directory* → one download arrives. Open it → install in Claude Desktop → restart. Confirm Claude sees the new directory data.

## 8. Cross-browser behavior (PR #198 + #196 working together) — (S)

This validates the multi-install handling end-to-end.

- [ ] On the same Mac, install the Fellows app in **Safari** AND **Chrome**.
- [ ] In each browser, confirm the **About → Install name** is different (e.g., `giraffe-gorilla-mouse` vs `otter-koala-falcon`).
- [ ] Confirm the **window title** of each install shows its own codename.
- [ ] In **Spotlight**, search for "EHF" — both copies appear, identical names/icons. As documented.
- [ ] In **Finder**, rename `~/Applications/EHF Fellows Directory.app` (Safari's) to `EHF Fellows — Safari.app`. Spotlight now distinguishes them.
- [ ] Create a group in Safari. Open the Chrome copy — empty state, no group. As documented.
- [ ] Follow the **Migrating from another browser** recipe:
  - Safari: Settings → ⬇ Download my user data. Save to `~/Documents/rels_from_safari.db`.
  - Chrome: Settings → Data folder → Choose data folder…. Pick a folder.
  - Chrome: Settings → ⬆ Restore from a file → pick `rels_from_safari.db`.
  - Confirm the group from Safari now visible in Chrome.
- [ ] Uninstall the Safari copy (drag `EHF Fellows — Safari.app` to Trash). Safari's data is gone but the data folder Chrome uses is untouched.

## 9. Sanity regression — (L, do last)

After all PRs merged, run:

```bash
just test
```

Expect everything green. The 24-hour delta added 30 new cases (12
mcpb-settings + 12 mcpb-routes + 6 codename), and #199 + #200
cleaned up 11 pre-existing failures, so the suite is materially
healthier than it was going in.

---

## What to surface back when you find issues

When you're testing, capture:

1. **Anything that doesn't work** — exact symptom + console error / network panel / screenshot if visible.
2. **Anything that feels off in the copy** — preamble wording, walkthrough wording, error messages.
3. **The Claude Desktop install-warning banner screenshot** — for the disclosure copy refinement (issue #186). The current preamble copy is a best-guess; pinning it to the actual screenshot is a small follow-up.
4. **Any browser-specific gotcha** you hit on the Safari/Firefox secondary path that's not documented.
