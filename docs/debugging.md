# Debugging

Playbooks for the debug scenarios that have actually come up on this project.

## Inspecting a developer's live Chrome via Claude Code

When a PWA bug reproduces on your own browser but not on a clean Playwright profile (stuck service worker, stale cached shell, misbehaving installed PWA, cookie/session state you can't explain), let Claude Code attach to your real Chrome and inspect it directly. This is the setup that traced the "install landing appears without a magic link" bug to a pre-auth-gate `app.js` lingering in JS memory after the old cacheFirst SW had been cleared.

### One-time install

```bash
claude mcp add --scope user chrome-devtools -- npx -y chrome-devtools-mcp@latest --no-usage-statistics
claude mcp list   # verify: chrome-devtools - ✓ Connected
```

Requires Node 20.19+ and a current Chrome. User-scope (`~/.claude.json`) keeps this available across all projects without committing it to the repo.

### Attaching to your running Chrome (the case that motivated this doc)

Default mode launches its own clean Chrome, which will never show the bug you're chasing on your own profile — use this mode only when you want Claude to see **your** browser state.

1. **Quit Chrome completely** (`Cmd+Q`, not just close windows). Anything short of a full quit keeps the existing process around without the remote-debugging port.
2. Relaunch with the debug port bound to loopback:
   ```bash
   open -na "Google Chrome" --args \
     --remote-debugging-port=9222 \
     --user-data-dir="$HOME/Library/Application Support/Google/Chrome"
   ```
   `--user-data-dir` pointing at your normal profile is what lets the attached session see your real cookies, service workers, and installed PWAs. Drop that flag if you want a throwaway profile.
3. Confirm the port is live: `curl -s http://127.0.0.1:9222/json/version | head -5` should return JSON with the Chrome version.
4. In Claude Code, ask Claude to attach to `http://127.0.0.1:9222`. The `mcp__chrome-devtools__*` tools become available and Claude can run JS in your pages, inspect DOM/Network/Console, and read cookies/cache/SW state.

### Privacy caveat

While `--remote-debugging-port=9222` is open, **anything loaded in that Chrome is visible to Claude** — including banking, email, and other unrelated tabs. The port binds to 127.0.0.1 so only local processes can connect, but treat the session as non-private. When you're done debugging:

- Quit Chrome (`Cmd+Q`) and relaunch normally without the flag.
- Or narrow blast radius during the session: only open the tab you're debugging and a fresh profile (`--user-data-dir=/tmp/chrome-debug`) — this trades off the ability to see real cookies / installed PWAs.

### Useful first requests to hand off

When asking Claude to debug a stuck browser, lead with one of these — they give concrete ground truth fast:

- *"Attach to my Chrome on port 9222, navigate to `https://fellows.globaldonut.com/`, and report `/api/auth/status`, `navigator.serviceWorker.getRegistrations()`, `caches.keys()`, and whether the running `app.js` defines `window.clearAllAppData`."*
- *"Attach, open the page, run my snippet in the console, and paste the JSON output back."*

### When to use the default (isolated) mode instead

If you're reproducing a bug on a **fresh** visitor (first-time install, behavior for someone who's never been to the site), the isolated mode is what you want — it guarantees no residue from any past session. That's the mode the `/tmp/fellows_debug/probe.py` Playwright scripts already cover, and chrome-devtools-mcp can do the same thing interactively.

## Production PWA bundle drift

When local code and production behavior diverge, check that the droplet is on current `main`:

```bash
just drift              # prod git SHA vs local HEAD + origin/main, side-by-side
just deploy             # rebuild bundle and push if prod is behind
just ship-fast          # if deploy/dist/ is already current, just re-push + smoke
```

Under the hood: `just drift` curls `https://fellows.globaldonut.com/build-meta.json` for prod's git SHA and `built_at`, then formats it next to `git log -1 HEAD` and `git log -1 origin/main`. All three lines have the same shape — `<sha> <iso-timestamp> <subject>` — so a glance tells you whether prod, your laptop, and the remote are in sync. Production has shipped with stale `deploy/dist/` before; if prod's SHA trails origin/main, run `just deploy` (or `./scripts/deploy_pwa.sh --ask-become-pass`).

Other production debug entry points (service logs, Postmark send flow, Diagnostics panel) live in [`docs/email_system_management.md`](email_system_management.md) and [`docs/DevOps.md`](DevOps.md).

## Pre-ship assist recipes (chrome-devtools-mcp)

A handful of [`pre_ship_test_plan.md`](pre_ship_test_plan.md) steps can't be CI-gated
under `just test` — they need a **real** Chrome with real service-worker / OPFS /
installed-PWA state, or the real launcher. They stay manual, but you don't have to
click through them by hand: attach Claude Code to a real Chrome (see *Attaching to your
running Chrome* above) and hand off the matching recipe below. Each recipe is an
attach-and-assert prompt — Claude drives the browser and reports pass/fail. None of
them remove the **irreducible** part of the step (real inbox receipt, real device,
the native Claude Desktop handshake); they automate the browser-observable part.

Selectors/signals these lean on (all real, used by the e2e suite too): `#sw-update-banner`
(the "New version available — Reload" banner), `#install-gate-private` (email gate),
`window.__dataProvider.kind` (`'worker'` on the happy path), `window.__bootMarks`,
`navigator.serviceWorker.controller`, `/api/auth/status`, `/build-meta.json`, and the
`#/about` build badge. If served JS still contains the literal `__FELLOWS_UI_DIAG__`
or `__CACHE_VERSION__`, the build-label substitution didn't run — that's a bug.

### Recipe A — first-visit smoke on prod (Phase 2 §1, browser portion)

Use **isolated mode** (throwaway profile) so it's a true first-time visitor.

> *"Attach to a fresh isolated Chrome, open `https://fellows.globaldonut.com/`, and
> report: (1) `GET /api/auth/status` returns `authEnabled:true, authenticated:false`;
> (2) `#install-gate-private` is visible and `#directory` is not; (3) no console errors
> and no failed network requests on load; (4) the served `app.js` contains neither
> `__FELLOWS_UI_DIAG__` nor `__CACHE_VERSION__`. Do NOT submit an email — the real
> inbox receipt (steps 1.2–1.6) is mine to do by hand."*

Replaces the eyeball of 1.1; leaves the real Postmark round-trip (1.2–1.6) manual.

### Recipe B — update banner on a real installed PWA (Phase 2 §5)

Use **real-profile mode** (your normal `--user-data-dir`) so the actually-installed PWA
and its registered SW are in scope. Re-read the **privacy caveat** above first — every
tab in that Chrome is visible to Claude for the session.

> *"Attach to my running Chrome (port 9222, my real profile). Open the installed Fellows
> PWA (or `https://fellows.globaldonut.com/`). Report the current `#/about` build label
> and `GET /build-meta.json` `git_sha`. Then wait for me to say 'deployed'; on that
> signal, reload-poll for up to 60s and confirm: `#sw-update-banner` becomes visible,
> then click its Reload control and confirm `navigator.serviceWorker.controller` changed
> and the `#/about` build label now matches the new `/build-meta.json` `git_sha`."*

Pinned in `just test` only as drift→banner *logic* (`test_update_check.py`); this recipe
exercises the **real SW update** on a really-installed app.

### Recipe C — real `serve-prod` launcher SW/precache pass (Phase 1 §1 caveat)

The one gap the in-process `deploy_server` fixture can't cover: the real launcher's
dist-build + SW-precache + build-label-stamp path. Run `just serve-prod` first.

> *"Attach to a fresh isolated Chrome, open `http://127.0.0.1:8766/`, and report:
> (1) the served `app.js` and `sw.js` contain neither `__FELLOWS_UI_DIAG__` nor
> `__CACHE_VERSION__` (stamp ran); (2) `window.__dataProvider.kind === 'worker'` and
> `window.__bootMarks.get_full_done` is set (clean boot); (3) the `#/about` build badge
> shows my current `git rev-parse --short HEAD`. Then I'll run
> `just serve-prod-reset && just serve-prod` to bump the build label — reload and confirm
> `#sw-update-banner` appears (the SW noticed the new shell)."*

### Recipe D — real Android Chrome over adb (Phase 2 §3, optional)

For a tethered Android device with USB debugging on:

```bash
adb forward tcp:9222 localabstract:chrome_devtools_remote
# then point chrome-devtools-mcp at --browser-url http://127.0.0.1:9222
```

> *"Attach to the Android Chrome on port 9222, open `https://fellows.globaldonut.com/`,
> drive the magic-link round-trip (I'll paste the link), and confirm the directory loads,
> a fellow detail opens, and selecting a fellow reveals the composer FAB."*

The Add-to-Home-Screen install gesture itself stays manual (the OS install prompt is
outside the page).
