# Email Gate

Authoritative specification of the email-gate / install-landing algorithm. The runtime (`app/static/app.js`, `deploy/server.py`, `deploy/magic_link_auth.py`) must match this document; if they drift, this document is what's right and the runtime is a bug.

Operator procedures (Postmark, env file, Postmark response interpretation) stay in [`email_system_management.md`](email_system_management.md). This file is the behavioral spec.

## Goals

- The default view is the **email gate** — an empty form for requesting a magic link. Everything else requires affirmative state to appear.
- The **install landing** exists only to capture a one-shot "install the PWA" gesture, inside a bounded window after a token was issued. It is not a logged-in home page.
- A dev must always be able to return to the gate in one click, even if auth state is confusing.

## Definitions

- **Session cookie** — `fellows_session`, HttpOnly, HMAC-signed, carrying `token_issued_at` (epoch seconds) and a server-side `session_id`. v3 format; v1 and v2 cookies are rejected on sight so prior sessions re-login cleanly after each version bump.
- **Magic-link token** — single-use, `TOKEN_TTL = 30 min` from issue. Random 32-byte hex.
- **Install window** — `INSTALL_WINDOW = 30 min` measured from token issue (not from click). Same duration as token TTL by design: a user has 30 min from the email being sent to finish clicking and installing.
- **Display mode** — *browser* (`display-mode != standalone`) vs *PWA* (`display-mode: standalone`).

## Invariants

1. **Email gate is the default.** The only exits from it are: (a) a URL carrying an unexpired magic-link token, or (b) an authenticated session *within* the install window, or (c) PWA mode with a valid session (→ directory).
2. **Install landing never repeats.** It shows only inside the install window. Once the window closes, or the user explicitly logs out, the only path back is a fresh magic link.
3. **Expired links are explicit.** Clicking an expired token lands on the email gate with a visible "that link expired" banner.
4. **Invalid links are explicit.** Clicking a tampered or already-consumed token lands on the email gate with "that link isn't valid".
5. **Magic-link emails state the TTL.** Body includes: "This link will expire in 30 minutes."
6. **Session cookie TTL is long** (`SESSION_MAX_AGE = 7 days`) so installed PWAs persist; the install window is decoupled and short.
7. **Dev escape hatch is always reachable.** Two layers:
   - A **"Back to email gate"** control on the install landing, which `POST`s `/api/logout` (clears the cookie server-side) then navigates to `/?gate=1`.
   - A **hardcoded URL override** `/?gate=1` that forces the gate UI regardless of cookie state. Works even when JS-driven logout fails.
8. **Unsupported browsers are told so — on click, not eagerly.** If a user clicks "Install app" and `beforeinstallprompt` never fired (and they're not on iOS Safari), the install landing swaps in a panel asking them to use Chrome, Edge, Safari, or another browser that supports PWA install. No auto-timer: Chrome suppresses `beforeinstallprompt` when the PWA is already installed on the device, and an eager timer would false-positive on those users.
9. **URL-just-works for returning visitors.** A browser-tab visit with `fellows_authenticated_once` set *acts as the app* (directory via API) instead of forcing the install landing. The installed standalone PWA remains the preferred launcher; this is a graceful fallback for users who type/bookmark the URL. `?gate=1` still wins in every case.
10. **A stale session does not lock users out of cached data.** If `/api/fellows` (or `/api/fellows?full=1`) returns 401 during boot, the app falls back to the IndexedDB cache populated by the last successful boot. The build badge flips to `server: offline · using cache` so users know the state. The user can still browse the directory, read profiles, and use the search over cached data. Fresh data requires an explicit `?gate=1` visit to request a new magic link. Rationale: "install once, works forever" — a long-lived local copy should not fail shut when the server session expires.

## Browser-mode decision tree

Evaluated on every page render (after auth-status fetch). Order matters — first match wins.

```
1. URL hash == "#/unlock/<token>"?
     POST /api/verify-token {token}
       → 200 ok        : cookie{token_issued_at=now} set by server; strip hash; fall through to #2
       → 401 expired   : location.replace("/?gate=1&reason=expired")
       → 401 invalid   : location.replace("/?gate=1&reason=invalid")
       → network err   : location.replace("/?gate=1&reason=invalid")

2. localStorage[fellows_authenticated_once] == "1"  AND  ?gate=1 NOT in URL?
     → ACT AS APP (directory via API, same code path as standalone PWA)
       - This is "URL-just-works": a returning user who already installed the
         PWA once sees the directory in a regular browser tab instead of
         being pushed through the install landing again. The installed
         standalone copy remains the preferred launcher; this path is a
         graceful fallback when they type/bookmark the URL.
       - If the API refuses (session expired, 5xx), fall through to
         startBrowserUx (item #3+) so the email gate can appear.

3. ?gate=1 in URL?
     → EMAIL GATE
       ?reason=expired → banner "That link expired. Enter your email to get a new one."
       ?reason=invalid → banner "That link isn't valid. Enter your email to get a new one."
       otherwise       → no banner

4. authStatus.authEnabled == false  (local dev passthrough)
     → INSTALL LANDING (dev has no real gate; this preserves the developer UX)

5. authStatus.authenticated && authStatus.installRecentlyAllowed
     → INSTALL LANDING
       - Install button wired to beforeinstallprompt
       - Unsupported-browser hint only shows on click when prompt isn't
         available (no 3s auto-timer — see PR #47).
       - "Back to email gate" link: POST /api/logout then navigate /?gate=1

6. default
     → EMAIL GATE (no banner)
```

### `fellows_authenticated_once` marker

Set in two places:

- `startBrowserUx` when `/api/auth/status` returns `authenticated: true` — the browser has a valid session, so even if the install window has closed we know this origin has been cleared before.
- Successful `getList()` in app-mode boot (standalone PWA, or browser-tab-acting-as-app) — proves the API accepted our session.

Preserved across `clearAllAppData` (the only localStorage key that survives Clear App Cache). Rationale: "Clear App Cache" exists to fix a broken app, not to log users out of an install they were happily using.

## PWA-mode decision tree

Installed PWAs never see the install landing.

```
1. authStatus.authenticated?  → DIRECTORY
2. otherwise                  → EMAIL GATE (same component as browser mode)
```

## State diagram

```
                      ┌──────────────────────┐
                      │   EMAIL GATE         │◀────────────────────────┐
                      │   (default)          │                         │
                      └──────────┬───────────┘                         │
            submit email         │                                     │
                                 ▼                                     │
                    Postmark sends magic link                          │
                      (expires 30 min)                                 │
                                 │                                     │
     click link within 30 min    │     click expired link              │
                                 │            │                        │
                                 ▼            ▼                        │
                  ┌───────────────────┐   gate + "expired" banner      │
                  │ verify-token: ok  │                                │
                  │ cookie{tia=now}   │                                │
                  └──────────┬────────┘                                │
                             ▼                                         │
                  ┌──────────────────────────┐  logout / window expiry │
                  │  INSTALL LANDING         │  / ?gate=1 URL          │
                  │  (install window)        ├─────────────────────────┘
                  │  [Back to email gate]    │
                  └──────────┬───────────────┘
                             │ click "Install app" → browser installs PWA
                             ▼
                  ┌────────────────────┐
                  │  PWA (standalone)  │
                  │  → DIRECTORY       │
                  └────────────────────┘
```

## Endpoints

| Method | Path                   | Purpose                                                       |
|--------|------------------------|---------------------------------------------------------------|
| GET    | `/api/auth/status`     | Returns `{authEnabled, authenticated, installRecentlyAllowed, hasSessionCookie, build, buildGitSha}`. Never gated. |
| POST   | `/api/send-unlock`     | Accepts `{email}`. Always returns `{sent: true}` (anti-enumeration). Internally: validates shape, checks rate limit, checks allowlist, issues token, sends Postmark email. |
| POST   | `/api/verify-token`    | Accepts `{token}`. Returns `{ok: true}` + Set-Cookie on success; `{ok: false, error: "expired"\|"invalid"}` otherwise (401). |
| POST   | `/api/logout`          | Clears session cookie (Max-Age=0). Always returns `{ok: true}`. |
| POST   | `/api/client-errors`   | Accepts a sanitized client-error report. Always returns 204 (anti-enumeration). Logs `event=client_error` to journald. See § Client error reporting. |

## Client error reporting

Behavioral spec for `POST /api/client-errors` and the gate's "Send diagnostics" button. Implementation: `deploy/server.py:_handle_client_errors` and `deploy/client_error_sanitizer.py`. Surfaces in operations: `just prod-errors` (see `docs/justfile.md`).

### Why it exists

The bug-report dialog (in-app "Report bug" / inline "report a problem to the maintainer") covers the case where a user is willing to open their mail client and describe what happened. The "Send diagnostics" button on the gate covers the case where the user is stuck *at* the gate: they hit Send link, got "Could not send. Try again later.", and need a friction-free way to flag the failure without composing an email. One click → sanitized POST → server-side journald.

### Goal

Capture enough diagnostic detail (browser/OS, the captured error ring, which build was running, the optional `lastSubmitHashPrefix` correlation handle) to triage from the maintainer side, **without** the user disclosing their email, IP, profile slug, magic-link token, or other identifiers.

### Privacy boundary

The privacy boundary is *server-side*. The client tries to send a clean payload, but the server re-sanitizes everything regardless. Trust the server, not the client. The boundary is enforced by `deploy/client_error_sanitizer.py` (pure functions; unit-tested in `tests/test_client_error_sanitizer.py`).

What the maintainer can read in journald:

- **User agent** — `navigator.userAgent`, length-capped at 240. Used for "is this Safari 15 or 16?" triage. Not sanitized further (some browsers encode device names; accepted tradeoff for high signal).
- **Build** — `git_sha @ built_at` of the JS bundle the user was running. Up to 64 chars.
- **Route** — the URL hash route the user was on, with these substitutions: query string dropped (`?…`), `#/fellow/<slug>` redacted to `#/fellow/<redacted>`, `#/unlock/<token>` redacted to `#/unlock/<token>` placeholder (token leak would grant a session).
- **Display mode** — `"standalone"` (installed PWA) or `"browser-tab"`. Other values dropped.
- **Online flag** — `Boolean(navigator.onLine)`.
- **Events** (up to 20) — each has a `kind` from a fixed allow-list (`http`, `sw`, `window.error`, `unhandledrejection`, `console.error`, `install`, `worker`), an optional ISO `ts` (length-capped, not parsed), a `msg` (up to 500 chars, with email + slug + token redaction applied), and an optional `extra` (up to 200 chars, same redaction). Unknown kinds are silently dropped.
- **`lastSubmitHashPrefix`** — only if it matches `^[0-9a-f]{12}$`. This is `sha256(email).slice(0,12)` from a prior gate submit; it's the same join key the server already logs as `email_hash_prefix` in `event=send_unlock_email`. Not reversible to an email at this length, but stable enough to grep journald and find the matching send attempt.
- **`client_ip_prefix`** — first 12 hex of `sha256(client_ip)`. The raw IP is *never* logged. The hash is stable enough that two reports from the same client cluster together; opaque enough that a journald audit doesn't expose a per-fellow source map.

What never reaches journald:

- Raw email addresses (regex-replaced with `<email>` in every free-text field).
- Profile slugs (`#/fellow/<slug>` → `<redacted>`).
- Magic-link tokens (`#/unlock/<token>` → `<redacted>`).
- Query strings (dropped from any URL field).
- The raw client IP.
- Anything that doesn't match the schema's accept-list of top-level keys.

### Schema

Request body (POST, `Content-Type: application/json`, max 16 KB):

```jsonc
{
  "events": [                              // required, array, capped at 20
    {
      "kind": "http",                       // one of: http, sw, window.error, unhandledrejection, console.error, install
      "ts":   "2026-04-30T15:00:00Z",       // optional, ISO-8601, length-capped
      "msg":  "GET /api/fellows → 404",    // free text, sanitized + truncated to 500
      "extra": "..."                        // optional, sanitized + truncated to 200
    }
  ],
  "ua":    "Mozilla/5.0 ...",                // length-capped at 240
  "build": "abc1234 @ 2026-04-30T15:00Z",    // length-capped at 64
  "route": "#/groups/3",                     // sanitized: query stripped, slugs/tokens redacted
  "displayMode": "browser-tab",              // "standalone" or "browser-tab"
  "online": true,                            // boolean
  "lastSubmitHashPrefix": "ab12cd34ef56"     // optional, 12 lowercase-hex chars only
}
```

Unknown top-level keys are silently dropped. Events whose `kind` isn't in the accept-list are silently dropped. Non-conforming `lastSubmitHashPrefix` is silently dropped.

#### `kind=install` events (install-funnel telemetry)

The install landing page (`#install-landing`) fires one-event payloads with `kind=install` at each meaningful step in the install flow, so the maintainer can answer "what fraction of install-landing visits actually saw `beforeinstallprompt` fire vs. timed out?" without instrumenting an analytics pipeline. Same `/api/client-errors` sink, same sanitizer rules — adding the kind to the allowlist doesn't widen what a caller can put in journald.

Event names in `msg`:

| `msg` | Fired when |
|---|---|
| `landing_shown` | The install landing first renders. The denominator for everything below. |
| `ios_safari_advised` | The user is on iOS Safari, where `beforeinstallprompt` doesn't exist; the UI shows the Share → Add to Home Screen hint. |
| `before_prompt_fired` | Chrome/Edge fired `beforeinstallprompt`; install button now active. `extra` carries the comma-joined `event.platforms` (typically `web`). |
| `before_prompt_never_arrived` | 5 seconds after `landing_shown`, no `beforeinstallprompt` seen — engagement heuristic not met, already-installed PWA on the same profile, or unsupported browser. Skipped on iOS Safari (where the event doesn't exist by design). |
| `button_clicked` | User clicked the Install button. |
| `button_clicked_no_prompt` | User clicked Install but no deferred prompt was available — the unsupported-hint surfaces. |
| `outcome_accepted` / `outcome_dismissed` / `outcome_unknown` | Result of the OS install dialog; `extra` carries `choice.platform`. |
| `outcome_error` | The promise from `prompt()` / `userChoice` rejected; `extra` carries the error message (sanitizer-redacted). |
| `app_installed` | The browser's `appinstalled` event fired — terminal success signal. |
| `use_in_tab_clicked` | User took the "Use the directory in this tab" escape hatch instead of installing. |

Operator query — funnel breakdown:

```bash
just prod-stats                # last 24h
just prod-stats '7 days ago'   # weekly view
```

`just prod-stats` parses these events out of journald and renders an `Install funnel:` section under `Client error reports`. Each row counts events by `msg`; `outcome_*` rows include a per-platform breakdown from `extra` (typically `web` for Chrome/Edge/Android Chrome). The section is hidden when there's no install activity in the window. See `scripts/prod_stats.py:_print_install_funnel` for the renderer.

#### `kind=worker` events

Spawn / init outcomes for the dedicated SQLite worker (`vendor/sqlite-worker.js`), used to triage cold-start failures and stuck-boot reports. One event per worker spawn outcome plus, after the boot watchdog ships, one event per stuck boot. Cardinality is bounded — the worker spawns at most twice per page load (warm + at most one re-spawn), and `boot_stuck` fires at most once.

| `msg` | Fired when |
|---|---|
| `spawn_ok` | Warm worker `init` RPC succeeded. `extra` carries `rpc=<n> schema=<n> opfsCapable=<bool> hasFellowsDb=<bool> hasRelDb=<bool>`. |
| `spawn_failed` | Worker construction or `init` RPC failed (timeout, OPFS init error, etc.). `extra` carries the truncated error message. |
| `ownership_conflict` | Worker init refused because another tab already holds the OPFS SAH-pool. Signals that "this app is already open in another tab" panel was shown. |
| `boot_stuck` | `bootDirectoryAsApp` did not reach `get_list_done` within `BOOT_WATCHDOG_MS` (20 s default). `extra` carries the last completed `bootMark` name (`script_start`, `pick_provider_start`, `worker_init_done`, `provider_ready`, …) — this is the load-bearing diagnostic. The recovery panel surfaces the same name to the user. |

Operator query: `journalctl -u fellows-pwa | grep '"kind": "worker"'`. Pair `boot_stuck` events with the user's `ua` and `lastSubmitHashPrefix` (if any) to find the matching session and reproduce.

#### `kind=boot` events

Once-per-page-load success beacon, fired after `bootMark('get_list_done')` succeeds. This is the load-bearing input for `just installed-versions` (see [`plans/install_version_telemetry.md`](../plans/install_version_telemetry.md)) — it's how the operator learns *what build each installed PWA is currently executing*, regardless of whether the user has done anything in this session beyond opening the app.

| `msg` | Fired when |
|---|---|
| `cold_start` | `bootDirectoryAsApp` reached `get_list_done` (success — fresh API or cached). `extra` carries `displayMode=<x>` and, when the data provider has resolved, `provider=<worker|api+idb|api>`. |

Cardinality is bounded to one per page load (module-scope `bootBeaconFired` guard). When `lastSubmitInfo.emailHashPrefix` is in localStorage from a prior magic-link gate submit, the payload includes `lastSubmitHashPrefix` — the join key that ties each boot back to the user's `email_hash_prefix` from the matching `send_unlock_email` event. Anonymous boots (Clear-App-Cache'd, never gated) still report the running `build`, just without the email join.

Operator query: `journalctl -u fellows-pwa | grep '"kind": "boot"'`. `just installed-versions` does the join + plaintext-email lookup automatically.

### Anti-abuse posture

- **Always 204 No Content.** No echo, no error message, no oracle. A probing attacker can't tell whether their payload was logged, dropped on shape, dropped on rate-limit, or dropped because all events were filtered.
- **16 KB body cap** at the `do_POST` layer. Larger → 413, no log emitted.
- **Per-IP rate limit.** Same bucket machinery as `/api/send-unlock` (`deploy/magic_link_auth.py:check_rate_limit`), keyed by `clienterr:<ip_hash_prefix>`. 4th request in the window is silently dropped.
- **Unauthenticated by design.** The whole point is to capture reports from users who couldn't pass the auth gate. Authenticated visitors can use it too; the endpoint never depends on a session cookie.
- **No DB writes, no file writes.** The structured journald event is the only persistence. Wipe operations are journald rotation; no extra cleanup needed.

### Operator triage

`just prod-errors [SINCE]` (see `docs/justfile.md`) prints the 4xx + 5xx access-line counters AND the new `Client error reports:` count, with the recent-errors list interleaving both kinds tagged `[client_error]` vs raw access lines. Pair with the user's `lastSubmitHashPrefix` (if they shared a screenshot of the diag block) to find the matching `event=send_unlock_email` entry: `journalctl -u fellows-pwa | grep '"email_hash_prefix": "ab12cd34ef56"'`.

`just installed-versions [SINCE]` (see [`docs/justfile.md`](justfile.md) and [`plans/install_version_telemetry.md`](../plans/install_version_telemetry.md)) is the "what build is this user actually running?" view. Joins `verify_token` + `kind=boot` events to plaintext emails via `fellows.db`, with a `⚠ STUCK` flag when a user's install build differs from their currently-running build — the dominant symptom of a service-worker update path that didn't take. Plaintext-confidential.



## Cookie format (v3)

Plaintext payload (utf-8): `v3:<session_expires_at>:<token_issued_at>:<session_id>:<nonce>`
Cookie value: `base64url(payload) + "." + hex(hmac_sha256(secret, payload))`

- `session_expires_at` = `int(time.time()) + SESSION_MAX_AGE`.
- `token_issued_at` = the `issued_at` of the magic-link token that granted this session (epoch seconds). `0` only in legacy/test paths.
- `session_id` = a 32-char hex identifier minted by `consume_token` and recorded in `AuthState.sessions`. Required: a cookie whose `session_id` is not in the registry fails verification, so a leaked `FELLOWS_SESSION_SECRET` alone cannot mint a working cookie.
- Sig = `hmac_sha256(FELLOWS_SESSION_SECRET, payload)`.

On every request the server recomputes HMAC, rejects on mismatch, rejects if `session_expires_at < now`, and rejects if `session_id` is missing from the in-memory registry. The install-window check is *separate*: `now - token_issued_at < INSTALL_WINDOW`.

The session registry is in-memory only — a server restart drops it, which is the deliberate one-time logout on each deploy. Every fellow re-authenticates once; subsequent requests within the cookie's 7-day TTL keep working.

## Security notes

- Anti-enumeration: `/api/send-unlock` never reveals whether the email is on the allowlist.
- Distinguishing "expired" vs "invalid" in verify-token leaks only the fact that the token existed at some point. Negligible vs UX win.
- `/api/logout` is idempotent and doesn't require a valid session. That's intentional — the endpoint's job is to guarantee the cookie is cleared, not to validate the caller.
- The URL override `?gate=1` does not bypass auth; it only forces the **UI** to render the gate. Protected endpoints (`/fellows.db`, `/images/*`, directory `/api/*`) still require a valid session.
- `/api/client-errors` is unauthenticated by design (see § Client error reporting) but rate-limited per IP and capped at 16 KB body. Always returns 204, never echoes payload, sanitizes free-text against email / profile-slug / unlock-token leakage before logging.
