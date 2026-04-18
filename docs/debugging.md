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
curl -sSI https://fellows.globaldonut.com/api/auth/status | grep -i x-fellows-build
```

Compare with `git log --format='%ci %h' -1 origin/main`. Production has shipped with stale `deploy/dist/` before; if the build timestamp trails main, run `./scripts/deploy_pwa.sh --ask-become-pass`.

Other production debug entry points (service logs, Postmark send flow, Diagnostics panel) live in [`docs/email_system_management.md`](email_system_management.md) and [`docs/DevOps.md`](DevOps.md).
