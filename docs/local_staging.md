# Local staging server

A local-only server that runs `deploy/server.py` (the production server) on
`http://127.0.0.1:8766` with auth on and Postmark stubbed to a file. Bridges
the gap between the dev server (no auth, no MCPB routes, returns
`authEnabled: false`) and prod (requires a deploy to test).

Use this when you need to verify:

- The magic-link round-trip (gate → email → unlock → session → install landing).
- Auth-gated routes (`/mcpb/<name>.mcpb`, the session-checked `/fellows.db` path, etc.).
- Any UI branch that gates on `authStatus.authEnabled === true`.
- The MCPB Settings UI's "Continue" path, which 404s against the dev server.
- Folder mode (Phase 2) under real session-cookie behavior.

Do **not** use this as a production server. It uses committed test-only
secrets, signs the bundle manifest with the committed dev signing key (which
prod's service-worker origin check rejects), and allows insecure cookies so
the session works over plain HTTP.

## Prereqs

```bash
just doctor               # confirms .venv, fellows.db, Playwright
just build-mcpb           # one-time; only needed for § 6 / § 7 of the test plan
```

Without `just build-mcpb`, the `/mcpb/*` routes will 404. Everything else
works.

## Quick start

```bash
just serve-prod
```

You'll see a banner with the test email (default `you@local-staging.example`)
and the magic-link log path.

Open a **new private window** at `http://127.0.0.1:8766/`. You land at the
email gate — different from `just serve`, which skips the gate entirely.

## Magic-link auth flow

1. Submit the gate form with the test email shown on the startup banner.
2. The fake Postmark stub writes the link to `tmp/prod-local/magic_links.log`
   and prints it to the launcher's stderr.
3. Get the link:
   ```bash
   just serve-prod-link
   ```
4. Paste it into the same browser. The session cookie sets, the install
   landing renders.

The session is a real HMAC-signed v3 cookie. All session-gated routes
behave as they do in prod.

## When to reset

`tmp/prod-local/` is reused across runs by default so you can resume a
session. Reset when:

- You change anything in `app/static/` (the SW would otherwise serve the
  cached old shell from the precache the maintainer-test session installed).
- You rebuild `app/fellows.db` (`just db-rebuild`).
- The launcher complains the manifest is stale.

```bash
just serve-prod-reset      # wipe tmp/prod-local/
just serve-prod            # rebuilds dist on next start
```

## What's different from real prod

| What | Local staging | Prod |
|---|---|---|
| Hostname | `127.0.0.1:8766` (HTTP) | `fellows.globaldonut.com` (HTTPS via Caddy) |
| Session cookie | HMAC-signed, `Secure` flag off | HMAC-signed, `Secure` on |
| Magic-link sender | File + stderr | Real Postmark to real inbox |
| Bundle signing key | Committed dev key | Operator-held prod key (origin-checked in sw.js) |
| CAA / HSTS preload | None | Per `docs/DevOps.md` § Signing keys |
| `fellows.db` | Your local rebuild | Whatever was last deployed |
| `.mcpb` bundles | From `deploy/dist/mcpb/` (run `just build-mcpb` first) | Same path, served from the deployed dist |

The launcher's Handler subclass adds `Cross-Origin-Opener-Policy: same-origin`
and `Cross-Origin-Embedder-Policy: require-corp` — Caddy adds these in prod
and `deploy/server.py` omits them intentionally
(`deploy/server.py:_security_headers` → see comment block). Without them
OPFS-SAH-Pool refuses to install in the browser, and folder mode can't be
tested.

## Troubleshooting

**Port 8766 stuck.** Previous run didn't shut down cleanly.
```bash
just serve-prod-stop
just serve-prod
```

**OPFS panel says "browser not supported".** Either your browser genuinely
doesn't support OPFS-SAH-Pool, or COOP/COEP isn't reaching it. Check
DevTools → Network → response headers for the index page; both
`Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy` should be
present. If not, the Handler subclass isn't taking effect — file a bug.

**Magic-link form says "Could not send."** The fake-Postmark stub raised
something. Check the launcher's stderr; the most common cause is the
test email not in the dist's `fellows.db` (run `just serve-prod-reset`).

**Settings → MCPB → Continue downloads three empty files.** You haven't
run `just build-mcpb`. Bundles live at `deploy/dist/mcpb/*.mcpb`; the
launcher copies them into the staging dist at startup.

**Browser says "your connection is not private."** You're hitting `https://`
by accident — local staging is plain `http://127.0.0.1:8766/`.

## What this doesn't cover

- iOS Safari + Android Chrome real-device installs (need HTTPS + reachable
  hostname — that's a future Option 2 improvement, not here).
- Real Postmark deliverability (spam scoring, DMARC).
- Caddy header preservation regressions (the python server sets CSP /
  Permissions-Policy / CORP itself; the Caddy-added COOP / COEP / HSTS
  layer is only validated on prod).
- Real Let's Encrypt / CAA / HSTS preload.

For those, fall back to the existing prod smoke after deploy
(`just smoke`, `just drift`, manual phone test).

## Related

- `tests/conftest.py:deploy_server` — the in-process pytest fixture this
  launcher mirrors. Keep both consistent.
- `plans/maintainer_test_plan_through_pr_200.md` — items marked `(S)` Ship
  are the ones this launcher moves to `(L)` Local.
- `docs/DevOps.md` § Signing keys — prod signing flow this launcher
  short-circuits with the dev key.
- `docs/email_gate.md` — the magic-link decision tree this launcher
  exercises.
